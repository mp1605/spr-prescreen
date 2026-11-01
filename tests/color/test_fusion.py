import hashlib

import pytest
from pydantic import ValidationError

from backend.core.engines.base import Hit
from backend.core.fuse import fuse_findings
from backend.core.ingest_models import ParseResult, Segment, SourceUnit, WordBox
from backend.core.models import Finding, Location
from backend.core.screen import screen_document
from tests.color.conftest import AS_OF


def overlap_document(pdf=False):
    text = "Animal testing and directed energy"
    words = []
    cursor = 0
    for index, word in enumerate(text.split()):
        start = text.index(word, cursor)
        words.append(
            WordBox(
                char_start=start,
                char_end=start + len(word),
                bbox=(10 + index * 25, 10, 30 + index * 25, 20),
            )
        )
        cursor = start + len(word)
    locator = {"page": 1} if pdf else {"paragraph": 1}
    unit = SourceUnit(
        unit_id=1,
        part="pdf" if pdf else "word/document.xml",
        text=text,
        words=tuple(words) if pdf else (),
        width=300 if pdf else None,
        height=200 if pdf else None,
        **locator,
    )
    split = text.index("and")
    segments = []
    for name, start, end in [("a", 0, split + 3), ("b", split, len(text))]:
        boxes = tuple(
            word.bbox for word in words if word.char_start < end and start < word.char_end
        )
        segments.append(
            Segment(
                segment_id=name,
                unit_id=1,
                text=text[start:end],
                location=Location(
                    char_start=start, char_end=end, bbox=boxes if pdf else None, **locator
                ),
            )
        )
    return ParseResult(
        paper_id="sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        file_name="coordinate-contract.pdf" if pdf else "coordinate-contract.docx",
        file_type="pdf" if pdf else "docx",
        byte_count=0,
        status="complete",
        units=(unit,),
        segments=tuple(segments),
    )


@pytest.mark.parametrize("pdf", [False, True])
def test_overlap_union_is_one_exact_source_passage(pdf, registry, assessor):
    document = overlap_document(pdf)
    hits = (
        Hit(segment_id="a", item_id="L2-01", list="list2", detector="A", char_start=0, char_end=6),
        Hit(
            segment_id="b",
            item_id="L2-02",
            list="list2",
            detector="B",
            char_start=document.units[0].text.index("directed"),
            char_end=len(document.units[0].text),
        ),
    )
    flags, info = fuse_findings(
        document, hits + hits, registry, assessor, as_of=AS_OF, profile="contract"
    )
    assert len(flags) == 1 and flags[0].items == ("L2-01", "L2-02")
    assert flags[0].quote == document.units[0].text and flags[0].color == "yellow"
    assert info.state == "complete"
    if pdf:
        assert flags[0].location.bbox == tuple(word.bbox for word in document.units[0].words)


def test_disjoint_spans_and_different_units_remain_separate(registry, assessor, atom_document):
    document = atom_document("Animal testing. Directed energy.", "Animal testing")
    result = screen_document(document, registry, specificity=assessor, as_of=AS_OF)
    assert result.flag_count.total == 3
    assert {f.location.paragraph for f in result.findings} == {1, 2}


def test_lists_are_never_cross_merged_and_ids_include_pipeline_provenance(
    registry, assessor, atom_document
):
    document = atom_document("(CUI) F-22")
    before = document.model_dump_json()
    legacy = screen_document(document, registry)
    one = screen_document(document, registry, specificity=assessor, as_of=AS_OF)
    two = screen_document(document, registry, specificity=assessor, as_of=AS_OF)
    assert [flag.list for flag in one.findings] == ["list1", "list2"]
    assert one.findings == two.findings
    assert {f.finding_id for f in one.findings}.isdisjoint(f.finding_id for f in legacy.findings)
    assert document.model_dump_json() == before


def test_numeric_evidence_cannot_be_fabricated(registry, assessor, atom_document):
    result = screen_document(
        atom_document("F-22 · 3 aircraft · 7th Wing"), registry, specificity=assessor, as_of=AS_OF
    )
    payload = result.findings[0].model_dump(mode="json")
    payload["assessment"]["items"][0]["evidence"][0]["text"] = "invented evidence"
    with pytest.raises(ValidationError, match="exact finding source"):
        Finding.model_validate(payload)


def test_excluded_noise_is_not_added_back_by_fusion(registry, assessor, atom_document):
    document = atom_document(
        "Animal testing\nAI-GENERATED FAKE CONTENT FOR EDUCATIONAL PURPOSES ONLY\nDirected energy"
    )
    assert all("AI-GENERATED" not in segment.text for segment in document.segments)
    result = screen_document(document, registry, specificity=assessor, as_of=AS_OF)
    assert len(result.findings) == 2
    assert all("AI-GENERATED" not in flag.quote for flag in result.findings)


def test_no_candidates_stays_green_and_unreadable_source_stays_incomplete(
    registry, assessor, atom_document
):
    from backend.core.ingest import parse_document

    clean = screen_document(atom_document("List 1"), registry, specificity=assessor, as_of=AS_OF)
    assert clean.color == "green" and clean.label == "No flags found" and clean.fusion
    bad = screen_document(
        parse_document("corrupt.pdf", b""), registry, specificity=assessor, as_of=AS_OF
    )
    assert bad.color == "yellow" and bad.label == "Incomplete"
