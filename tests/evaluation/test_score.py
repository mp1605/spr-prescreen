import pytest

from backend.eval.matching import grouped_passages, match_passages, text_similarity
from backend.eval.models import GoldCase, GoldTrigger, Passage
from backend.eval.report import render_report
from backend.eval.score import score_cases


def trigger(quote, items=("L2-01",), color="yellow", tag="T1"):
    return GoldTrigger(tag=tag, quote=quote, items=items, color=color, reason="Math contract")


def test_known_metrics_confusion_misses_decoys_and_cost(registry, prediction):
    a, b = [item.text for item in registry.list2[:2]]
    gold = (
        GoldCase(case_id="match", expected_color="yellow", triggers=(trigger(a),)),
        GoldCase(case_id="miss", expected_color="yellow", triggers=(trigger(b, ("L2-02",)),)),
        GoldCase(case_id="false", expected_color="green", decoys=(b,), reference_good=True),
    )
    actual = (
        prediction("match", [(a, ("L2-01",), "yellow")]),
        prediction("miss"),
        prediction("false", [(b, ("L2-02",), "yellow")]),
    )
    report = score_cases(gold, actual, kind="format_contract")
    assert report.trigger_count == 2 and report.matched_triggers == 1
    assert report.trigger_recall == report.list2_recall == 0.5
    assert report.list1_recall is None
    assert report.false_alarms == 1 and report.weighted_cost == 4
    assert report.greens_wrongly_flagged == report.decoys_flagged == 1
    assert report.false_alarms_on_reference_papers == 1
    assert report.paper_color_accuracy == pytest.approx(1 / 3)
    assert report.confusion["yellow"]["yellow"] == 1
    assert report.confusion["yellow"]["green"] == 1
    assert report.confusion["green"]["yellow"] == 1
    assert report.cases[1].missed[0].quote == b


def test_one_broad_passage_cannot_claim_two_triggers(registry, prediction):
    a, b = [item.text for item in registry.list2[:2]]
    gold = GoldCase(
        case_id="broad",
        expected_color="yellow",
        triggers=(trigger(a), trigger(b, ("L2-02",), tag="T2")),
    )
    actual = prediction("broad", [(a + " " + b, ("L2-01", "L2-02"), "yellow")])
    report = score_cases((gold,), (actual,), kind="format_contract")
    assert report.matched_triggers == 1 and report.trigger_recall == 0.5
    assert len(report.cases[0].missed) == 1


def test_maximum_matching_avoids_greedy_assignment_loss(registry):
    quote = registry.list2[0].text
    gold = (trigger(quote), trigger(quote, ("L2-02",), tag="T2"))
    broad = Passage(finding_ids=("broad",), quote=quote, items=("L2-01", "L2-02"), color="yellow")
    narrow = Passage(finding_ids=("narrow",), quote=quote, items=("L2-01",), color="yellow")
    assert match_passages((broad, narrow), gold) == {0: 1, 1: 0}


def test_duplicate_same_list_findings_are_extra_false_alarms(registry, prediction):
    quote = registry.list2[0].text
    gold = GoldCase(case_id="duplicate", expected_color="yellow", triggers=(trigger(quote),))
    specs = [(quote, ("L2-01",), "yellow", 1)] * 2
    actual = prediction("duplicate", specs)
    report = score_cases((gold,), (actual,), kind="format_contract")
    assert report.matched_triggers == 1 and report.false_alarms == 1


def test_identical_cross_list_evidence_is_one_passage(registry, prediction):
    quote = registry.list2[0].text
    gold = GoldCase(
        case_id="cross-list",
        expected_color="red",
        triggers=(trigger(quote, ("L1-1", "L2-01"), "red"),),
    )
    actual = prediction(
        "cross-list", [(quote, ("L1-1",), "red", 1), (quote, ("L2-01",), "yellow", 1)]
    )
    report = score_cases((gold,), (actual,), kind="format_contract")
    assert len(grouped_passages(actual.result.findings)) == 1
    assert report.false_alarms == 0 and report.list1_recall == report.list2_recall == 1


def test_list_specific_recall_requires_agreement_on_that_list(registry, prediction):
    quote = registry.list2[0].text
    gold = GoldCase(
        case_id="partial",
        expected_color="red",
        triggers=(trigger(quote, ("L1-1", "L2-01"), "red"),),
    )
    actual = prediction("partial", [(quote, ("L2-01",), "yellow")])
    report = score_cases((gold,), (actual,), kind="format_contract")
    assert report.trigger_recall == report.list2_recall == 1
    assert report.list1_recall == 0 and report.item_accuracy == 0.5
    assert report.flag_color_accuracy == 0 and report.paper_color_accuracy == 0


def test_wrong_item_id_does_not_match_an_identical_quote(registry, prediction):
    quote = registry.list2[0].text
    gold = GoldCase(case_id="wrong-item", expected_color="yellow", triggers=(trigger(quote),))
    actual = prediction("wrong-item", [(quote, ("L2-02",), "yellow")])
    report = score_cases((gold,), (actual,), kind="format_contract")
    assert report.trigger_recall == 0 and report.false_alarms == 1
    assert report.flag_color_accuracy is None


def test_zero_trigger_and_color_accuracy_denominators_are_honest(prediction):
    gold = GoldCase(case_id="zero", expected_color="green")
    report = score_cases((gold,), (prediction("zero"),), kind="format_contract")
    assert report.trigger_recall is report.list1_recall is report.list2_recall is None
    assert report.item_accuracy is report.flag_color_accuracy is report.decoy_flag_rate is None
    assert report.paper_color_accuracy == 1 and report.weighted_cost == 0
    assert "Not defined" in render_report(report)


def test_incomplete_is_counted_without_inventing_an_evidence_false_alarm(prediction):
    gold = GoldCase(case_id="incomplete", expected_color="green")
    report = score_cases(
        (gold,), (prediction("incomplete", incomplete=True),), kind="format_contract"
    )
    assert report.incomplete_papers == 1 and report.paper_color_accuracy == 0
    assert report.false_alarms == report.greens_wrongly_flagged == 0


def test_ai_timing_uses_attempts_without_changing_denominators(prediction):
    gold = tuple(GoldCase(case_id=name, expected_color="green") for name in ("off", "on"))
    actual = (prediction("off", seconds=2), prediction("on", ai_state="ran", seconds=4))
    report = score_cases(gold, actual, kind="format_contract")
    assert report.seconds_per_paper_ai_off == 2 and report.seconds_per_paper_ai_on == 4


@pytest.mark.parametrize(
    "problem", ["missing", "extra", "duplicate_gold", "duplicate_prediction", "empty", "hash"]
)
def test_invalid_evaluation_sets_cannot_silently_change_a_denominator(problem, prediction):
    one = GoldCase(case_id="one", expected_color="green")
    gold, actual = (one,), (prediction("one"),)
    if problem == "missing":
        actual = ()
    elif problem == "extra":
        actual += (prediction("extra"),)
    elif problem == "duplicate_gold":
        gold += (one,)
    elif problem == "duplicate_prediction":
        actual += actual
    elif problem == "empty":
        gold = actual = ()
    else:
        gold = (one.model_copy(update={"paper_id": "sha256:" + "a" * 64}),)
    with pytest.raises(ValueError):
        score_cases(gold, actual, kind="format_contract")


def test_text_matching_boundaries_and_unicode():
    assert text_similarity("one two", "one two three four") >= 1  # Exactly 50% gold-token coverage.
    assert text_similarity("F\u200b-35", "F-35") >= 1
    assert text_similarity("!!!", "???") == 0
    assert text_similarity("red blue", "tiger mountain") < 1


def test_report_includes_full_misses_and_safe_fences(registry, prediction):
    quote = registry.list2[0].text + " ``` ![untrusted](https://example.invalid)"
    gold = GoldCase(case_id="report", expected_color="yellow", triggers=(trigger(quote),))
    report = score_cases((gold,), (prediction("report"),), kind="format_contract")
    text = render_report(report)
    assert quote in text and "NOT SCANNER ACCURACY" in text
    assert "````text" in text and "L2-01" in text
    assert "## Where it fails" in text and "expected trigger(s) were not matched" in text
