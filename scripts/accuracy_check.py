"""Rescreen exposed sources with unchanged scoring; never claim unseen validation."""

import argparse
import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter

import yaml

from backend.cli_io import write_report, write_text_report
from backend.core.engines.local_bge import LocalBGE
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.ingest import parse_many
from backend.core.rules_loader import RuleRegistry, load_rules, load_yaml
from backend.core.runtime import configure_offline_environment
from backend.core.screen import screen_document
from backend.core.settings import load_settings
from backend.core.specificity import SpecificityEngine
from backend.eval.dataset import load_dataset
from backend.eval.models import PredictionCase
from backend.eval.report import render_report
from backend.eval.score import score_cases
from scripts.accuracy_patterns import candidate

ROOT = Path(__file__).resolve().parents[1]
CHAT = Path(
    "/Users/mpatel/Documents/Codex/2026-10-31/ground-rules-and-constraints-these-constraints"
)


def fingerprint():
    paths = list((ROOT / "backend/core").rglob("*.py"))
    paths += list((ROOT / "backend/eval").rglob("*.py"))
    paths += [
        ROOT / p
        for p in (
            "config/settings.yaml",
            "policies/official_rules.yaml",
            "policies/active.json",
            "docs/official-lists.pdf",
            "MASTER_PROMPT.md",
        )
    ]
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--active", action="store_true")
    args = parser.parse_args()
    configure_offline_environment(ROOT)
    before = fingerprint()
    base = ROOT / "reports/accuracy-v2"
    baseline = RuleRegistry.model_validate(load_yaml(base / "baseline/rules.yaml"))
    rules = load_rules(ROOT) if args.active else candidate(baseline)
    output = base / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True)
    previous = Path(json.loads((CHAT / "work/regression80-latest.json").read_text())["directory"])
    cache = base / "runtime-cache"
    if not cache.exists():
        shutil.copytree(previous / "runs/cache/semantic", cache / "runs/cache/semantic")
    source = Path("/Users/mpatel/Downloads/SPR Fake Papers with Triggers")
    dataset = load_dataset(
        source / "Tests",
        source / "Keys",
        ROOT / "reports/evaluation/rule-reference-crosswalk.json",
        rules,
    )
    original = json.loads((ROOT / "reports/evaluation/dataset.json").read_text())["inputs"]
    assert dataset.inventory == tuple(original), "Source hashes changed"
    documents = parse_many(dataset.papers, cache_directory=previous / "cache/parse", workers=2)
    semantic = SemanticEngine(cache, rules, load_settings(ROOT).semantic, provider=LocalBGE(ROOT))
    engine, specificity = RulesEngine(rules), SpecificityEngine(ROOT, rules)
    predictions = []
    started = perf_counter()
    for n, (doc, gold) in enumerate(zip(documents, dataset.gold, strict=True), 1):
        result = screen_document(
            doc,
            rules,
            engine=engine,
            semantic=semantic.session(),
            specificity=specificity,
            as_of=date(2026, 11, 1),
        )
        assert result.trace == ("list1:done", "list2:done")
        predictions.append(PredictionCase(case_id=gold.case_id, result=result))
        if n % 20 == 0:
            print(f"Actual rescreen {n}/80 · {perf_counter() - started:.1f}s", flush=True)
    report = score_cases(dataset.gold, tuple(predictions), kind="sponsor_evaluation")
    assert before == fingerprint(), "Scanner or scorer changed during execution"
    original_manifest = json.loads((ROOT / "reports/M12-evidence-manifest.json").read_text())
    assert all(
        hashlib.sha256((ROOT / v["path"]).read_bytes()).hexdigest() == v["sha256"]
        for v in original_manifest["artifacts"]
    ), "Original M12 evidence changed"
    write_report(output / "report.json", report.model_dump(mode="json"))
    write_report(output / "predictions.json", [p.model_dump(mode="json") for p in predictions])
    write_text_report(
        output / "report.md",
        "# Development on all 80 exposed papers\n\n"
        "This is not unseen validation. Original scoring and gold are unchanged.\n\n"
        + render_report(report),
    )
    write_text_report(
        output / "candidate-rules.yaml",
        yaml.safe_dump(rules.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
    )
    write_report(
        base / "latest.json", {"directory": str(output), "mode": "all80_exposed_development"}
    )
    write_report(
        output / "validation.json",
        {
            "mode": "all80_exposed_development",
            "unseen_validation": False,
            "tuned_on_these_80": True,
            "original_M12_preserved": True,
            "original_artifacts_verified": len(original_manifest["artifacts"]),
            "source_hashes_match_original": True,
            "scanner_and_scorer_stable_during_run": True,
            "scanner_hashes": before,
            "ai_enabled": False,
            "ollama_calls": 0,
            "paper_count": len(predictions),
            "docx": sum(d.file_type == "docx" for d in documents),
            "pdf": sum(d.file_type == "pdf" for d in documents),
            "gold_triggers": report.trigger_count,
            "all_lists_checked": all(
                p.result.trace == ("list1:done", "list2:done") for p in predictions
            ),
            "release_decisions": sorted({p.result.release_decision for p in predictions}),
            "vector_cache": {
                s: sum(p.result.semantic.cache_state == s for p in predictions)
                for s in ("hit", "miss", "unavailable")
            },
            "screen_and_checkpoint_seconds": perf_counter() - started,
            "timing_scope": (
                "Warm source-vector cache; excludes source/key preflight and model setup"
            ),
        },
    )
    print(json.dumps(report.model_dump(mode="json", exclude={"cases"})), flush=True)


if __name__ == "__main__":
    main()
