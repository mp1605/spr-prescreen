"""Source-verified annotated copies; scanner findings and original files are never edited."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from backend.core.annotate_docx import annotate_docx
from backend.core.annotate_pdf import annotate_pdf
from backend.core.annotation_notes import AnnotationError
from backend.core.batch_models import ReviewState
from backend.core.ingest_models import IngestLimits, ParseResult
from backend.core.models import PaperResult


@dataclass(frozen=True)
class AnnotatedCopy:
    data: bytes
    warnings: tuple[str, ...]


def annotate(
    data: bytes,
    parsed: ParseResult,
    paper: PaperResult,
    review: ReviewState,
    *,
    notes: bool = False,
    bookmarks: bool = False,
) -> AnnotatedCopy:
    if len(data) > IngestLimits().max_file_bytes:
        raise AnnotationError("Original exceeds the annotation size limit.")
    if (
        "sha256:" + hashlib.sha256(data).hexdigest() != paper.paper_id
        or parsed.paper_id != paper.paper_id
    ):
        raise AnnotationError("Original SHA-256 does not match the stored screening result.")
    if parsed.file_type != paper.file_type:
        raise AnnotationError("Original format does not match the stored screening result.")
    for flag in paper.findings:
        unit = next(
            (
                u
                for u in parsed.units
                if (u.page, u.paragraph) == (flag.location.page, flag.location.paragraph)
            ),
            None,
        )
        if (
            unit is None
            or unit.text[flag.location.char_start : flag.location.char_end] != flag.quote
        ):
            raise AnnotationError("Stored evidence does not match the parsed source.")
    if paper.file_type == "docx":
        content, warnings = annotate_docx(
            data, parsed, paper, review, notes=notes, bookmarks=bookmarks
        )
        return AnnotatedCopy(content, warnings)
    return AnnotatedCopy(annotate_pdf(data, paper, review, notes=notes), ())
