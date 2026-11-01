"""Admin draft state and impact reports never contain sponsor labels or recall estimates."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from backend.core.models import PaperResult
from backend.core.rules_loader import StrictModel


class PolicyConflict(ValueError):
    pass


class PolicyInputError(ValueError):
    pass


class FieldChange(StrictModel):
    item_id: str | None = None
    field: str
    before: str
    after: str
    protected: bool = False


class ValidationReport(StrictModel):
    valid: bool
    errors: tuple[str, ...]
    changes: tuple[FieldChange, ...]
    yaml_sha256: str
    detector_count: int = 0


class Draft(StrictModel):
    draft_id: str
    revision: int = 0
    created_utc: datetime
    updated_utc: datetime
    base_version: str
    base_sha256: str
    yaml_text: str
    validation: ValidationReport | None = None
    preview_id: str | None = None
    restore_from: str | None = None
    state: Literal["draft", "validated", "previewing", "previewed", "published"] = "draft"
    published_version: str | None = None


class DraftEdit(StrictModel):
    revision: int = Field(ge=0)
    yaml_text: str = Field(min_length=1, max_length=524288)


class RevisionCommand(StrictModel):
    revision: int = Field(ge=0)


class PublishCommand(RevisionCommand):
    preview_id: str
    change_note: str = Field(min_length=3, max_length=2000, pattern=r"\S")


class PreviewEntry(StrictModel):
    file_name: str
    sha256: str
    before: PaperResult | None = None
    after: PaperResult | None = None
    changed: bool = False
    message: str = "Waiting to parse"


class Preview(StrictModel):
    preview_id: str
    draft_id: str
    draft_sha256: str
    base_sha256: str
    state: Literal["queued", "running", "complete", "failed", "interrupted"] = "queued"
    eligible: bool = False
    entries: tuple[PreviewEntry, ...]
    message: str = "Waiting for local impact scan"
    created_utc: datetime
    source: Literal["explicit_upload_only"] = "explicit_upload_only"
    sponsor_metrics: Literal["NOT_MEASURED"] = "NOT_MEASURED"
