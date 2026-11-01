"""Pure metric calculation. Missing/extra cases fail instead of improving a denominator."""

from __future__ import annotations

from statistics import mean
from typing import Literal

from backend.eval.matching import grouped_passages, match_passages, text_similarity
from backend.eval.models import CaseScore, EvaluationReport, GoldCase, PredictionCase


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def score_cases(
    gold: tuple[GoldCase, ...],
    predictions: tuple[PredictionCase, ...],
    *,
    kind: Literal["format_contract", "sponsor_evaluation"],
) -> EvaluationReport:
    targets = {case.case_id: case for case in gold}
    actual = {case.case_id: case.result for case in predictions}
    if not gold or len(targets) != len(gold) or len(actual) != len(predictions):
        raise ValueError("Evaluation requires nonempty unique gold and prediction case IDs")
    if targets.keys() != actual.keys():
        raise ValueError(
            "Gold and prediction case sets must agree exactly; missing/extra results exist"
        )
    confusion = {
        color: dict.fromkeys(("green", "yellow", "red"), 0) for color in ("green", "yellow", "red")
    }
    cases: list[CaseScore] = []
    list_totals = {"L1-": 0, "L2-": 0}
    list_matches = {"L1-": 0, "L2-": 0}
    matched_count = correct_color = intersection = union = 0
    false_count = green_flags = decoy_total = decoy_hits = reference_false = 0
    for case in gold:
        result = actual[case.case_id]
        if case.paper_id is not None and case.paper_id != result.paper_id:
            raise ValueError("Gold and prediction source SHA-256 identities disagree")
        passages = grouped_passages(result.findings)
        matches = match_passages(passages, case.triggers)
        matched_count += len(matches)
        for prefix in list_totals:
            list_totals[prefix] += sum(
                any(i.startswith(prefix) for i in t.items) for t in case.triggers
            )
        for target, predicted in matches.items():
            trigger, passage = case.triggers[target], passages[predicted]
            agreement = set(trigger.items) & set(passage.items)
            intersection += len(agreement)
            union += len(set(trigger.items) | set(passage.items))
            correct_color += passage.color == trigger.color
            for prefix in list_matches:
                list_matches[prefix] += any(item.startswith(prefix) for item in agreement)
        misses = tuple(t for n, t in enumerate(case.triggers) if n not in matches)
        false = tuple(p for n, p in enumerate(passages) if n not in matches.values())
        decoys = tuple(
            d for d in case.decoys if any(text_similarity(p.quote, d) >= 1 for p in passages)
        )
        false_count += len(false)
        decoy_total += len(case.decoys)
        decoy_hits += len(decoys)
        green_flags += case.expected_color == "green" and bool(passages)
        reference_false += len(false) if case.reference_good else 0
        confusion[case.expected_color][result.color] += 1
        cases.append(
            CaseScore(
                case_id=case.case_id,
                expected_color=case.expected_color,
                actual_color=result.color,
                trigger_count=len(case.triggers),
                matched_count=len(matches),
                false_alarms=false,
                missed=misses,
                decoy_hits=decoys,
                matches=tuple(
                    (case.triggers[t].tag, passages[p].finding_ids)
                    for t, p in sorted(matches.items())
                ),
            )
        )
    total = sum(len(case.triggers) for case in gold)
    off = [r.seconds for r in actual.values() if r.ai_state == "off"]
    on = [r.seconds for r in actual.values() if r.ai_state != "off"]
    return EvaluationReport(
        kind=kind,
        paper_count=len(gold),
        trigger_count=total,
        matched_triggers=matched_count,
        trigger_recall=_ratio(matched_count, total),
        list1_recall=_ratio(list_matches["L1-"], list_totals["L1-"]),
        list2_recall=_ratio(list_matches["L2-"], list_totals["L2-"]),
        list1_trigger_count=list_totals["L1-"],
        list2_trigger_count=list_totals["L2-"],
        item_accuracy=_ratio(intersection, union),
        flag_color_accuracy=_ratio(correct_color, matched_count),
        paper_color_accuracy=sum(case.expected_color == actual[case.case_id].color for case in gold)
        / len(gold),
        confusion=confusion,
        false_alarms=false_count,
        greens_wrongly_flagged=green_flags,
        decoy_count=decoy_total,
        decoys_flagged=decoy_hits,
        decoy_flag_rate=_ratio(decoy_hits, decoy_total),
        false_alarms_on_reference_papers=reference_false,
        reference_paper_count=sum(case.reference_good for case in gold),
        incomplete_papers=sum(
            bool(r.incomplete_pages or r.incomplete_reasons) for r in actual.values()
        ),
        seconds_per_paper_ai_off=mean(off) if off else None,
        seconds_per_paper_ai_on=mean(on) if on else None,
        weighted_cost=3 * (total - matched_count) + false_count,
        rules_versions=tuple(sorted({r.rules_version for r in actual.values()})),
        cases=tuple(cases),
        matching_policy=(
            "One-to-one maximum-cardinality passage matching; official-ID agreement plus "
            "multiset gold-token coverage ≥50% OR normalized partial ratio ≥80%. "
            "Identical cross-list evidence is grouped. Item accuracy is matched-pair micro Jaccard."
        ),
    )
