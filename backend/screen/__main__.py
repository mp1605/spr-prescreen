"""Explicit-input batch screening; evaluation corpora are never discovered."""

from __future__ import annotations

import argparse
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from backend.cli_io import write_report
from backend.core.engines.ai import AIEngine
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.ingest_models import IngestLimits
from backend.core.policy import DISCLAIMER
from backend.core.rules_loader import PolicyError, load_rules
from backend.core.runtime import configure_offline_environment
from backend.core.screen import screen_document
from backend.core.settings import load_settings
from backend.core.specificity import SpecificityEngine
from backend.ingest.io import read_batch
from backend.version import CURRENT_MILESTONE


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local rules + semantic pre-screen. A reviewer makes the release decision."
    )
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--rules-only", action="store_true", help="Explicit E1 diagnostic baseline")
    parser.add_argument(
        "--no-ai", action="store_true", help="Skip optional AI for this explicit scan"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    try:
        rules = load_rules(root)
        engine = RulesEngine(rules)
        batch = read_batch(args.files, IngestLimits())
        settings = load_settings(root)
    except (PolicyError, ValueError) as exc:
        parser.error(str(exc))
    configure_offline_environment(root)
    semantic = (
        None
        if args.rules_only
        else SemanticEngine(root, rules, settings.semantic, cache=not args.no_cache)
    )
    ai = AIEngine(settings.ai) if not args.rules_only and not args.no_ai else None
    stage = "rules_only" if args.rules_only else "rules_semantic"
    specificity = None if args.rules_only else SpecificityEngine(root, rules)
    started = perf_counter()
    cache = None if args.no_cache else root / "runs/cache/parse"
    parsed = batch.parse(cache, args.workers)
    parse_seconds = perf_counter() - started
    rejected = tuple(document for document in parsed if document.status == "rejected")
    papers = tuple(
        screen_document(
            document,
            rules,
            engine=engine,
            semantic=semantic.session() if semantic else None,
            specificity=specificity,
            ai=ai.session() if ai else None,
        )
        for document in parsed
        if document.status != "rejected"
    )
    total_seconds = perf_counter() - started
    summary = {color: sum(p.color == color for p in papers) for color in ("green", "yellow", "red")}
    summary.update(
        incomplete=sum(bool(p.incomplete_pages or p.incomplete_reasons) for p in papers),
        rejected=len(rejected),
        unreadable_inputs=len(batch.input_errors),
    )
    stamp = datetime.now(UTC)
    output = (
        args.output
        or root / "runs" / f"screen-{stamp:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}" / "results.json"
    )
    used = {item for paper in papers for finding in paper.findings for item in finding.items}
    write_report(
        output,
        dict(
            milestone=CURRENT_MILESTONE,
            screening_stage=stage,
            created_utc=stamp.isoformat(),
            disclaimer=DISCLAIMER,
            release_decision="NOT_MADE_BY_TOOL",
            rules_version=rules.policy_version,
            rules_sha256=hashlib.sha256(
                (root / "policies/official_rules.yaml").read_bytes()
            ).hexdigest(),
            summary=summary,
            timing=dict(
                parse_batch_seconds=parse_seconds,
                total_seconds=total_seconds,
                paper_seconds_scope="rules stage only"
                if args.rules_only
                else (
                    "rules + semantic + fusion/specificity + optional AI, "
                    "including first-use model initialization"
                ),
            ),
            ai_configuration=ai.settings.model_dump(mode="json") if ai else None,
            semantic_configuration=settings.semantic.model_dump(mode="json") if semantic else None,
            limitations=[
                "Rules-only diagnostic baseline."
                if args.rules_only
                else "Semantic retrieval uses official wording only; thresholds are uncalibrated.",
                "List 2 uses source-bound specificity; judgment-dependent matches remain yellow."
                if specificity
                else "Rules-only baseline retains preliminary List 2 yellow.",
                "Sponsor evaluation has not been performed.",
            ],
            policy_items={
                item.id: item.text for item in (*rules.list1, *rules.list2) if item.id in used
            },
            papers=[paper.model_dump(mode="json") for paper in papers],
            rejected_inputs=[document.model_dump(mode="json") for document in rejected],
            input_errors=[error.model_dump(mode="json") for error in batch.input_errors],
        ),
    )
    print(
        f"Pre-screened {len(papers)} input(s): {summary['green']} green, "
        f"{summary['yellow']} yellow, {summary['red']} red. "
        f"Incomplete: {summary['incomplete']}; rejected: {summary['rejected']}; "
        f"unreadable: {summary['unreadable_inputs']}. "
        f"Flags: {sum(p.flag_count.total for p in papers)}."
    )
    return 2 if summary["incomplete"] or summary["rejected"] or summary["unreadable_inputs"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
