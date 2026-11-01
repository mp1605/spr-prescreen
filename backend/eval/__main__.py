"""Harness commands. Dataset execution requires an explicit separate authorization flag."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from backend.cli_io import write_report, write_text_report
from backend.core.rules_loader import load_rules
from backend.core.settings import load_settings
from backend.eval.archive import archived_report
from backend.eval.report import deferred_report, render_report
from backend.eval.self_check import run_self_check


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Frozen evaluation harness; dataset execution requires explicit authorization."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser(
        "self-check", help="Run in-memory official-text format/math contracts"
    )
    check.add_argument("--output", type=Path)
    status = commands.add_parser(
        "status", help="Read archived evaluation status without opening datasets"
    )
    status.add_argument("--report", type=Path)
    status.add_argument("--archive-root", type=Path)
    run = commands.add_parser("run", help="Sponsor evaluation; locked during development")
    run.add_argument("--split", choices=("dev", "holdout"), default="dev")
    run.add_argument("--authorized-sponsor-evaluation", action="store_true")
    run.add_argument("--papers", type=Path)
    run.add_argument("--keys", type=Path)
    run.add_argument("--crosswalk", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    settings = load_settings(root)
    if args.command == "run":
        if args.authorized_sponsor_evaluation:
            if not all((args.papers, args.keys, args.crosswalk)):
                parser.error("Authorized evaluation requires --papers, --keys and --crosswalk")
            from backend.eval.runner import evaluate

            evaluate(root, args.papers, args.keys, args.crosswalk)
            return 0
        # Do not discover paths, read gold/predictions, create a ledger claim, or scan anything.
        if not settings.evaluation.sponsor_material_access:
            print(
                "DEFERRED: sponsor execution requires explicit authorization and source paths. "
                "No sponsor dataset files were opened."
            )
            return 2
    if args.command == "status":
        archive_root = args.archive_root or root
        reports = (archived_report(archive_root, "dev"), archived_report(archive_root, "holdout"))
        if any(reports):
            if args.report:
                write_text_report(args.report, "\n".join(render_report(r) for r in reports if r))
            print(
                json.dumps(
                    dict(
                        state="complete" if all(reports) else "partial",
                        sponsor_material_access=True,
                        sponsor_accuracy_measured=True,
                        harness_available=True,
                    )
                )
            )
            return 0
        if args.report:
            write_text_report(args.report, deferred_report())
        print(
            json.dumps(
                dict(
                    state="deferred",
                    sponsor_material_access=False,
                    sponsor_accuracy_measured=False,
                    harness_available=True,
                )
            )
        )
        return 0
    if args.command == "self-check":
        try:
            result = run_self_check(load_rules(root))
        except Exception:
            print("Harness self-check failed; inspect the test suite. No sponsor evaluation ran.")
            return 1
        if args.output:
            write_report(args.output, result)
        print(
            f"Harness contracts passed: {result['checks_passed']}. Sponsor accuracy not measured."
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
