"""Explicit-file ingestion CLI. Never discovers or opens an evaluation corpus."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend.cli_io import write_report
from backend.core.ingest_models import PARSER_VERSION, IngestLimits
from backend.ingest.io import read_batch


def main() -> int:
    from backend.security.airlock import install_airlock

    install_airlock()
    parser = argparse.ArgumentParser(
        description="Parse explicit PDF/DOCX inputs locally. This does not screen or clear a paper."
    )
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--workers", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    limits = IngestLimits()
    try:
        batch = read_batch(args.files, limits)
    except ValueError as exc:
        parser.error(str(exc))
    input_errors = batch.input_errors
    root = Path(__file__).resolve().parents[2]
    cache = None if args.no_cache else root / "runs/cache/parse"
    results = batch.parse(cache, args.workers)
    summary = {
        state: sum(result.status == state for result in results)
        for state in ("complete", "incomplete", "rejected")
    }
    stamp = datetime.now(UTC)
    output = (
        args.output
        or root / "runs" / f"ingest-{stamp:%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}" / "parsed.json"
    )
    write_report(
        output,
        dict(
            parser_version=PARSER_VERSION,
            created_utc=stamp.isoformat(),
            screening_state="NOT_SCREENED",
            release_decision="NOT_MADE_BY_TOOL",
            summary=summary,
            documents=[result.model_dump(mode="json") for result in results],
            input_errors=[error.model_dump(mode="json") for error in input_errors],
        ),
    )
    print(
        f"Parsed {len(results)} input(s): {summary['complete']} complete, "
        f"{summary['incomplete']} incomplete, {summary['rejected']} rejected. "
        f"Unreadable inputs: {len(input_errors)}. "
        f"Segments: {sum(len(r.segments) for r in results)}. Screening not performed."
    )
    return 0 if not summary["incomplete"] and not summary["rejected"] and not input_errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
