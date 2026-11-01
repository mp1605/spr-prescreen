"""Markdown reports keep missing measurements distinct from zero errors."""

from __future__ import annotations

import re

from backend.eval.models import EvaluationReport


def deferred_report() -> str:
    return """# Sponsor evaluation — NOT PERFORMED

Sponsor papers, answer keys, and expected results have not been opened or scored.
The user's blind-build instruction defers evaluation until implementation is complete.

The evaluation harness is implemented and tested using official text and format/math
contracts only. Those checks are not scanner-performance measurements.

| Measurement | Result |
| --- | --- |
| Sponsor trigger recall | Not measured |
| Sponsor paper-color accuracy | Not measured |
| Sponsor false alarms / decoy hits | Not measured |
| Sponsor development/holdout runs | Not performed |

The run command remains locked before dataset access. No gold dataset or fabricated
development scorecard is produced. A reviewer makes every release decision.
"""


def _rate(value: float | None) -> str:
    return "Not defined (no eligible observations)" if value is None else f"{value:.2%}"


def _quoted(text: str) -> str:
    longest = max((len(m[0]) for m in re.finditer(r"`+", text)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}text\n{text}\n{fence}"


def render_report(report: EvaluationReport) -> str:
    title = (
        "Format-contract score — NOT SCANNER ACCURACY"
        if report.kind == "format_contract"
        else "Security and Policy Review — evaluation results"
    )
    rows = [
        f"# {title}",
        "",
        "Pre-screen only — a reviewer makes the release decision.",
        "",
        f"Papers: {report.paper_count}; triggers: {report.trigger_count}; "
        f"matched: {report.matched_triggers}.",
        "",
        "| Metric | Value |",
        "| --- | --- |",
    ]
    for label, value in (
        ("Trigger recall", report.trigger_recall),
        ("List 1 recall", report.list1_recall),
        ("List 2 recall", report.list2_recall),
        ("Matched-item micro Jaccard", report.item_accuracy),
        ("Matched flag-color accuracy", report.flag_color_accuracy),
        ("Paper-color accuracy", report.paper_color_accuracy),
        ("Decoy flag rate", report.decoy_flag_rate),
    ):
        rows.append(f"| {label} | {_rate(value)} |")
    rows += [
        "",
        f"False alarms: {report.false_alarms}; decoys flagged: "
        f"{report.decoys_flagged}/{report.decoy_count}; "
        f"incomplete papers: {report.incomplete_papers}.",
        "Reference-paper false alarms: "
        + (
            str(report.false_alarms_on_reference_papers)
            if report.reference_paper_count
            else "Not measured (no reference papers)"
        )
        + "; "
        f"green test/reference papers with findings: {report.greens_wrongly_flagged}.",
        f"Weighted cost: {report.weighted_cost}. {report.cost_assumption}.",
        "",
        "Confusion matrix: rows are expected, columns are predicted.",
        "",
        "| Expected / predicted | Green | Yellow | Red |",
        "| --- | --- | --- | --- |",
    ]
    for color, values in report.confusion.items():
        rows.append(f"| {color} | {values['green']} | {values['yellow']} | {values['red']} |")
    rows += ["", "Matching policy:", _quoted(report.matching_policy), "", "## Missed triggers", ""]
    for case in report.cases:
        for trigger in case.missed:
            rows.append(
                _quoted(
                    f"{case.case_id} / {trigger.tag} / {', '.join(trigger.items)}\n"
                    f"{trigger.quote}\nReason: {trigger.reason}"
                )
            )
    if not any(case.missed for case in report.cases):
        rows.append("No missed triggers in this evaluated input set.")
    rows += ["", "## Decoy hits and unmatched findings", ""]
    for case in report.cases:
        for decoy in case.decoy_hits:
            rows.append(_quoted(f"{case.case_id} / decoy\n{decoy}"))
        for passage in case.false_alarms:
            rows.append(
                _quoted(
                    f"{case.case_id} / unmatched finding / {', '.join(passage.items)}\n"
                    f"{passage.quote}"
                )
            )
    misses = report.trigger_count - report.matched_triggers
    failures = []
    if misses:
        failures.append(f"{misses} expected trigger(s) were not matched.")
    if report.false_alarms:
        failures.append(f"{report.false_alarms} predicted passage(s) had no matching trigger.")
    if report.item_accuracy is not None and report.item_accuracy < 1:
        failures.append("Some matched passages have missing or extra official item IDs.")
    if report.flag_color_accuracy is not None and report.flag_color_accuracy < 1:
        failures.append("Some matched flags have the wrong red/yellow label.")
    if report.paper_color_accuracy < 1:
        failures.append("Some paper colors disagree with the supplied reference labels.")
    if report.incomplete_papers:
        failures.append(f"{report.incomplete_papers} paper(s) were incompletely processed.")
    rows += ["", "## Where it fails", ""]
    rows.extend(f"- {failure}" for failure in failures)
    if not failures:
        rows.append("No failures observed in this input set; this says nothing about other inputs.")
    rows += [
        "",
        "## Timing and limits",
        "",
        f"AI off seconds/paper: {report.seconds_per_paper_ai_off}; "
        f"AI attempted seconds/paper: {report.seconds_per_paper_ai_on}.",
        "Timing inherits the scope recorded by the screening run; it is not a new benchmark.",
        "Rates are undefined when their denominators are empty. List-specific recall requires "
        "agreement on an item from that list. Identical cross-list evidence is one passage.",
        "Keyword/topic applicability and unusual document layouts still require human review.",
    ]
    return "\n".join(rows) + "\n"
