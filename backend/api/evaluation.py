"""Read-only scorecard artifacts. No dataset discovery, scoring, or key access."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException

from backend.core.policy import DISCLAIMER
from backend.core.rules_loader import StrictModel
from backend.eval.archive import archived_report
from backend.eval.models import EvaluationReport
from backend.eval.split import case_ids


class ScorecardStatus(StrictModel):
    split: Literal["dev", "holdout"]
    state: Literal["deferred", "complete"] = "deferred"
    sponsor_material_access: bool = False
    sponsor_accuracy_measured: bool = False
    report: EvaluationReport | None = None
    message: str = (
        "Sponsor evaluation is deferred until implementation is complete and separately "
        "authorized. No scorecard measurements are available."
    )
    disclaimer: str = DISCLAIMER
    release_decision: Literal["NOT_MADE_BY_TOOL"] = "NOT_MADE_BY_TOOL"


class DevelopmentScorecard(StrictModel):
    milestone: Literal["M13-development"] = "M13-development"
    split: Literal["dev"] = "dev"
    tuned_on_this_split: Literal[True] = True
    unseen_validation: Literal[False] = False
    holdout_reused: Literal[False] = False
    report: EvaluationReport
    disclaimer: str = DISCLAIMER
    release_decision: Literal["NOT_MADE_BY_TOOL"] = "NOT_MADE_BY_TOOL"


def evaluation_router(root: Path | None = None) -> APIRouter:
    router = APIRouter(prefix="/api/evaluation")

    @router.get("/development/latest", response_model=DevelopmentScorecard)
    def development() -> DevelopmentScorecard:
        if root is None or not (root / "reports/m13/final-dev.json").is_file():
            raise HTTPException(404, "No completed development-improvement report")
        try:
            path = root / "reports/m13/final-dev.json"
            if path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("Report too large")
            report = EvaluationReport.model_validate_json(path.read_bytes())
            if (
                report.kind != "sponsor_evaluation"
                or report.paper_count != 60
                or {case.case_id for case in report.cases} != set(case_ids("dev"))
            ):
                raise ValueError("Expected the complete development split")
        except (OSError, ValueError):
            raise HTTPException(503, "Development report is invalid or unavailable") from None
        return DevelopmentScorecard(report=report)

    @router.get("/scorecard/{split}", response_model=ScorecardStatus)
    def scorecard(split: Literal["dev", "holdout"]) -> ScorecardStatus:
        if root is not None:
            try:
                report = archived_report(root, split)
            except (OSError, ValueError):
                raise HTTPException(
                    503, "Stored evaluation report is invalid or unavailable"
                ) from None
            if report is not None:
                return ScorecardStatus(
                    split=split,
                    state="complete",
                    sponsor_material_access=True,
                    sponsor_accuracy_measured=True,
                    report=report,
                    message=(
                        "Separately authorized evaluation of the frozen scanner; no tuning. "
                        "E1 + E2 + specificity, AI off. "
                        "No separate cleared-paper corpus was supplied. "
                        "Policy-description mappings are disclosed in the evaluation report."
                    ),
                )
        return ScorecardStatus(split=split)

    return router
