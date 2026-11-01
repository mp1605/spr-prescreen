"""Versioned exports keep original scanner results separate from human decisions."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from backend.core.batch_models import BatchRecord, ReviewState
from backend.core.rules_loader import StrictModel

SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
SourceIntegrity = Literal["verified", "unavailable", "mismatch", "not_screened", "not_retained"]


class ExportReport(StrictModel):
    schema_version: Literal["spr-export-v1"] = "spr-export-v1"
    generated_utc: datetime
    disclaimer: str
    release_decision: Literal["NOT_MADE_BY_TOOL"] = "NOT_MADE_BY_TOOL"
    scope: Literal["entire_batch"] = "entire_batch"
    batch: BatchRecord
    source_sha256: dict[str, SHA256 | None]
    current_source_sha256: dict[str, SHA256 | None]
    source_integrity: dict[str, SourceIntegrity]
    reviews: dict[str, ReviewState]
    annotation_convention: str = (
        "Red/yellow retain raw screening colors, including overridden flags. "
        "Reviewer decisions remain separate. Green means no flags found, not a release decision."
    )


class AnnotationManifest(StrictModel):
    schema_version: Literal["spr-annotation-v1"] = "spr-annotation-v1"
    run_id: str
    entry_id: str
    original_file_name: str
    download_file_name: str
    source_sha256: SHA256
    annotated_sha256: SHA256
    rules_version: str
    ai_state: str
    review_revision: int = Field(ge=0)
    created_utc: datetime
    findings_annotated: int = Field(ge=0)
    notes_included: bool = False
    warnings: tuple[str, ...]
    disclaimer: str
    release_decision: Literal["NOT_MADE_BY_TOOL"] = "NOT_MADE_BY_TOOL"
