"""Publish saved evaluation evidence. This command never reruns screening or holdout."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from backend.cli_io import write_report, write_text_report
from backend.eval.frozen import verify_frozen_scanner
from backend.eval.io import parse_gold_jsonl
from backend.eval.models import EvaluationReport, PredictionCase
from backend.eval.report import render_report

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    folder = ROOT / "reports/evaluation"
    fingerprint = verify_frozen_scanner(ROOT)
    reports = {
        split: EvaluationReport.model_validate_json((folder / f"{split}.json").read_bytes())
        for split in ("dev-rules-only", "dev", "holdout", "combined")
    }
    timing = json.loads((folder / "timing.json").read_text())
    gold = parse_gold_jsonl((folder / "gold.jsonl").read_text())
    raw = {
        case.case_id: PredictionCase.model_validate_json(
            (folder / "predictions" / f"{case.case_id}.json").read_bytes()
        ).result
        for case in gold
    }
    coverage = []
    engines: Counter[str] = Counter()
    scores = {case.case_id: case for case in reports["combined"].cases}
    for case in gold:
        findings = {f.finding_id: f for f in raw[case.case_id].findings}
        matches = dict(scores[case.case_id].matches)
        for trigger in case.triggers:
            selected = matches.get(trigger.tag, ())
            actual = {item for ident in selected for item in findings[ident].items}
            coverage.append(
                dict(
                    case_id=case.case_id,
                    tag=trigger.tag,
                    quote=trigger.quote,
                    expected_items=trigger.items,
                    matched_items=sorted(actual),
                    missing_items=sorted(set(trigger.items) - actual),
                    missing_lists=[
                        prefix
                        for prefix in ("L1-", "L2-")
                        if any(i.startswith(prefix) for i in trigger.items)
                        and not any(i.startswith(prefix) for i in actual & set(trigger.items))
                    ],
                )
            )
        for passage in scores[case.case_id].false_alarms:
            names = {engine for ident in passage.finding_ids for engine in findings[ident].engines}
            engines[" + ".join(sorted(names))] += 1
    write_report(folder / "item-coverage.json", coverage)
    sizes = timing["files"]
    table = ["| Measurement | Dev | Holdout | Combined |", "| --- | ---: | ---: | ---: |"]
    for label, field, percentage in (
        ("Papers", "paper_count", False),
        ("Expected triggers", "trigger_count", False),
        ("Matched triggers", "matched_triggers", False),
        ("Recall", "trigger_recall", True),
        ("List 1 recall", "list1_recall", True),
        ("List 2 recall", "list2_recall", True),
        ("Paper-color accuracy", "paper_color_accuracy", True),
        ("Matched flag-color accuracy", "flag_color_accuracy", True),
        ("Matched-item micro Jaccard", "item_accuracy", True),
        ("Unmatched passages", "false_alarms", False),
        ("Green papers with findings", "greens_wrongly_flagged", False),
    ):
        values = [getattr(reports[s], field) for s in ("dev", "holdout", "combined")]
        formatted = [f"{v:.1%}" if percentage else str(v) for v in values]
        table.append(f"| {label} | " + " | ".join(formatted) + " |")
    summary = (
        """# M12 — frozen scanner evaluation

The software evaluation completed; **accuracy targets were not met**. This build needs
substantial detection/precision work before it can be relied on to prioritize SPR review.
The tool never clears a paper. Pre-screen only — a reviewer makes the release decision.

## Authorization and freeze

On 1 November 2026 the user explicitly authorized a separate M12 evaluation, with no tuning.
The scanner had been built blind. All scanner/core/security source, active policies,
official guide and settings still match the pre-evaluation M11 manifest. Evaluation-only
readers, artifact APIs and scorecard presentation were extended; detectors, thresholds,
models and exemplars were not changed. AI remained off and no Ollama call was made.
The fixed 60/20 split was used. Holdout was claimed once and completed once; the claim
refuses another run. Rendering or rereading stored reports does not run inference again.

## Inputs and ground-truth interpretation

The supplied folder contained 80 canonical papers (60 DOCX, 20 PDF), 80 canonical keys,
four suffixed duplicate keys and an INDEX.csv. Only canonical keys were used; INDEX.csv
was not read. The keys yielded 99 triggers, six primary quoted decoys, and expected colors
20 green / 25 yellow / 35 red. All 99 gold quotations occur in their source papers after
whitespace/punctuation normalization. No source parsed as incomplete.

The key tables mostly describe policies instead of giving official IDs. The disclosed
80-entry `evaluation/rule-reference-crosswalk.json` maps those descriptions to unchanged
official items. It was reviewed before predictions were scored, using the answer-table
descriptions, without using predictions. Short descriptions such as readiness,
vulnerabilities, decision authority and dependencies require interpretation; item-dependent
metrics are conditional on that crosswalk. This is evaluation data, never scanner rules
or an exemplar bank. Primary quoted decoys exclude explanatory text after the closing quote.
Strict parsing initially rejected these formats; only the evaluation reader was corrected.

The supplied folder contains no separate real cleared/reference corpus. Its false-alarm
rate is **not measured**. The 20 green test papers are measured separately below; a stored
zero reference-paper count must not be interpreted as zero false alarms on cleared papers.

## Measured results

"""
        + "\n".join(table)
        + "\n\n"
    )
    summary += (
        "Dev matched 42/74 triggers and missed 32. Holdout matched 15/25 and missed 10. "
        "Overall, 57/99 matched and 42 were missed. List-specific denominators overlap "
        "when a trigger names both lists: 31 List 1 and 79 List 2 triggers. List 1-specific "
        "recall was 18/31; List 2-specific recall was 41/79.\n\n"
        "All 20 green papers were flagged: 18 red and two yellow. Six declared decoys "
        "occurred in dev; one was flagged. Holdout contained no declared decoys, so its "
        "decoy rate is undefined. The targets of zero dev List 1 misses, at least 90% "
        "holdout recall, at least 80% paper-color accuracy, and zero decoy hits were not met.\n\n"
        "The current E1-only dev baseline (with current specificity) matched 37/74 (50.0%), "
        "versus 42/74 (56.8%) with E2: five additional matches. Unmatched dev passages rose "
        "from 113 to 733, and paper-color accuracy fell from 48.3% to 46.7%. This is a "
        "baseline measured now, not an earlier M3 sponsor measurement.\n\n"
        "Unmatched passages are counted as false alarms under the supplied keys. They "
        "can also reflect one-to-one passage granularity or an unseeded policy concern; "
        "they have not all been adjudicated by a human. Passing software tests establishes "
        "implementation checks, not these accuracy targets.\n\n## Timing\n\n"
    )
    summary += (
        f"Parsing: {timing['parse_seconds']:.2f} s; shared BGE/specificity setup: "
        f"{timing['model_and_specificity_setup_seconds']:.2f} s; evaluation loop: "
        f"{timing['evaluation_loop_seconds']:.2f} s. The loop includes the dev E1 baseline, "
        "checkpoint writes and report generation. Key preflight/import time is excluded.\n\n"
        "Saved E1+E2 paper screening averaged "
        f"{reports['combined'].seconds_per_paper_ai_off:.3f} s "
        f"per paper, excluding parse/setup. These 80 inputs contain "
        f"{sum(f['screening_words'] for f in sizes):,} extracted screening words "
        f"({min(f['screening_words'] for f in sizes)}–{max(f['screening_words'] for f in sizes)} "
        "per file; mean 562.1). The 20 PDFs have 40 pages total. DOCX paragraph extraction "
        "does not determine rendered page count. AI-on timing/accuracy was not measured.\n\n"
        "These are CPU BGE embedding plus rules/specificity timings, not local LLM latency "
        "and not the agent's implementation/test/browser-tool time.\n\n## Where it fails\n\n"
        "- Recall remains low, including List 1 triggers that must not be missed.\n"
        "- The semantic engine adds many unmatched candidates and drives benign test papers red.\n"
        "- Red/yellow labels often disagree with the keys, even for matched triggers.\n"
        "- Several matched passages have missing or extra policy IDs.\n"
        "- Uncalibrated retrieval and broad pattern coverage require later development work. "
        "This evaluation was not used to modify them.\n\n"
        f"Engine provenance of the 1,026 unmatched passages: {dict(engines)}. This count "
        "locates candidate sources; it is not a causal audit of every false alarm.\n\n"
        "## Detailed evidence\n\n"
        "`TEST_REPORT.md` contains both split summaries, the combined confusion matrix, "
        "all 42 globally missed triggers quoted with IDs/reasons, every declared decoy hit, "
        "all unmatched passages, and a list-specific miss appendix. Saved predictions, "
        "gold source hashes, crosswalk, input sizes and the holdout ledger remain under "
        "`reports/evaluation/`. No holdout rerun is permitted by the runner.\n\n"
        f"Frozen scanner fingerprint: `{fingerprint}`.\n\n"
        "M10 physical network-disconnection and different-Mac checks, and a full Chrome "
        "Lighthouse navigation run, remain unverified. The historical M10 ZIP is unchanged.\n"
    )
    write_text_report(ROOT / "reports/M12_EVALUATION_REPORT.md", summary)
    detailed = summary + "\n\n" + render_report(reports["combined"])
    detailed += "\n## List-specific missed-trigger evidence\n\n"
    for record in coverage:
        if record["missing_lists"]:
            detailed += (
                f"### {record['case_id']} / {record['tag']}\n\n"
                f"No matching item from: {', '.join(record['missing_lists'])}. "
                f"Expected IDs: {', '.join(record['expected_items'])}.\n\n"
                + "\n".join("> " + line for line in record["quote"].splitlines())
                + "\n\n"
            )
    write_text_report(ROOT / "reports/TEST_REPORT.md", detailed)
    print("Published saved M12 reports; no scanner execution or holdout rerun.")


if __name__ == "__main__":
    main()
