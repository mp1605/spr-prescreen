"""Read-only item navigation; decisions remain separate per-upload resources."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from backend.core.batch_models import ReviewEvent
from backend.core.models import Color, Finding
from backend.core.rules_loader import StrictModel, Text


class ItemScope(StrictModel):
    run_ids: tuple[str, ...]
    snapshot: str
    completed_papers: int = Field(ge=0)
    unfinished_entries: int = Field(ge=0)
    unavailable_entries: int = Field(ge=0)
    incomplete_papers: int = Field(ge=0)
    unique_findings: int = Field(ge=0)


class ItemSummary(StrictModel):
    item_id: Text
    list: Literal["list1", "list2"]
    text: Text
    source_pages: tuple[int, ...]
    findings: int = Field(ge=0)
    papers: int = Field(ge=0)
    red: int = Field(ge=0, description="Raw passage priority, not per-item disposition")
    yellow: int = Field(ge=0, description="Raw passage priority, not per-item disposition")
    pending: int = Field(ge=0)
    accepted: int = Field(ge=0)
    overridden: int = Field(ge=0)


class ItemIndex(StrictModel):
    scope: ItemScope
    items: tuple[ItemSummary, ...]
    count_convention: str = (
        "Each finding appears under every item it names. Item counts may overlap; "
        "scope.unique_findings counts each finding once per upload. Colors are raw "
        "passage priorities; per-item dispositions remain in the finding assessment. "
        "A decision applies to the whole finding across all of its named items."
    )


class ItemFinding(StrictModel):
    run_id: str
    entry_id: str
    file_name: Text
    file_type: Literal["pdf", "docx"]
    paper_color: Color
    rules_version: Text
    incomplete_reasons: tuple[str, ...]
    incomplete_pages: tuple[int, ...]
    review_revision: int = Field(ge=0)
    decision: ReviewEvent | None
    finding: Finding
    review_url: str
    decisions_url: str


class ItemPage(StrictModel):
    scope: ItemScope
    item: ItemSummary
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    has_more: bool
    entries: tuple[ItemFinding, ...]
    release_decision: Literal["NOT_MADE_BY_TOOL"] = "NOT_MADE_BY_TOOL"
