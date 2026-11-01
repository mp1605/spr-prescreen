"""Similarity evidence is a policy reference, never a probability or release decision."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from backend.core.policy import OFFICIAL_IDS
from backend.core.rules_loader import StrictModel, Text


class SemanticMatch(StrictModel):
    item_id: Text
    text: Text
    score: float = Field(ge=0, le=1)
    band: Literal["high", "possible"]
    source: Literal["official_rule"] = "official_rule"

    @model_validator(mode="after")
    def official(self) -> SemanticMatch:
        if self.item_id not in OFFICIAL_IDS:
            raise ValueError("Semantic references must name official items")
        return self


class SemanticInfo(StrictModel):
    version: Literal["official-bge-v1"] = "official-bge-v1"
    model: Literal["BAAI/bge-small-en-v1.5"] = "BAAI/bge-small-en-v1.5"
    dimensions: Literal[384] = 384
    reference_source: Literal["official_rules_only"] = "official_rules_only"
    reference_count: Literal[39] = 39
    reference_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    model_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    high_threshold: float = Field(ge=0, le=1)
    mid_threshold: float = Field(ge=0, le=1)
    calibrated: Literal[False] = False
    feedback_usage: Literal["excluded_during_blind_build"] = "excluded_during_blind_build"
    state: Literal["complete", "error"]
    segments: int = Field(ge=0)
    chunks: int = Field(ge=0)
    cache_state: Literal["not_used", "hit", "miss", "unavailable"]
    seconds: float = Field(ge=0)

    @model_validator(mode="after")
    def completion(self) -> SemanticInfo:
        if self.mid_threshold >= self.high_threshold:
            raise ValueError("Semantic thresholds must be ordered")
        if self.state == "complete" and self.segments:
            if self.chunks < self.segments or self.model_digest is None:
                raise ValueError("Completed semantic text needs model and window provenance")
        return self


class FeedbackReference(StrictModel):
    """Audit records keep references and polarity, not duplicated document quotations."""

    finding_id: Text
    polarity: Literal["positive", "negative"]
    usage: Literal["excluded_during_blind_build"] = "excluded_during_blind_build"


class FeedbackExample(FeedbackReference):
    finding_id: Text
    paper_id: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    rules_version: Text
    items: tuple[Text, ...] = Field(min_length=1)
    quote: Text
    source: Literal["reviewer_decision"] = "reviewer_decision"

    @model_validator(mode="after")
    def official(self) -> FeedbackExample:
        if any(item not in OFFICIAL_IDS for item in self.items):
            raise ValueError("Feedback cannot introduce policy items")
        return self
