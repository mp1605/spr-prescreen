"""Development-only measurement. Never opens or evaluates holdout papers/keys."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path

import yaml

from backend.cli_io import write_report, write_text_report
from backend.core.engines.local_bge import LocalBGE
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.ingest import parse_document
from backend.core.rules_loader import RuleRegistry, load_rules, load_yaml
from backend.core.screen import screen_document
from backend.core.settings import load_settings
from backend.core.specificity import SpecificityEngine
from backend.eval.key_format import KeyTable
from backend.eval.models import PredictionCase
from backend.eval.parse_keys import parse_blocks
from backend.eval.read_docx import read_docx
from backend.eval.read_pdf import read_pdf
from backend.eval.report import render_report
from backend.eval.score import score_cases
from backend.eval.split import case_ids
from scripts.m13_patterns import candidate

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/mpatel/Downloads/SPR Fake Papers with Triggers")


def development_inputs(registry, output):
    crosswalk = {
        v["reference"]: v["items"]
        for v in json.loads(
            (ROOT / "reports/evaluation/rule-reference-crosswalk.json").read_text()
        )["references"]
    }
    documents, gold = [], []
    for case_id in case_ids("dev"):
        papers = [SOURCE / "Tests" / f"{case_id}.{ext}" for ext in ("docx", "pdf")]
        keys = [SOURCE / "Keys" / f"{case_id}_KEY.{ext}" for ext in ("docx", "pdf")]
        paper = next(p for p in papers if p.is_file())
        key = next(p for p in keys if p.is_file())
        data = key.read_bytes()
        blocks = read_docx(data) if key.suffix == ".docx" else read_pdf(data)
        mapped = []
        for block in blocks:
            if isinstance(block, KeyTable):
                block = KeyTable(
                    tuple(
                        (row[0], "; ".join(crosswalk[row[1]]), *row[2:])
                        if len(row) == 4 and row[1] in crosswalk
                        else row
                        for row in block.rows
                    ),
                    block.paragraphs,
                )
            mapped.append(block)
        parsed = parse_document(paper.name, paper.read_bytes(), cache_directory=output / "parse")
        documents.append(parsed)
        target = parse_blocks(
            tuple(mapped),
            case_id=case_id,
            registry=registry,
            source_sha256=hashlib.sha256(data).hexdigest(),
        )
        gold.append(target.model_copy(update={"paper_id": parsed.paper_id}))
    return documents, tuple(gold)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active", action="store_true")
    parser.add_argument("--thresholds", default="0.76,0.80,0.84")
    args = parser.parse_args()
    output = ROOT / "reports/m13"
    output.mkdir(parents=True, exist_ok=True)
    active = load_rules(ROOT)
    baseline = RuleRegistry.model_validate(
        load_yaml(ROOT / "reports/m13/baseline-source/policies/official_rules.yaml")
    )
    rules = active if args.active else candidate(baseline)
    if not args.active:
        write_text_report(
            output / "candidate-rules.yaml",
            yaml.safe_dump(rules.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        )
    documents, gold = development_inputs(rules, output)
    assert len(gold) == 60 and sum(len(c.triggers) for c in gold) == 74
    settings = load_settings(ROOT)
    provider = LocalBGE(ROOT)
    specificity = SpecificityEngine(ROOT, rules)
    engine = RulesEngine(rules)
    summary = []
    for threshold in map(float, args.thresholds.split(",")):
        semantic = SemanticEngine(
            output,
            rules,
            settings.semantic.model_copy(
                update={
                    "mid_threshold": threshold,
                    "high_threshold": max(0.86, threshold + 0.01),
                }
            ),
            provider=provider,
        )
        predictions = []
        for n, (doc, target) in enumerate(zip(documents, gold, strict=True), 1):
            result = screen_document(
                doc,
                rules,
                engine=engine,
                semantic=semantic.session(),
                specificity=specificity,
                as_of=date(2026, 11, 1),
            )
            predictions.append(PredictionCase(case_id=target.case_id, result=result))
            if n % 15 == 0:
                print(f"Dev threshold {threshold}: {n}/60", flush=True)
        report = score_cases(gold, tuple(predictions), kind="sponsor_evaluation")
        label = ("active" if args.active else "candidate") + f"-{threshold:.2f}"
        write_report(output / f"{label}.json", report.model_dump(mode="json"))
        write_text_report(output / f"{label}.md", render_report(report))
        write_report(
            output / f"{label}-predictions.json", [p.model_dump(mode="json") for p in predictions]
        )
        row = {
            "profile": label,
            "recall": report.trigger_recall,
            "list1": report.list1_recall,
            "color": report.paper_color_accuracy,
            "false_alarms": report.false_alarms,
            "greens_flagged": report.greens_wrongly_flagged,
            "cost": report.weighted_cost,
        }
        summary.append(row)
        print(json.dumps(row), flush=True)
    write_report(output / "latest-summary.json", summary)


if __name__ == "__main__":
    main()
