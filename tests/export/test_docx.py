import io
from zipfile import ZipFile

import pytest
from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn

from backend.core.annotate import annotate
from backend.core.annotation_notes import AnnotationError
from backend.core.ingest import parse_document
from backend.core.models import Finding
from tests.export.conftest import word_bytes


def package(data):
    with ZipFile(io.BytesIO(data)) as archive:
        return {n: archive.read(n) for n in archive.namelist()}


def test_docx_highlights_comments_and_untouched_parts(official_word, prepared, empty_review):
    parsed, paper = prepared(official_word)
    result = annotate(official_word, parsed, paper, empty_review, notes=True)
    parts = package(result.data)
    original = package(official_word)
    body = parse_xml(parts["word/document.xml"])
    comments = parse_xml(parts["word/comments.xml"])
    assert {h.get(qn("w:val")) for h in body.xpath(".//w:highlight")} == {"red", "yellow"}
    notes = ["".join(c.itertext()) for c in comments]
    assert any("L1-1" in n for n in notes) and any("L2-01" in n for n in notes)
    assert any("Original SHA-256: " + paper.paper_id[7:] in n for n in notes)
    assert any("NOT_MADE_BY_TOOL" in n for n in notes)
    assert len(Document(io.BytesIO(result.data)).comments) == 3
    for name in original:
        if name not in ("word/document.xml", "word/_rels/document.xml.rels", "[Content_Types].xml"):
            assert parts[name] == original[name]
    reparsed = parse_document("annotated.docx", result.data)
    assert [u.text for u in reparsed.units[: len(parsed.units)]] == [u.text for u in parsed.units]
    assert result.warnings == ()


def test_partial_run_highlight_preserves_bold_tabs_breaks_and_exact_text(prepared, empty_review):
    document = Document()
    run = document.add_paragraph().add_run("[ Animal testing ]\t\n")
    run.bold = True
    run.italic = True
    data = word_bytes(document)
    parsed, paper = prepared(data)
    original = paper.findings[0]
    start = original.quote.index("Animal")
    payload = original.model_dump()
    payload.update(
        quote="Animal testing",
        location=original.location.model_copy(update={"char_start": start, "char_end": start + 14}),
    )
    flag = Finding.model_validate(payload)
    paper = paper.model_copy(update={"findings": (flag,)})
    output = annotate(data, parsed, paper, empty_review, notes=True).data
    body = parse_xml(package(output)["word/document.xml"])
    highlighted = body.xpath(".//w:r[w:rPr/w:highlight]")
    assert "".join("".join(r.xpath("./w:t/text()")) for r in highlighted) == "Animal testing"
    assert all(r.xpath("./w:rPr/w:b") and r.xpath("./w:rPr/w:i") for r in highlighted)
    assert Document(io.BytesIO(output)).paragraphs[0].text == document.paragraphs[0].text
    assert len(body.xpath(".//w:tab")) == len(
        parse_xml(package(data)["word/document.xml"]).xpath(".//w:tab")
    )


def test_hyperlink_field_and_existing_comment_survive(prepared, empty_review):
    document = Document()
    p = document.add_paragraph()
    r = p.add_run("Animal ")
    r.bold = True
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(
        qn("r:id"),
        document.part.relate_to("https://example.invalid/", RT.HYPERLINK, is_external=True),
    )
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = "testing"
    run.append(text)
    hyperlink.append(run)
    p._p.append(hyperlink)
    field = OxmlElement("w:r")
    char = OxmlElement("w:fldChar")
    char.set(qn("w:fldCharType"), "begin")
    field.append(char)
    p._p.append(field)
    document.add_comment(r, "Existing review note", author="Original")
    data = word_bytes(document)
    parsed, paper = prepared(data)
    output = annotate(data, parsed, paper, empty_review, notes=True).data
    parts = package(output)
    body = parse_xml(parts["word/document.xml"])
    comments = parse_xml(parts["word/comments.xml"])
    assert len(body.xpath(".//w:hyperlink")) == 1 and len(body.xpath(".//w:fldChar")) == 1
    assert "https://example.invalid/" in parts["word/_rels/document.xml.rels"].decode()
    ids = [c.get(qn("w:id")) for c in comments]
    assert len(ids) == len(set(ids))
    assert any("Existing review note" in "".join(c.itertext()) for c in comments)
    assert len(Document(io.BytesIO(output)).comments) >= 3


def test_table_header_and_comment_stories_get_highlights_with_explicit_fallback(
    prepared, empty_review
):
    document = Document()
    document.add_paragraph("List 1")
    document.add_table(rows=1, cols=1).cell(0, 0).text = "Animal testing"
    document.sections[0].header.paragraphs[0].text = "Directed energy"
    r = document.paragraphs[0].runs[0]
    document.add_comment(r, "Animal testing", author="Original")
    data = word_bytes(document)
    parsed, paper = prepared(data)
    output = annotate(data, parsed, paper, empty_review, notes=True)
    parts = package(output.data)
    assert parse_xml(parts["word/header1.xml"]).xpath(".//w:highlight")
    assert parse_xml(parts["word/comments.xml"]).xpath(".//w:highlight")
    assert len(output.warnings) == 2
    assert all("note on document summary" in w for w in output.warnings)
    body = parse_xml(parts["word/document.xml"])
    assert body.xpath(".//w:tbl//w:highlight")
    # No invalid comment anchors are placed in headers or comments themselves.
    assert not parse_xml(parts["word/header1.xml"]).xpath(".//w:commentRangeStart")
    assert not parse_xml(parts["word/comments.xml"]).xpath(".//w:commentRangeStart")


def test_cross_list_overlap_red_wins_without_losing_either_note(prepared, empty_review):
    document = Document()
    document.add_paragraph("(CUI) Animal testing")
    data = word_bytes(document)
    parsed, paper = prepared(data)
    result = annotate(data, parsed, paper, empty_review, notes=True)
    body = parse_xml(package(result.data)["word/document.xml"])
    assert {n.get(qn("w:val")) for n in body.xpath(".//w:highlight")} == {"red"}
    notes = package(result.data)["word/comments.xml"].decode()
    assert "L1-1" in notes and "L2-01" in notes


def test_wrong_source_hash_is_refused(official_word, prepared, empty_review):
    parsed, paper = prepared(official_word)
    with pytest.raises(AnnotationError, match="SHA-256"):
        annotate(official_word + b"changed", parsed, paper, empty_review, notes=True)


def test_unflagged_word_story_retains_original_bytes(prepared, empty_review):
    document = Document()
    document.add_paragraph("Animal testing")
    document.sections[0].header.paragraphs[0].text = "List 1"
    data = word_bytes(document)
    parsed, paper = prepared(data)
    output = annotate(data, parsed, paper, empty_review, notes=True).data
    assert package(output)["word/header1.xml"] == package(data)["word/header1.xml"]
