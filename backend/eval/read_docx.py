"""DOCX key reader consumes caller-provided bytes; no filesystem discovery or external links."""

from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from backend.core.docx_ingest import validate_archive
from backend.core.ingest_models import IngestLimits
from backend.eval.key_format import KeyBlock, KeyFormatError, KeyParagraph, KeyRun, KeyTable


def _paragraph(paragraph: Paragraph) -> KeyParagraph:
    runs: list[KeyRun] = []
    text: list[str] = []
    offset = 0
    for element in paragraph.iter_inner_content():
        children = (element,) if isinstance(element, Run) else element.runs
        for run in children:
            value = run.text
            style = run.style
            bold = run.bold if run.bold is not None else style.font.bold
            if bold is None and paragraph.style is not None:
                bold = paragraph.style.font.bold
            superscript = run.font.superscript
            if superscript is None:
                superscript = style.font.superscript
            if value:
                runs.append(KeyRun(offset, offset + len(value), bool(bold), bool(superscript)))
                text.append(value)
                offset += len(value)
    return KeyParagraph("".join(text), tuple(runs), True)


def read_docx(data: bytes) -> tuple[KeyBlock, ...]:
    if len(data) > IngestLimits().max_file_bytes:
        raise KeyFormatError("Key exceeds the format-reader byte limit")
    try:
        with ZipFile(BytesIO(data)) as archive:
            validate_archive(archive, IngestLimits())
        document = Document(BytesIO(data))
        if document.element.body.xpath(".//w:ins | .//w:del | .//w:moveFrom | .//w:moveTo"):
            raise KeyFormatError("Tracked key revisions must be resolved before parsing")
        blocks: list[KeyBlock] = []
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                blocks.append(_paragraph(block))
            elif isinstance(block, Table):
                rows = tuple(tuple(cell.text for cell in row.cells) for row in block.rows)
                paragraphs = tuple(
                    _paragraph(p)
                    for row in block.rows
                    for cell in row.cells
                    for p in cell.paragraphs
                )
                blocks.append(KeyTable(rows, paragraphs))
        return tuple(blocks)
    except KeyFormatError:
        raise
    except Exception:
        raise KeyFormatError("DOCX key format could not be read completely") from None
