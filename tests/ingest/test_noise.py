from io import BytesIO

from docx import Document

from backend.core.ingest import parse_document
from backend.core.ingest_models import SourceUnit
from backend.core.text_segments import excluded_noise, segments_for


def test_noise_is_excluded_without_rewriting_source_offsets(official_rules):
    policy = official_rules.list2[0].text
    text = (
        "AI-GENERATED FAKE CONTENT FOR EDUCATIONAL PURPOSES ONLY\n"
        f"{policy}. (fictional author)\n"
        "Fictional source: List 2\nPage 1 of 2\n"
        f"{policy}."
    )
    unit = SourceUnit(
        unit_id=1, paragraph=1, part="word/document.xml", text=text, excluded=excluded_noise(text)
    )
    segments = segments_for(unit)
    assert len(segments) == 2 and segments[0].text == segments[1].text == policy + "."
    assert {e.reason for e in unit.excluded} == {
        "educational_banner",
        "fictional_author",
        "fictional_source",
        "page_footer",
    }
    assert segments[0].location.char_start == text.index(policy)
    assert segments[1].location.char_start == text.rindex(policy)
    for segment in segments:
        assert text[segment.location.char_start : segment.location.char_end] == segment.text


def test_narrative_mentions_are_not_removed(official_rules):
    # Prefixes inside a sentence are not boilerplate lines.
    text = official_rules.list2[-1].text + " Page 2"
    assert not excluded_noise(text)


def test_noise_only_document_is_incomplete():
    document = Document()
    document.add_paragraph("AI-GENERATED FAKE CONTENT FOR EDUCATIONAL PURPOSES ONLY")
    document.add_paragraph("Page 1")
    buffer = BytesIO()
    document.save(buffer)
    result = parse_document("format.docx", buffer.getvalue())
    assert result.status == "incomplete" and not result.segments
    assert result.review_color == "yellow"


def test_official_abbreviations_and_line_wrapping_do_not_lose_text(official_rules):
    text = official_rules.list2[23].text
    unit = SourceUnit(unit_id=1, paragraph=1, part="word/document.xml", text=text)
    assert [s.text for s in segments_for(unit)] == [text]
