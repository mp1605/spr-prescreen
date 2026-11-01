"""Local AI suggestions are untrusted until bound to immutable source text."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import Field, TypeAdapter, model_validator

from backend.core.policy import OFFICIAL_IDS
from backend.core.rules_loader import StrictModel, Text


def official_enum(schema: dict[str, Any]) -> None:
    schema["enum"] = sorted(OFFICIAL_IDS)


class AIProposal(StrictModel):
    quote: str = Field(min_length=1, max_length=2048, pattern=r"\S")
    item_id: str = Field(json_schema_extra=official_enum)
    clear_or_possible: Literal["clear", "possible"]
    reason: str = Field(min_length=3, max_length=1000, pattern=r"\S")

    @model_validator(mode="after")
    def official(self) -> AIProposal:
        if self.item_id not in OFFICIAL_IDS:
            raise ValueError("Unknown official item ID")
        return self


PROPOSALS: TypeAdapter[list[AIProposal]] = TypeAdapter(
    Annotated[list[AIProposal], Field(max_length=32)]
)


class AIEvidence(StrictModel):
    item_id: str
    quote: Text
    model_quote: Text
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    match: Literal["exact", "normalized", "fuzzy"]
    similarity: float = Field(ge=90, le=100)
    clear_or_possible: Literal["clear", "possible"]
    reason: Text

    @model_validator(mode="after")
    def source(self) -> AIEvidence:
        if self.item_id not in OFFICIAL_IDS or self.char_end - self.char_start != len(self.quote):
            raise ValueError("AI evidence requires an official item and exact source extent")
        return self


class AIInfo(StrictModel):
    version: Literal["spr-ai-v1"] = "spr-ai-v1"
    provider: Literal["ollama"] = "ollama"
    model: str
    model_digest: str | None = None
    configured_model_digest: str | None = None
    configuration_digest: str
    pipeline_digest: str
    prompt_digest: str | None = None
    state: Literal["ran", "timeout", "error", "skipped"]
    scope: Literal["full", "selective"] = "full"
    total_source_segments: int = Field(default=0, ge=0)
    source_segment_ids: tuple[str, ...] = ()
    generation_attempted: bool | None = None
    seconds: float = Field(ge=0)
    accepted: int = Field(default=0, ge=0)
    rejected: int = Field(default=0, ge=0)
    issue_codes: tuple[str, ...] = ()
    context_tokens: int
    timeout_seconds: int
    max_output_tokens: int
    source_segments: int = 0
    prompt_bytes: int = 0
