"""Add PDF highlights and notes without changing the original page contents."""

from __future__ import annotations

import pymupdf  # type: ignore[import-untyped]

from backend.core.annotation_notes import AnnotationError, finding_note, overridden, summary_note
from backend.core.batch_models import ReviewState
from backend.core.models import PaperResult


def annotate_pdf(
    data: bytes, paper: PaperResult, review: ReviewState, *, notes: bool = False
) -> bytes:
    try:
        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.needs_pass or not document.page_count:
                raise AnnotationError(
                    "This PDF cannot be opened for annotation. Export JSON instead."
                )
            if document.get_sigflags() > 0:
                raise AnnotationError(
                    "Signed PDFs require manual handling. Export JSON and the original."
                )
            if sum(len(f.location.bbox or ()) for f in paper.findings) > 200_000:
                raise AnnotationError("PDF annotation geometry exceeds the export resource limit.")
            # Lowest priority first: red remains visible on cross-list overlaps.
            for flag in sorted(paper.findings, key=lambda f: f.color == "red"):
                dismissed = overridden(flag, review)
                if dismissed and not notes:
                    continue
                loc = flag.location
                if not loc.page or loc.page > document.page_count or not loc.bbox:
                    raise AnnotationError(
                        "A finding has no usable PDF coordinates. Export JSON instead."
                    )
                page = document[loc.page - 1]
                rotation = page.rotation
                page.set_rotation(0)
                quads = []
                for box in loc.bbox:
                    rect = pymupdf.Rect(box)
                    if not page.rect.contains(rect):
                        raise AnnotationError(
                            "PDF evidence falls outside its page. Export JSON instead."
                        )
                    quads.append(pymupdf.Quad(rect.tl, rect.tr, rect.bl, rect.br))
                if dismissed:
                    annotation = page.add_text_annot(quads[0].ul, finding_note(flag, paper, review))
                    annotation.set_colors(stroke=(0.55, 0.55, 0.55))
                else:
                    annotation = page.add_highlight_annot(quads)
                    annotation.set_colors(stroke=(1, 0, 0) if flag.color == "red" else (1, 1, 0))
                    annotation.set_opacity(0.35)
                if notes:
                    annotation.set_info(
                        title="SPR Pre-Screen",
                        subject=", ".join(flag.items),
                        content=finding_note(flag, paper, review),
                    )
                annotation.update()
                page.set_rotation(rotation)
            if notes:
                first = document[0]
                rotation = first.rotation
                first.set_rotation(0)
                note = first.add_text_annot(
                    (first.rect.x0 + 8, first.rect.y0 + 8), summary_note(paper, review)
                )
                note.set_info(title="SPR Pre-Screen", subject="Review copy and source provenance")
                note.update()
                first.set_rotation(rotation)
            result: bytes = document.tobytes(garbage=3, deflate=True)
            return result
    except AnnotationError:
        raise
    except Exception as exc:
        raise AnnotationError(
            "PDF annotation failed. Export JSON and inspect the original."
        ) from exc
