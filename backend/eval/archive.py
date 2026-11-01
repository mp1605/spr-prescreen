"""Serve completed evaluation artifacts only; never start a run or open source datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from backend.eval.models import EvaluationReport
from backend.eval.split import case_ids


def evaluation_state(root: Path) -> Literal["deferred", "complete", "error"]:
    try:
        reports = (archived_report(root, "dev"), archived_report(root, "holdout"))
    except (OSError, ValueError):
        return "error"
    return "complete" if all(reports) else "deferred"


def archived_report(root: Path, split: Literal["dev", "holdout"]) -> EvaluationReport | None:
    folder = root / "reports/evaluation"
    path = folder / f"{split}.json"
    if not path.is_file():
        return None
    authorization = json.loads((folder / "authorization.json").read_text())
    if authorization.get("no_tuning") is not True or not authorization.get("scanner_fingerprint"):
        raise ValueError("Evaluation authorization/provenance is missing")
    if split == "holdout":
        ledger = json.loads((folder / "holdout-claim.json").read_text())
        if ledger.get("status") != "complete":
            return None
        if ledger.get("fingerprint") != authorization["scanner_fingerprint"]:
            raise ValueError("Holdout and evaluation fingerprints disagree")
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Evaluation report exceeds the archive size limit")
    report = EvaluationReport.model_validate_json(path.read_text())
    if (
        report.kind != "sponsor_evaluation"
        or {case.case_id for case in report.cases} != set(case_ids(split))
        or report.paper_count != len(case_ids(split))
    ):
        raise ValueError("Archived report is not a complete sponsor split")
    return report
