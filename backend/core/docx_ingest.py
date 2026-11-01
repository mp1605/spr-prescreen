"""Read Word stories without executing fields, following hyperlinks, or unpacking files."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from io import BytesIO
from pathlib import PurePosixPath
from typing import Protocol, cast
from zipfile import ZipFile

from docx import Document
from docx.oxml import parse_xml
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from backend.core.ingest_models import IngestLimits, ParseIssue, SourceRun, SourceUnit
from backend.core.text_segments import excluded_noise


class Element(Protocol):
    text: str | None
    tag: str

    def xpath(self, expression: str) -> Sequence[Element]: ...
    def get(self, key: str) -> str | None: ...


class Style(Protocol):
    name: str


class ParagraphLike(Protocol):
    style: Style | None


class RunLike(Protocol):
    text: str
    bold: bool | None
    italic: bool | None
    underline: object


class WordDocument(Protocol):
    part: object


class ArchiveLimit(ValueError):
    pass


def validate_archive(archive: ZipFile, limits: IngestLimits) -> list[str]:
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    if (
        len(entries) > limits.max_zip_entries
        or sum(i.file_size for i in entries) > limits.max_uncompressed_bytes
    ):
        raise ArchiveLimit("DOCX exceeds the package expansion limit.")
    if len(names) != len(set(names)):
        raise ArchiveLimit("DOCX has ambiguous duplicate package entries.")
    if any(
        PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts or "\\" in n for n in names
    ):
        raise ArchiveLimit("DOCX has invalid package paths.")
    if any(i.flag_bits & 1 for i in entries):
        raise ArchiveLimit("Encrypted package entries cannot be read.")
    for name in names:
        if name.endswith((".xml", ".rels")):
            if b"<!DOCTYPE" in archive.read(name).upper():
                raise ArchiveLimit("DOCX contains a prohibited XML document type declaration.")
    return names


def _story_names(names: list[str]) -> list[str]:
    stories = [
        n
        for n in names
        if re.fullmatch(
            r"word/(?:document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml",
            n,
        )
    ]
    return sorted(stories, key=lambda n: (n != "word/document.xml", n))


def _runs(node: Element, parent: ParagraphLike) -> tuple[str, tuple[SourceRun, ...]]:
    make_run = cast(Callable[[object, object], RunLike], Run)
    runs = []
    chunks = []
    offset = 0
    for element in node.xpath(".//w:r"):
        ancestors = element.xpath("ancestor::w:p[1]")
        if not ancestors or ancestors[0] is not node:
            continue  # Text-box paragraphs receive their own global paragraph locator.
        run = make_run(element, parent)
        text = run.text
        deleted = element.xpath(".//w:delText")
        if deleted:
            text += "".join(e.text or "" for e in deleted)
        if not text:
            continue
        links = element.xpath("ancestor::w:hyperlink[1]")
        hyperlink = (
            links[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            if links
            else None
        )
        runs.append(
            SourceRun(
                char_start=offset,
                char_end=offset + len(text),
                text=text,
                bold=bool(run.bold),
                italic=bool(run.italic),
                underline=bool(run.underline),
                hyperlink=hyperlink,
            )
        )
        chunks.append(text)
        offset += len(text)
    return "".join(chunks), tuple(runs)


def parse_docx(data: bytes, limits: IngestLimits) -> tuple[list[SourceUnit], list[ParseIssue]]:
    units: list[SourceUnit] = []
    issues: list[ParseIssue] = []
    try:
        with ZipFile(BytesIO(data)) as archive:
            names = validate_archive(archive, limits)
            open_word = cast(Callable[[BytesIO], WordDocument], Document)
            document = open_word(BytesIO(data))
            parse = cast(Callable[[bytes], Element], parse_xml)
            make_paragraph = cast(Callable[[object, object], ParagraphLike], Paragraph)
            characters = 0
            for part in _story_names(names):
                tree = parse(archive.read(part))
                if tree.xpath(
                    ".//*[local-name()='drawing' or local-name()='pict' or "
                    "local-name()='object' or local-name()='altChunk' or local-name()='oMath']"
                ):
                    issues.append(
                        ParseIssue(
                            code="unsupported_content",
                            message="Word visual or embedded content requires human inspection.",
                        )
                    )
                if tree.xpath(
                    ".//*[local-name()='ins' or local-name()='del' or "
                    "local-name()='moveFrom' or local-name()='moveTo']"
                ):
                    issues.append(
                        ParseIssue(
                            code="unsupported_content",
                            message="Tracked changes present; revision text was retained.",
                        )
                    )
                heading: str | None = None
                for node in tree.xpath(
                    ".//*[local-name()='p' and namespace-uri()='"
                    "http://schemas.openxmlformats.org/wordprocessingml/2006/main']"
                ):
                    if len(units) >= limits.max_paragraphs:
                        return units, issues + [
                            ParseIssue(
                                code="resource_limit",
                                message="Paragraph limit reached; remaining content was not read.",
                            )
                        ]
                    paragraph = make_paragraph(node, document.part)
                    text, runs = _runs(node, paragraph)
                    characters += len(text)
                    if characters > limits.max_characters:
                        return units, issues + [
                            ParseIssue(
                                code="resource_limit",
                                message="Word text limit reached; remaining content was not read.",
                            )
                        ]
                    style = paragraph.style
                    if text.strip() and (
                        (style and style.name.lower().startswith("heading"))
                        or node.xpath("./w:pPr/w:outlineLvl")
                    ):
                        heading = text.strip()
                    unit = SourceUnit(
                        unit_id=len(units) + 1,
                        paragraph=len(units) + 1,
                        part=part,
                        text=text,
                        runs=runs,
                        heading=heading,
                        excluded=excluded_noise(text),
                    )
                    units.append(unit)
    except ArchiveLimit as exc:
        issues.append(ParseIssue(code="resource_limit", message=str(exc)))
    except Exception:
        issues.append(
            ParseIssue(
                code="corrupt_file", message="Word package could not be opened or read completely."
            )
        )
    return units, issues
