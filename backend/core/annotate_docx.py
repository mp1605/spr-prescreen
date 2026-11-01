"""Annotate a copy of an OOXML package; untouched parts retain their original bytes."""

from __future__ import annotations

import posixpath
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from lxml import etree  # type: ignore[import-untyped]

from backend.core.annotation_notes import AnnotationError, finding_note, summary_note
from backend.core.batch_models import ReviewState
from backend.core.docx_ingest import _story_names, validate_archive
from backend.core.ingest_models import IngestLimits, ParseResult
from backend.core.models import Finding, PaperResult
from backend.core.word_annotations import (
    Xml,
    anchor_bookmark,
    anchor_comment,
    annotate_paragraph,
    bookmark_name,
    source_runs,
)

REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
COMMENT_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"
CONTENT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"


def xml_bytes(tree: Xml) -> bytes:
    result: bytes = etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True)
    return result


def xml_text(text: str) -> str:
    return "".join(
        c
        for c in text
        if c in "\t\n\r"
        or "\x20" <= c <= "\ud7ff"
        or "\ue000" <= c <= "\ufffd"
        or "\U00010000" <= c <= "\U0010ffff"
    )


class Comments:
    def __init__(self, package: dict[str, bytes]) -> None:
        self.package = package
        rel_path = "word/_rels/document.xml.rels"
        self.relationships = (
            etree.fromstring(package[rel_path])
            if rel_path in package
            else etree.Element("{" + REL_NS + "}Relationships", nsmap={None: REL_NS})
        )
        existing = [r for r in self.relationships if r.get("Type") == COMMENT_REL]
        if len(existing) > 1 or any(r.get("TargetMode") == "External" for r in existing):
            raise AnnotationError("Word comment relationships are ambiguous.")
        if existing:
            target = existing[0].get("Target", "")
            self.path = posixpath.normpath(
                target.lstrip("/") if target.startswith("/") else posixpath.join("word", target)
            )
            if self.path not in package:
                raise AnnotationError("Existing Word comments are unavailable.")
            self.tree = parse_xml(package[self.path])
        else:
            self.path = "word/comments.xml"
            if self.path in package:
                raise AnnotationError("An unlinked Word comments part requires manual handling.")
            self.tree = parse_xml(f"<w:comments {nsdecls('w')}/>".encode())
            ids = {r.get("Id") for r in self.relationships}
            identifier = 1
            while f"rId{identifier}" in ids:
                identifier += 1
            etree.SubElement(
                self.relationships,
                "{" + REL_NS + "}Relationship",
                Id=f"rId{identifier}",
                Type=COMMENT_REL,
                Target="comments.xml",
            )
        types = etree.fromstring(package["[Content_Types].xml"])
        matching = [t for t in types if t.get("PartName") == "/" + self.path]
        if not matching:
            etree.SubElement(
                types,
                "{" + CONTENT_NS + "}Override",
                PartName="/" + self.path,
                ContentType=COMMENT_TYPE,
            )
        self.types = types
        comment_ids = [int(c.get(qn("w:id"))) for c in self.tree if c.get(qn("w:id"), "").isdigit()]
        self.next_id = max(comment_ids, default=-1) + 1

    def add(self, text: str, first: Xml, last: Xml) -> None:
        identifier = self.next_id
        self.next_id += 1
        comment = OxmlElement("w:comment")
        comment.set(qn("w:id"), str(identifier))
        comment.set(qn("w:author"), "SPR Pre-Screen")
        comment.set(qn("w:initials"), "SPR")
        for line in xml_text(text).splitlines():
            paragraph = OxmlElement("w:p")
            run = OxmlElement("w:r")
            node = OxmlElement("w:t")
            node.set(qn("xml:space"), "preserve")
            node.text = line
            run.append(node)
            paragraph.append(run)
            comment.append(paragraph)
        self.tree.append(comment)
        anchor_comment(first, last, identifier)

    def save(self) -> None:
        self.package[self.path] = xml_bytes(self.tree)
        self.package["word/_rels/document.xml.rels"] = xml_bytes(self.relationships)
        self.package["[Content_Types].xml"] = xml_bytes(self.types)


def annotate_docx(
    data: bytes,
    parsed: ParseResult,
    paper: PaperResult,
    review: ReviewState,
    *,
    notes: bool = False,
    bookmarks: bool = False,
) -> tuple[bytes, tuple[str, ...]]:
    try:
        with ZipFile(BytesIO(data)) as archive:
            names = validate_archive(archive, IngestLimits())
            if any(n.startswith("_xmlsignatures/") for n in names):
                raise AnnotationError(
                    "Signed Word packages require manual handling. Export JSON instead."
                )
            package = {n: archive.read(n) for n in names}
        trees = {n: parse_xml(package[n]) for n in _story_names(names)}
        if "word/document.xml" not in trees:
            raise AnnotationError("Word document body is unavailable.")
        paragraphs = [(part, p) for part, tree in trees.items() for p in tree.xpath(".//w:p")]
        # Parser stops early on resource limits; never guess the unparsed remainder's coordinates.
        units = {u.paragraph: u for u in parsed.units}
        flags_by_paragraph: dict[int, list[Finding]] = {}
        for flag in paper.findings:
            if flag.location.paragraph is None or flag.location.paragraph not in units:
                raise AnnotationError("Word evidence has no parsed paragraph.")
            flags_by_paragraph.setdefault(flag.location.paragraph, []).append(flag)
        comments = Comments(package) if notes else None
        body = trees["word/document.xml"]
        summary_paragraph = next(
            (p for p in body.xpath(".//w:p") if not p.xpath("ancestor::w:txbxContent")), None
        )
        if notes and summary_paragraph is None:
            summary_paragraph = OxmlElement("w:p")
            body.find(qn("w:body")).insert(0, summary_paragraph)
        warnings = []
        fallback = []
        changed_parts: set[str] = set()
        bookmark_ids = [
            int(n.get(qn("w:id")))
            for tree in trees.values()
            for n in tree.xpath(".//w:bookmarkStart")
            if n.get(qn("w:id"), "").isdigit()
        ]
        bookmark_id = max(bookmark_ids, default=0) + 1
        # Nested text boxes are processed before their containing runs, so copying an object
        # cannot discard annotations already applied inside it.
        for index in reversed(range(len(paragraphs))):
            part, node = paragraphs[index]
            flags = flags_by_paragraph.get(index + 1, [])
            if not flags:
                continue
            unit = units[index + 1]
            if unit.part != part:
                raise AnnotationError("Word story identity no longer matches its evidence.")
            pieces = annotate_paragraph(node, unit.text, flags)
            changed_parts.add(part)
            for flag in flags:
                covered = [
                    p
                    for p in pieces
                    if p.start < flag.location.char_end and flag.location.char_start < p.end
                ]
                if not covered:
                    raise AnnotationError("Word finding has no annotatable text runs.")
                if bookmarks:
                    anchor_bookmark(
                        covered[0].node,
                        covered[-1].node,
                        bookmark_id,
                        bookmark_name(flag.finding_id),
                    )
                    bookmark_id += 1
                if comments is None:
                    continue
                note = finding_note(flag, paper, review)
                if part == "word/document.xml" and not node.xpath("ancestor::w:txbxContent"):
                    comments.add(note, covered[0].node, covered[-1].node)
                else:
                    label = f"{part}, paragraph {index + 1}"
                    fallback.append(
                        f"Highlighted in {label}. Comment placed on the document summary.\n" + note
                    )
                    warnings.append(
                        f"{flag.finding_id}: highlighted in {label}; note on document summary."
                    )
        if comments is not None:
            assert summary_paragraph is not None
            runs = source_runs(summary_paragraph)
            if runs:
                summary_run = runs[0]
            else:
                summary_run = OxmlElement("w:r")
                summary_paragraph.append(summary_run)
            comments.add(summary_note(paper, review), summary_run, summary_run)
            for note in fallback:
                comments.add(note, summary_run, summary_run)
            changed_parts.add("word/document.xml")
        # Do not overwrite a standard comments tree after appending our notes to it.
        for part, tree in trees.items():
            if comments is None or part != comments.path:
                if part in changed_parts:
                    package[part] = xml_bytes(tree)
            else:
                # Existing comment text may itself be screened and highlighted.
                for old in list(comments.tree):
                    replacement = next(
                        (c for c in tree if c.get(qn("w:id")) == old.get(qn("w:id"))), None
                    )
                    if replacement is not None:
                        comments.tree.replace(old, replacement)
        if comments is not None:
            comments.save()
        output = BytesIO()
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for name, content in package.items():
                archive.writestr(name, content)
        return output.getvalue(), tuple(warnings)
    except AnnotationError:
        raise
    except Exception as exc:
        raise AnnotationError(
            "Word annotation failed. Export JSON and inspect the original."
        ) from exc
