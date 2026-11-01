"""PyMuPDF extraction in unrotated PDF points, preserving character/word correspondence."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Protocol, cast

import pymupdf  # type: ignore[import-untyped]
from pydantic import BaseModel

from backend.core.ingest_models import IngestLimits, ParseIssue, SourceUnit, WordBox
from backend.core.models import Rect
from backend.core.text_segments import excluded_noise


class PDFPage(Protocol):
    def get_text(self, option: str, *, flags: int, sort: bool) -> object: ...
    def get_images(self, full: bool = False) -> Sequence[object]: ...


class PDFDocument(Protocol):
    is_pdf: bool
    is_encrypted: bool
    needs_pass: bool
    is_repaired: bool
    page_count: int

    def __enter__(self) -> PDFDocument: ...
    def __exit__(self, a: object, b: object, c: TracebackType | None) -> None: ...
    def __getitem__(self, index: int) -> PDFPage: ...


class PDFChar(BaseModel):
    c: str
    bbox: Rect


class PDFSpan(BaseModel):
    chars: tuple[PDFChar, ...] = ()


class PDFLine(BaseModel):
    spans: tuple[PDFSpan, ...] = ()


class PDFBlock(BaseModel):
    type: int
    lines: tuple[PDFLine, ...] = ()


class PDFText(BaseModel):
    width: float
    height: float
    blocks: tuple[PDFBlock, ...] = ()


def _page_unit(page: PDFPage, number: int) -> SourceUnit:
    raw = PDFText.model_validate(
        page.get_text(
            "rawdict",
            flags=int(pymupdf.TEXTFLAGS_RAWDICT) & ~int(pymupdf.TEXT_PRESERVE_IMAGES),
            sort=True,
        )
    )
    pieces: list[str] = []
    words: list[WordBox] = []
    offset = 0
    for block in raw.blocks:
        if block.type != 0:
            continue
        for line in block.lines:
            chars = [char for span in line.spans for char in span.chars]
            text = "".join(char.c for char in chars)
            # MuPDF emits one Unicode character per entry, but allow multi-codepoint glyphs.
            boxes = [char.bbox for char in chars for _ in char.c]
            for match in re.finditer(r"\S+", text):
                boxes_for_word = boxes[match.start() : match.end()]
                if not boxes_for_word:
                    continue
                x0 = min(b[0] for b in boxes_for_word)
                y0 = min(b[1] for b in boxes_for_word)
                x1 = max(b[2] for b in boxes_for_word)
                y1 = max(b[3] for b in boxes_for_word)
                if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
                    raise ValueError("Invalid PDF glyph geometry")
                words.append(
                    WordBox(
                        char_start=offset + match.start(),
                        char_end=offset + match.end(),
                        bbox=(x0, y0, x1, y1),
                    )
                )
            pieces.append(text + "\n")
            offset += len(text) + 1
        pieces.append("\n")
        offset += 1
    text = "".join(pieces)
    return SourceUnit(
        unit_id=number,
        page=number,
        part="pdf",
        text=text,
        width=raw.width,
        height=raw.height,
        words=tuple(words),
        excluded=excluded_noise(text),
    )


def parse_pdf(data: bytes, limits: IngestLimits) -> tuple[list[SourceUnit], list[ParseIssue]]:
    units: list[SourceUnit] = []
    issues: list[ParseIssue] = []
    open_pdf = cast(Callable[..., PDFDocument], pymupdf.open)
    old_errors = pymupdf.TOOLS.mupdf_display_errors(False)
    old_warnings = pymupdf.TOOLS.mupdf_display_warnings(False)
    try:
        with open_pdf(stream=data, filetype="pdf") as document:
            if not document.is_pdf:
                return [], [ParseIssue(code="corrupt_file", message="File content is not a PDF.")]
            if document.is_encrypted or document.needs_pass:
                return [], [
                    ParseIssue(code="encrypted_file", message="Encrypted PDF was not read.")
                ]
            if document.is_repaired:
                issues.append(
                    ParseIssue(
                        code="repaired_pdf",
                        message="PDF required repair; verify the source manually.",
                    )
                )
            if document.page_count > limits.max_pages:
                issues.append(
                    ParseIssue(
                        code="resource_limit",
                        message="Page limit reached; remaining PDF pages were not read.",
                    )
                )
            characters = 0
            for index in range(min(document.page_count, limits.max_pages)):
                try:
                    page = document[index]
                    unit = _page_unit(page, index + 1)
                    characters += len(unit.text)
                    if characters > limits.max_characters:
                        issues.append(
                            ParseIssue(
                                code="resource_limit",
                                page=index + 1,
                                message="Text limit reached; remaining content was not read.",
                            )
                        )
                        break
                    units.append(unit)
                    if not any(c.isalnum() for c in unit.text):
                        issues.append(
                            ParseIssue(
                                code="unreadable_page",
                                page=index + 1,
                                message="Page has no readable text; OCR was not performed.",
                            )
                        )
                    elif unit.text.count("\ufffd") / max(1, len(unit.text)) > 0.02:
                        issues.append(
                            ParseIssue(
                                code="damaged_text",
                                page=index + 1,
                                message="Text encoding is damaged; source inspection is required.",
                            )
                        )
                    if page.get_images(full=True):
                        issues.append(
                            ParseIssue(
                                code="unsupported_content",
                                page=index + 1,
                                message="Raster image content was not read; OCR was not performed.",
                            )
                        )
                except Exception:
                    issues.append(
                        ParseIssue(
                            code="unreadable_page",
                            page=index + 1,
                            message="Page extraction failed; source inspection is required.",
                        )
                    )
    except Exception:
        issues.append(ParseIssue(code="corrupt_file", message="PDF could not be opened or read."))
    finally:
        pymupdf.TOOLS.mupdf_display_errors(old_errors)
        pymupdf.TOOLS.mupdf_display_warnings(old_warnings)
    return units, issues
