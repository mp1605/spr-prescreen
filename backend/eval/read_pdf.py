"""PDF key text/bold-span and ruled-table reader, isolated from the scanner."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import redirect_stdout
from io import StringIO
from typing import Protocol, cast

import pymupdf  # type: ignore[import-untyped]
from pydantic import BaseModel

from backend.core.ingest_models import IngestLimits
from backend.eval.key_format import KeyBlock, KeyFormatError, KeyParagraph, KeyRun, KeyTable


class Span(BaseModel):
    text: str
    flags: int


class Line(BaseModel):
    spans: tuple[Span, ...] = ()


class Block(BaseModel):
    lines: tuple[Line, ...] = ()


class PageText(BaseModel):
    blocks: tuple[Block, ...] = ()


class PDFTable(Protocol):
    def extract(self) -> Sequence[Sequence[str | None]]: ...


class Tables(Protocol):
    tables: Sequence[PDFTable]


class Page(Protocol):
    def get_text(self, option: str, *, sort: bool) -> object: ...
    def find_tables(self) -> Tables: ...
    def get_images(self) -> Sequence[object]: ...


class PDF(Protocol):
    is_pdf: bool
    needs_pass: bool
    is_encrypted: bool
    is_repaired: bool
    page_count: int

    def __getitem__(self, index: int) -> Page: ...
    def close(self) -> None: ...


def _paragraph(page: Page) -> KeyParagraph:
    raw = PageText.model_validate(page.get_text("dict", sort=False))
    chunks: list[str] = []
    runs: list[KeyRun] = []
    offset = 0
    for block in raw.blocks:
        for line in block.lines:
            for span in line.spans:
                if span.text:
                    runs.append(
                        KeyRun(
                            offset,
                            offset + len(span.text),
                            bool(span.flags & 16),
                            bool(span.flags & 1),
                        )
                    )
                    chunks.append(span.text)
                    offset += len(span.text)
            chunks.append("\n")
            offset += 1
        chunks.append("\n")
        offset += 1
    return KeyParagraph("".join(chunks), tuple(runs), False)


def read_pdf(data: bytes) -> tuple[KeyBlock, ...]:
    if len(data) > IngestLimits().max_file_bytes:
        raise KeyFormatError("Key exceeds the format-reader byte limit")
    document: PDF | None = None
    old_errors = pymupdf.TOOLS.mupdf_display_errors(False)
    old_warnings = pymupdf.TOOLS.mupdf_display_warnings(False)
    try:
        open_pdf = cast(Callable[..., PDF], pymupdf.open)
        document = open_pdf(stream=data, filetype="pdf")
        if (
            not document.is_pdf
            or document.is_encrypted
            or document.needs_pass
            or document.is_repaired
        ):
            raise KeyFormatError("PDF key is encrypted, repaired, or not a native PDF")
        if document.page_count > IngestLimits().max_pages:
            raise KeyFormatError("PDF key exceeds the page limit")
        output: list[KeyBlock] = []
        for index in range(document.page_count):
            page = document[index]
            paragraph = _paragraph(page)
            if not paragraph.text.strip() and page.get_images():
                raise KeyFormatError("PDF key contains an image-only unreadable page")
            output.append(paragraph)
            with redirect_stdout(StringIO()):
                tables = page.find_tables().tables
            for table in tables:
                output.append(
                    KeyTable(tuple(tuple(cell or "" for cell in row) for row in table.extract()))
                )
        return tuple(output)
    except KeyFormatError:
        raise
    except Exception:
        raise KeyFormatError("PDF key format could not be read completely") from None
    finally:
        if document is not None:
            document.close()
        pymupdf.TOOLS.mupdf_display_errors(old_errors)
        pymupdf.TOOLS.mupdf_display_warnings(old_warnings)
