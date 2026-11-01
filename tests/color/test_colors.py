import pytest

from backend.core.color_models import SpecificityFeature
from backend.core.engines.base import Hit
from backend.core.item_color import assess_item
from backend.core.screen import screen_document
from tests.color.conftest import AS_OF

# Typed source-feature contracts isolate the color policy from NLP/retrieval accuracy.
CLEAR_CASES = {
    "L2-01": ("quantity", "unit"),
    "L2-02": ("program", "measurement"),
    "L2-03": ("system", "measurement"),
    "L2-04": ("quantity", "location"),
    "L2-05": ("program", "measurement"),
    "L2-06": ("quantity", "unit"),
    "L2-07": ("quantity", "unit"),
    "L2-08": ("program", "measurement"),
    "L2-09": ("system", "measurement"),
    "L2-10": ("quantity", "unit", "future_date"),
    "L2-11": ("program", "measurement"),
    "L2-12": ("quantity", "unit"),
    "L2-13": ("quantity", "unit", "operational"),
    "L2-14": ("quantity", "unit"),
    "L2-15": ("procedure", "unit", "future_date"),
    "L2-16": ("system", "measurement"),
    "L2-17": ("procedure", "system", "measurement"),
    "L2-18": ("future_date", "location"),
    "L2-19": ("origin_release", "location"),
    "L2-21": ("authority_action",),
    "L2-24": ("rank",),
    "L2-25": ("control", "program", "measurement"),
    "L2-27": ("coordination_gap", "actor"),
    "L2-28": ("coordination_gap", "unit"),
    "L2-29": ("quantity", "system"),
    "L2-30": ("system", "measurement"),
    "L2-31": ("release_event", "location", "measurement"),
}


@pytest.mark.parametrize("item_id,kinds", CLEAR_CASES.items())
def test_every_supported_clear_condition_needs_its_source_facts(item_id, kinds, atom_document):
    text = item_id + " | " + " | ".join(kinds)
    document = atom_document(text)
    features = tuple(
        SpecificityFeature(
            kind=kind, text=kind, char_start=text.index(kind), char_end=text.index(kind) + len(kind)
        )
        for kind in kinds
    )
    hit = Hit(
        segment_id=document.segments[0].segment_id,
        item_id=item_id,
        list="list2",
        detector="Numerical condition contract",
        char_start=0,
        char_end=len(item_id),
    )
    result = assess_item(
        item_id,
        (hit,),
        features,
        {document.segments[0].segment_id: document.segments[0]},
        document.units[0],
    )
    assert result.disposition == "clear" and result.rule_anchor.text == item_id
    result = assess_item(
        item_id,
        (hit,),
        (),
        {document.segments[0].segment_id: document.segments[0]},
        document.units[0],
    )
    assert result.disposition == "possible" and result.reason


@pytest.mark.parametrize("index", range(31))
def test_official_item_wording_alone_stays_possible(index, registry, assessor, atom_document):
    result = screen_document(
        atom_document(registry.list2[index].text), registry, specificity=assessor, as_of=AS_OF
    )
    assert all(
        flag.color == "yellow" and flag.why_unsure
        for flag in result.findings
        if flag.list == "list2"
    )


def test_quantity_unit_multi_item_group_is_red_and_generic_topic_yellow(
    registry, assessor, atom_document
):
    result = screen_document(
        atom_document("F-22 · 3 aircraft · 7th Wing · readiness", registry.list2[3].text),
        registry,
        specificity=assessor,
        as_of=AS_OF,
    )
    assert result.color == "red" and result.flag_count.total == 2
    assert result.flag_count.red == result.flag_count.yellow == 1
    specific = result.findings[0]
    assert {"L2-06", "L2-12", "L2-14"} <= set(specific.items)
    assert all(item.rule_anchor and item.evidence for item in specific.assessment.items)


@pytest.mark.parametrize("cue", ["hypothetical", "could", "if", "does not disclose"])
def test_uncertain_context_prevents_promotion_without_removing_flags(
    cue, registry, assessor, atom_document
):
    result = screen_document(
        atom_document(f"{cue} · F-22 · 3 aircraft · 7th Wing · readiness"),
        registry,
        specificity=assessor,
        as_of=AS_OF,
    )
    assert result.color == "yellow" and result.findings[0].why_unsure
    assert "L2-06" in result.findings[0].items


def test_judgment_items_remain_possible_inside_a_red_multi_item_flag(
    registry, assessor, atom_document
):
    result = screen_document(
        atom_document("F-22 · 3 aircraft · 7th Wing · national interest"),
        registry,
        specificity=assessor,
        as_of=AS_OF,
    )
    flag = result.findings[0]
    values = {item.item_id: item.disposition for item in flag.assessment.items}
    assert flag.color == "red" and values["L2-06"] == "clear" and values["L2-20"] == "possible"
    assert "L2-20" in flag.why_unsure


def test_adjacent_sentence_facts_cannot_promote_an_unrelated_topic(
    registry, assessor, atom_document
):
    result = screen_document(
        atom_document("F-22. 3 aircraft · 7th Wing."), registry, specificity=assessor, as_of=AS_OF
    )
    code = next(flag for flag in result.findings if "L2-06" in flag.items)
    assert code.color == "yellow"


def test_specificity_failure_keeps_flags_and_marks_incomplete(
    registry, assessor, atom_document, monkeypatch
):
    def failed(*args, **kwargs):
        raise RuntimeError("Do not log source text")

    monkeypatch.setattr(assessor, "features", failed)
    result = screen_document(
        atom_document("(CUI)", "F-22 · 3 aircraft · 7th Wing"),
        registry,
        specificity=assessor,
        as_of=AS_OF,
    )
    assert result.color == "red" and result.fusion.state == "error"
    assert result.flag_count.total == 2 and result.incomplete_reasons
    assert result.findings[-1].color == "yellow"


def test_high_semantic_score_with_numeric_features_is_still_possible(atom_document):
    from backend.core.semantic_models import SemanticMatch

    document = atom_document("L2-06 | quantity | unit")
    text = document.units[0].text
    reference = SemanticMatch(item_id="L2-06", text="F-22", score=0.99, band="high")
    hit = Hit(
        segment_id=document.segments[0].segment_id,
        item_id="L2-06",
        list="list2",
        detector="Official reference",
        engine="semantic",
        score=0.99,
        reference=reference,
        char_start=0,
        char_end=len(text),
    )
    features = tuple(
        SpecificityFeature(
            kind=kind, text=kind, char_start=text.index(kind), char_end=text.index(kind) + len(kind)
        )
        for kind in ("quantity", "unit")
    )
    result = assess_item(
        "L2-06",
        (hit,),
        features,
        {document.segments[0].segment_id: document.segments[0]},
        document.units[0],
    )
    assert result.disposition == "possible" and "Semantic resemblance" in result.reason


def test_future_date_uses_recorded_clock_and_changes_finding_identity(
    registry, assessor, atom_document
):
    from datetime import date

    document = atom_document("Deployment schedules or locations · Washington D.C. · May 2030")
    before = screen_document(document, registry, specificity=assessor, as_of=date(2030, 1, 1))
    after = screen_document(document, registry, specificity=assessor, as_of=date(2031, 1, 1))
    first = next(f for f in before.findings if "L2-18" in f.items)
    second = next(f for f in after.findings if "L2-18" in f.items)
    assert first.color == "red" and second.color == "yellow"
    assert first.finding_id != second.finding_id
    assert before.fusion.as_of_utc_date == date(2030, 1, 1)
