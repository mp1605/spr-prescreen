"""Official phrases and atomic format contracts; no sponsor papers or key content."""

import hashlib
import io
from datetime import UTC, datetime
from zipfile import ZipFile

import numpy as np
import pymupdf
import pytest
from docx import Document
from docx.shared import Inches, Pt
from PIL import Image

from backend.core.annotate import annotate
from backend.core.batch_models import BatchEntry, BatchRecord
from backend.core.run_store import RunStore
from backend.core.word_converter import PreviewError, convert_word
from backend.core.word_preview import WordPreview, verify_renderable
from tests.conftest import ROOT
from tests.export.conftest import word_bytes
from tests.export.test_docx import package
from tests.export.test_pdf import pdf_bytes


def test_default_docx_adds_only_highlights(official_word, prepared, empty_review):
    parsed, paper = prepared(official_word)
    result = annotate(official_word, parsed, paper, empty_review)
    before, after = package(official_word), package(result.data)
    assert before.keys() == after.keys()
    assert "word/comments.xml" not in after
    assert not Document(io.BytesIO(result.data)).comments
    assert b"bookmarkStart" not in after["word/document.xml"]
    for name in before:
        if name != "word/document.xml":
            assert before[name] == after[name]
    assert [p.text for p in Document(io.BytesIO(official_word)).paragraphs] == [
        p.text for p in Document(io.BytesIO(result.data)).paragraphs
    ]


def test_default_pdf_has_no_added_note_icons_and_identical_page_streams(prepared, empty_review):
    data = pdf_bytes()
    parsed, paper = prepared(data, "pdf")
    result = annotate(data, parsed, paper, empty_review)
    with (
        pymupdf.open(stream=data, filetype="pdf") as original,
        pymupdf.open(stream=result.data, filetype="pdf") as copy,
    ):
        a, b = original[0], copy[0]
        assert a.get_contents() == b.get_contents()
        assert [original.xref_stream(x) for x in a.get_contents()] == [
            copy.xref_stream(x) for x in b.get_contents()
        ]
        assert a.get_text("words") == b.get_text("words")
        # MuPDF's annotation transparency group changes 8-bit rounding by at most 1.
        pixels_a = np.frombuffer(a.get_pixmap(annots=False).samples, dtype=np.uint8).astype(int)
        pixels_b = np.frombuffer(b.get_pixmap(annots=False).samples, dtype=np.uint8).astype(int)
        assert np.abs(pixels_a - pixels_b).max() <= 1
        notes = [n for n in b.annots() if n.type[1] == "Text"]
        assert len(notes) == 1 and notes[0].info["content"] == "Original note"
        assert len([n for n in b.annots() if n.type[1] == "Highlight"]) == len(paper.findings)
        assert all(not n.info["content"] for n in b.annots() if n.type[1] == "Highlight")


def layout_fixture():
    document = Document()
    document.styles["Normal"].font.name = "Arial"
    document.styles["Normal"].font.size = Pt(12)
    section = document.sections[0]
    section.header.paragraphs[0].text = "Directed energy"
    document.add_heading("List 1", 1)
    document.add_paragraph("(CUI)").runs[0].bold = True
    table = document.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    for cell, text in zip(
        [c for row in table.rows for c in row.cells],
        ["Animal testing", "List 2", "List 1", "Animal testing"],
        strict=True,
    ):
        cell.text = text
    image = io.BytesIO()
    Image.new("RGB", (80, 40), (25, 100, 140)).save(image, format="PNG")
    image.seek(0)
    document.add_picture(image, width=Inches(1))
    document.add_page_break()
    document.add_heading("List 2", 1)
    document.add_paragraph("Animal testing")
    document.add_comment(document.paragraphs[0].runs[0], "Animal testing", author="Format contract")
    return word_bytes(document)


def seed(root, data, parsed, paper):
    store = RunStore(root)
    run, entry = "web-" + "a" * 32, "b" * 32
    store.save(
        BatchRecord(
            run_id=run,
            created=datetime.now(UTC),
            rules_version=paper.rules_version,
            entries=(
                BatchEntry(entry_id=entry, file_name="format.docx", phase="done", result=paper),
            ),
        )
    )
    store.save_source(run, entry, data)
    store.save_parse(run, entry, parsed)
    return store, run, entry


def test_real_word_pages_keep_geometry_images_tables_and_exact_anchors(
    tmp_path, prepared, monkeypatch
):
    (tmp_path / "runtime").symlink_to(ROOT / "runtime", target_is_directory=True)
    data = layout_fixture()
    parsed, paper = prepared(data)
    store, run, entry = seed(tmp_path, data, parsed, paper)
    preview = WordPreview(tmp_path, store)
    path, layout = preview.prepare(run, entry)
    assert len(layout.units) == 2
    assert layout.anchors and set(layout.anchors) | set(layout.unmapped) == {
        f.finding_id for f in paper.findings
    }
    comment_flag = next(
        f
        for f in paper.findings
        if next(u for u in parsed.units if u.paragraph == f.location.paragraph).part
        == "word/comments.xml"
    )
    assert comment_flag.finding_id in layout.unmapped
    body_paragraph = max(
        u.paragraph
        for u in parsed.units
        if u.part == "word/document.xml" and u.text == "Animal testing"
    )
    body_last = next(f for f in paper.findings if f.location.paragraph == body_paragraph)
    assert layout.anchors[body_last.finding_id].page == 2
    original_dir = tmp_path / "source-render"
    original_dir.mkdir()
    source = original_dir / "original.docx"
    source.write_bytes(data)
    original_pdf = convert_word(tmp_path, source, original_dir)
    with pymupdf.open(original_pdf) as original, pymupdf.open(path) as highlighted:
        assert len(original) == len(highlighted)
        for a, b in zip(original, highlighted, strict=True):
            assert a.rect == b.rect
            assert a.get_text("words") == b.get_text("words")
            assert len(a.get_images()) == len(b.get_images())
            assert len(a.get_drawings()) < len(b.get_drawings())  # native highlight rectangles
    import backend.core.word_preview as module

    monkeypatch.setattr(module, "convert_word", lambda *args: pytest.fail("Cache rerendered"))
    assert preview.prepare(run, entry)[1] == layout
    assert preview.page(run, entry, layout.identity, 2).startswith(b"\x89PNG")
    with pytest.raises(PreviewError, match="unavailable"):
        preview.page(run, entry, "0" * 64, 1)
    assert (
        hashlib.sha256(store.source(run, entry).read_bytes()).digest()
        == hashlib.sha256(data).digest()
    )
    store.source(run, entry).write_bytes(b"changed")
    with pytest.raises(PreviewError, match="SHA-256"):
        preview.prepare(run, entry)


def test_missing_renderer_is_actionable(tmp_path):
    with pytest.raises(PreviewError, match="highlighted DOCX"):
        convert_word(tmp_path, tmp_path / "source.docx", tmp_path)


def test_external_resource_is_not_followed():
    parts = package(layout_fixture())
    parts["word/_rels/document.xml.rels"] = parts["word/_rels/document.xml.rels"].replace(
        b"</Relationships>",
        b'<Relationship Id="remote" Type="image" Target="https://example.invalid/image" '
        b'TargetMode="External"/></Relationships>',
    )
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    with pytest.raises(PreviewError, match="Externally linked"):
        verify_renderable(stream.getvalue())
