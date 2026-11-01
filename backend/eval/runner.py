"""Authorized, frozen E1/E2 evaluation. Keys are used only by the evaluator."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from time import perf_counter

from backend.cli_io import write_report, write_text_report
from backend.core.engines.local_bge import LocalBGE
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.ingest import parse_many
from backend.core.rules_loader import load_rules
from backend.core.runtime import configure_offline_environment
from backend.core.screen import screen_document
from backend.core.settings import load_settings
from backend.core.specificity import SpecificityEngine
from backend.eval.dataset import load_dataset, select_gold
from backend.eval.frozen import verify_frozen_scanner
from backend.eval.io import write_gold_jsonl
from backend.eval.ledger import claim_holdout, finish_holdout
from backend.eval.models import PredictionCase
from backend.eval.report import render_report
from backend.eval.score import score_cases
from backend.eval.split import case_ids


def evaluate(root: Path, papers: Path, keys: Path, crosswalk: Path) -> None:
    configure_offline_environment(root)
    fingerprint = verify_frozen_scanner(root)
    output = root / "reports/evaluation"
    if any((output / name).exists() for name in ("dev.json", "holdout-claim.json")):
        raise ValueError("Evaluation output already claimed; existing evidence is not overwritten")
    rules, settings = load_rules(root), load_settings(root)
    dataset = load_dataset(papers, keys, crosswalk, rules)
    write_gold_jsonl(output / "gold.jsonl", dataset.gold)
    write_report(
        output / "authorization.json",
        dict(
            authorized_utc=datetime.now(UTC).isoformat(),
            scanner_fingerprint=fingerprint,
            source="Explicit user authorization in chat, 1 November 2026",
            papers=str(papers),
            keys=str(keys),
            no_tuning=True,
            ai_enabled=False,
        ),
    )
    write_report(
        output / "dataset.json",
        dict(
            inputs=dataset.inventory,
            ignored_keys=dataset.ignored_keys,
            triggers=sum(len(c.triggers) for c in dataset.gold),
            decoys=sum(len(c.decoys) for c in dataset.gold),
            reference_papers=0,
            reference_note="Supplied folder contains Tests and Keys only; no cleared corpus.",
        ),
    )
    started = perf_counter()
    parsed = parse_many(dataset.papers, cache_directory=output / "cache/parse", workers=2)
    parse_seconds = perf_counter() - started
    docs = {source.file_name.rsplit(".", 1)[0]: source for source in parsed}
    print(
        f"Parsed {len(parsed)}/80 papers; {sum(d.status != 'complete' for d in parsed)} incomplete",
        flush=True,
    )
    started = perf_counter()
    provider = LocalBGE(root)
    specificity = SpecificityEngine(root, rules)
    setup_seconds = perf_counter() - started
    semantic = SemanticEngine(output, rules, settings.semantic, provider=provider)
    engine = RulesEngine(rules)
    predictions: dict[str, tuple[PredictionCase, ...]] = {}
    total_started = perf_counter()
    for split in ("dev", "holdout"):
        verify_frozen_scanner(root)
        if split == "holdout":
            claim_holdout(output, fingerprint)
        succeeded = False
        try:
            results: list[PredictionCase] = []
            baseline: list[PredictionCase] = []
            for index, case_id in enumerate(case_ids(split), 1):
                document = docs[case_id]
                if split == "dev":
                    baseline.append(
                        PredictionCase(
                            case_id=case_id,
                            result=screen_document(
                                document,
                                rules,
                                engine=engine,
                                specificity=specificity,
                                as_of=date(2026, 11, 1),
                            ),
                        )
                    )
                result = screen_document(
                    document,
                    rules,
                    engine=engine,
                    semantic=semantic.session(),
                    specificity=specificity,
                    as_of=date(2026, 11, 1),
                )
                prediction = PredictionCase(case_id=case_id, result=result)
                results.append(prediction)
                # Durable per-paper checkpoint. Logs deliberately contain no source text.
                write_report(
                    output / "predictions" / f"{case_id}.json", prediction.model_dump(mode="json")
                )
                print(
                    f"{split}: {index}/{len(case_ids(split))} · {case_id} · "
                    f"{result.seconds:.2f}s · {result.flag_count.total} flags",
                    flush=True,
                )
            gold = select_gold(dataset, split)
            report = score_cases(gold, tuple(results), kind="sponsor_evaluation")
            write_report(output / f"{split}.json", report.model_dump(mode="json"))
            write_text_report(output / f"{split}.md", render_report(report))
            if baseline:
                base_report = score_cases(gold, tuple(baseline), kind="sponsor_evaluation")
                write_report(output / "dev-rules-only.json", base_report.model_dump(mode="json"))
            predictions[split] = tuple(results)
            succeeded = True
        finally:
            if split == "holdout":
                finish_holdout(output, fingerprint, succeeded=succeeded)
    final = tuple(p for values in predictions.values() for p in values)
    combined = score_cases(dataset.gold, final, kind="sponsor_evaluation")
    write_report(output / "combined.json", combined.model_dump(mode="json"))
    write_text_report(output / "combined.md", render_report(combined))
    write_report(
        output / "timing.json",
        dict(
            parse_seconds=parse_seconds,
            model_and_specificity_setup_seconds=setup_seconds,
            evaluation_loop_seconds=perf_counter() - total_started,
            ai_enabled=False,
            as_of="2026-11-01",
            scanner_fingerprint=fingerprint,
            files=[
                dict(
                    case_id=case_id,
                    file_type=d.file_type,
                    bytes=d.byte_count,
                    pdf_pages=max((u.page or 0 for u in d.units), default=0) or None,
                    word_paragraphs=sum(u.paragraph is not None for u in d.units) or None,
                    screening_words=sum(len(s.text.split()) for s in d.segments),
                    segments=len(d.segments),
                )
                for case_id, d in docs.items()
            ],
            timing_note=(
                "PaperResult seconds exclude parsing and shared model setup; loop includes "
                "dev E1 baseline, checkpoint/report writes. AI not attempted."
            ),
        ),
    )
    verify_frozen_scanner(root)
    print("Completed dev and one holdout pass; frozen scanner verified unchanged.", flush=True)
