import hashlib

import pymupdf

from backend.core.ingest import parse_document
from backend.core.ingest_models import IngestLimits


def make_pdf(*texts):
    with pymupdf.open() as document:
        for text in texts:
            page = document.new_page()
            page.insert_text((50, 60), text)
        return document.tobytes()


def test_original_guide_all_pages_have_exact_locators(guide_pdf):
    result = parse_document("official-guide.PDF", guide_pdf)
    assert result.paper_id == "sha256:" + hashlib.sha256(guide_pdf).hexdigest()
    assert result.status == "complete" and len(result.units) == 4
    assert {s.location.page for s in result.segments} == {1, 2, 3, 4}
    assert all(s.location.bbox for s in result.segments)
    for segment in result.segments:
        unit = result.units[segment.unit_id - 1]
        loc = segment.location
        assert unit.text[loc.char_start : loc.char_end] == segment.text
        for x0, y0, x1, y1 in loc.bbox:
            assert 0 <= x0 < x1 <= unit.width + 1
            assert 0 <= y0 < y1 <= unit.height + 1


def test_repeated_text_has_distinct_offsets_and_rectangles(official_rules):
    text = official_rules.list2[0].text
    data = make_pdf(f"{text}.\n{text}.")
    result = parse_document("policy.pdf", data)
    assert result.status == "complete"
    assert len(result.segments) == 2
    a, b = result.segments
    assert a.text == b.text
    assert a.location.char_start != b.location.char_start
    assert a.location.bbox != b.location.bbox
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for word in result.units[0].words:
            loc = result.units[0].text[word.char_start : word.char_end]
            assert document[0].get_textbox(pymupdf.Rect(word.bbox)).strip() == loc


def test_blank_page_does_not_hide_readable_pages(official_rules):
    result = parse_document("policy.pdf", make_pdf(official_rules.list2[0].text, ""))
    assert result.status == "incomplete" and result.review_color == "yellow"
    assert result.incomplete_pages == (2,)
    assert result.segments[0].location.page == 1


def test_image_only_page_is_incomplete_without_ocr(guide_pdf):
    with pymupdf.open(stream=guide_pdf, filetype="pdf") as source:
        image = source[0].get_pixmap().tobytes("png")
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_image(page.rect, stream=image)
        data = document.tobytes()
    result = parse_document("image.pdf", data)
    assert result.status == "incomplete" and result.review_color == "yellow"
    assert result.incomplete_pages == (1,) and not result.segments
    assert any(i.code == "unreadable_page" for i in result.issues)


def test_encrypted_pdf_is_not_opened(guide_pdf):
    with pymupdf.open(stream=guide_pdf, filetype="pdf") as document:
        encrypted = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="format-fixture",
            user_pw="format-fixture",
        )
    result = parse_document("encrypted.pdf", encrypted)
    assert result.status == "incomplete" and result.review_color == "yellow"
    assert result.issues[0].code == "encrypted_file" and not result.segments


def test_page_and_character_limits_leave_an_explicit_issue(guide_pdf):
    for limits in (IngestLimits(max_pages=1), IngestLimits(max_characters=1)):
        result = parse_document("guide.pdf", guide_pdf, limits=limits)
        assert result.status == "incomplete"
        assert any(i.code == "resource_limit" for i in result.issues)


def test_rotation_keeps_coordinates_in_unrotated_pdf_space(official_rules):
    data = make_pdf(official_rules.list2[0].text)
    with pymupdf.open(stream=data, filetype="pdf") as document:
        document[0].set_rotation(90)
        data = document.tobytes()
    result = parse_document("rotated.pdf", data)
    assert result.status == "complete"
    assert result.units[0].width < result.units[0].height
    assert result.segments[0].location.bbox[0][0] == 50
