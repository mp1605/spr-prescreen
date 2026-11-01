from __future__ import annotations

import platform
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from backend.core.assets import AssetStatus, model_status
from backend.core.batch import BatchService
from backend.core.offline_status import OfflineStatus, offline_status
from backend.core.policy import DISCLAIMER
from backend.core.rules_loader import RuleRegistry, StrictModel
from backend.core.settings import Settings
from backend.eval.archive import evaluation_state
from backend.security.airlock import airlock_status
from backend.version import CURRENT_MILESTONE


class Health(StrictModel):
    status: Literal["ok"] = "ok"
    milestone: Literal["M12"] = CURRENT_MILESTONE
    color_stage: Literal["specificity-v1"] = "specificity-v1"
    evaluation_harness_available: Literal[True] = True
    sponsor_evaluation_state: Literal["deferred", "complete", "error"] = "deferred"
    ingestion_available: Literal[True] = True
    screening_available: Literal[True] = True
    screening_stage: Literal["rules_semantic"] = "rules_semantic"
    rules_version: str
    list1_count: int
    list2_count: int
    detector_count: int
    disclaimer: str = DISCLAIMER
    release_decision: Literal["NOT_MADE_BY_TOOL"] = "NOT_MADE_BY_TOOL"


class SystemStatus(StrictModel):
    bind: str
    python: str
    models: AssetStatus
    ai_enabled: bool
    rules_detectors: int
    semantic_enabled: Literal[True] = True
    semantic_state: str
    semantic_model: str
    semantic_reference_source: Literal["official_rules_only"] = "official_rules_only"
    semantic_reference_count: Literal[39] = 39
    semantic_reference_digest: str
    semantic_mid_threshold: float
    semantic_high_threshold: float
    feedback_usage: Literal["excluded_during_blind_build"] = "excluded_during_blind_build"
    evaluation_mode: Literal["blind"] = "blind"
    sponsor_material_access: bool = False
    evaluation_harness_available: Literal[True] = True
    sponsor_evaluation_state: Literal["deferred", "complete", "error"] = "deferred"
    semantic_calibrated: Literal[False] = False
    airlock_installed: bool = False
    specificity_enabled: Literal[True] = True
    specificity_version: Literal["specificity-v1"] = "specificity-v1"
    specificity_policy_digest: str
    optional_entity_model_state: str


def system_router(
    root: Path,
    settings: Settings,
    service: BatchService,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health", response_model=Health)
    def health() -> Health:
        rules = service.rules
        return Health(
            sponsor_evaluation_state=evaluation_state(root),
            rules_version=rules.policy_version,
            list1_count=len(rules.list1),
            list2_count=len(rules.list2),
            detector_count=sum(len(item.detectors) for item in (*rules.list1, *rules.list2)),
        )

    @router.get("/rules", response_model=RuleRegistry)
    def policy_rules() -> RuleRegistry:
        return service.rules

    @router.get("/rules/source")
    def policy_source() -> FileResponse:
        return FileResponse(root / service.rules.source_document, media_type="application/pdf")

    @router.get("/system", response_model=SystemStatus)
    def system() -> SystemStatus:
        rules, semantic, specificity = service.rules, service.semantic, service.specificity
        assert semantic is not None and specificity is not None
        return SystemStatus(
            sponsor_evaluation_state=evaluation_state(root),
            sponsor_material_access=(root / "reports/evaluation/authorization.json").is_file(),
            bind=f"{settings.host}:{settings.port}",
            python=platform.python_version(),
            models=model_status(root),
            ai_enabled=service.ai.settings.enabled if service.ai else False,
            airlock_installed=airlock_status()[0],
            rules_detectors=sum(len(item.detectors) for item in (*rules.list1, *rules.list2)),
            semantic_state=semantic.state,
            semantic_model=settings.semantic.model,
            semantic_reference_digest=semantic.reference_digest,
            semantic_mid_threshold=settings.semantic.mid_threshold,
            semantic_high_threshold=settings.semantic.high_threshold,
            specificity_policy_digest=specificity.policy_digest,
            optional_entity_model_state=specificity.ner_state,
        )

    @router.get("/system/offline", response_model=OfflineStatus)
    async def offline(request: Request) -> OfflineStatus:
        return await offline_status(root, request.scope.get("server"))

    return router
