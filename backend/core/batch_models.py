"""Persistent browser-run contracts; upload identity is distinct from content identity."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from backend.core.models import PaperResult
from backend.core.rules_loader import StrictModel, Text
from backend.core.semantic_models import FeedbackExample, FeedbackReference
from backend.core.settings import AISettings

Phase = Literal[
    "queued", "parsing", "list1", "list2", "ai", "done", "failed", "rejected", "cancelled"
]
TERMINAL = {"done", "failed", "rejected", "cancelled"}


class BatchEntry(StrictModel):
    entry_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    file_name: Text
    phase: Phase = "queued"
    message: str = "Waiting to parse"
    attempt: int = Field(default=1, ge=1)
    seconds: float = Field(default=0, ge=0)
    result: PaperResult | None = None


class BatchRecord(StrictModel):
    run_id: str = Field(pattern=r"^web-[a-f0-9]{32}$")
    created: datetime
    rules_version: Text
    ai_settings: AISettings | None = None
    revision: int = Field(default=0, ge=0)
    entries: tuple[BatchEntry, ...] = Field(min_length=1, max_length=100)


class ReviewProgress(StrictModel):
    reviewed: int = Field(ge=0)
    complete: bool
    approved: bool = False


class BatchView(BatchRecord):
    reviews: dict[str, ReviewProgress]


class ReviewEvent(StrictModel):
    event_id: str
    entry_id: str
    finding_id: str | None = None
    action: Literal["accept", "override", "inspect", "approve", "undo"]
    reason: str | None = Field(default=None, max_length=2000)
    reviewer: Text = Field(max_length=100)
    utc: datetime
    target_event: str | None = None
    feedback: FeedbackReference | None = None


class ReviewState(StrictModel):
    revision: int
    decisions: dict[str, ReviewEvent]
    inspected: bool
    events: tuple[ReviewEvent, ...]
    feedback_examples: tuple[FeedbackExample, ...] = ()
    approved: bool = False
    approval_event: ReviewEvent | None = None
    storage_file: str | None = None
    storage_error: str | None = None


class ReviewCommand(StrictModel):
    revision: int = Field(ge=0)
    action: Literal["accept", "override", "inspect", "approve", "undo"]
    finding_id: str | None = None
    reviewer: Text = Field(max_length=100)
    reason: str | None = Field(default=None, max_length=2000)
    target_event: str | None = None
