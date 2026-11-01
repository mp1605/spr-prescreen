"""Atomic source/uncertainty boundaries, independent of sponsor answers."""

import pytest

from backend.core.engines.base import Hit
from backend.core.item_color import assess_item


def test_spelled_and_hyphenated_measurements_keep_source_coordinates(facts):
    text = "20-kilowatt; six hours; eleven homes; 2025"
    features = facts(text)
    assert {f.text for f in features if f.kind == "measurement"} == {"20-kilowatt", "six hours"}
    assert any(f.kind == "quantity" and f.text == "eleven homes" for f in features)
    assert any(f.kind == "date" and f.text == "2025" for f in features)
    assert all(text[f.char_start : f.char_end] == f.text for f in features)


@pytest.mark.parametrize("cue,expected", [("", "clear"), ("Hypothetical: ", "possible")])
def test_literal_performance_needs_topic_and_nonconditional_facts(
    cue, expected, facts, atom_document
):
    text = cue + "Laser prototype destroyed targets at 2 kilometers."
    doc = atom_document(text)
    segment = doc.segments[0]
    hit = Hit(
        segment_id=segment.segment_id,
        item_id="L2-02",
        list="list2",
        detector="Atomic topic",
        char_start=len(cue),
        char_end=len(cue) + 5,
    )
    result = assess_item("L2-02", (hit,), facts(text), {segment.segment_id: segment}, doc.units[0])
    assert result.disposition == expected
    if expected == "clear":
        assert result.rule_anchor.text == "Laser"
        assert all(text[f.char_start : f.char_end] == f.text for f in result.evidence)


def test_generic_standard_sequence_is_not_a_detailed_procedure(facts):
    assert not any(f.kind == "procedure" for f in facts("It differs from the standard sequence."))
    assert any(f.kind == "procedure" for f in facts("It reveals the exact sequence."))
    assert any(f.kind == "procedure" for f in facts("The detailed sequence is provided."))


def test_reported_inability_and_explicit_hypothesis_stay_distinct(facts):
    reported = facts("The evaluation revealed that equipment could not perform its mission.")
    assert any(f.kind == "dependency" for f in reported)
    assert not any(f.kind == "uncertainty" for f in reported)
    hypothetical = facts("The hypothetical evaluation revealed equipment could not perform.")
    assert any(f.kind == "uncertainty" for f in hypothetical)


def test_hoped_for_benefit_does_not_cancel_an_explicit_schedule(facts):
    text = "The team is scheduled to deploy in March 2040, and a change would ease workloads."
    assert not any(f.kind == "uncertainty" for f in facts(text))
    uncertain = "The team would deploy in March 2040 if funding became available."
    assert any(f.kind == "uncertainty" for f in facts(uncertain))
