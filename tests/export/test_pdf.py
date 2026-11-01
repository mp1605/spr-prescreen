import pymupdf
import pytest

from backend.core.annotate import annotate
from backend.core.annotation_notes import AnnotationError


def pdf_bytes(rotation=0):
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_text((60, 80), "(CUI)")
        page.insert_text((60, 120), "Animal testing")
        page.add_text_annot((30, 30), "Original note")
        page.set_rotation(rotation)
        return doc.tobytes()


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdf_annotations_keep_content_rotation_and_existing_notes(rotation, prepared, empty_review):
    data = pdf_bytes(rotation)
    parsed, paper = prepared(data, "pdf")
    result = annotate(data, parsed, paper, empty_review, notes=True)
    with (
        pymupdf.open(stream=result.data, filetype="pdf") as doc,
        pymupdf.open(stream=data, filetype="pdf") as original,
    ):
        assert doc[0].rotation == rotation
        assert doc[0].get_text() == original[0].get_text()
        page = doc[0]
        annotations = list(page.annots())
        highlights = [a for a in annotations if a.type[1] == "Highlight"]
        assert len(highlights) == paper.flag_count.total
        assert {tuple(a.colors["stroke"]) for a in highlights} == {(1, 0, 0), (1, 1, 0)}
        assert any("Original note" in a.info["content"] for a in annotations)
        assert any(paper.paper_id[7:] in a.info["content"] for a in annotations)
        assert any("L1-1" in a.info["content"] for a in highlights)
        assert any("L2-01" in a.info["content"] for a in highlights)
        assert all("Pre-screen only" in a.info["content"] for a in highlights)


def test_pdf_missing_geometry_is_explicit_not_silently_skipped(prepared, empty_review):
    data = pdf_bytes()
    parsed, paper = prepared(data, "pdf")
    first = paper.findings[0]
    paper = paper.model_copy(
        update={
            "findings": (
                first.model_copy(
                    update={"location": first.location.model_copy(update={"bbox": None})}
                ),
                *paper.findings[1:],
            )
        }
    )
    with pytest.raises(AnnotationError, match="coordinates"):
        annotate(data, parsed, paper, empty_review, notes=True)
