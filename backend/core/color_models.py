"""Source-bound reasons for color; existing runs may omit these M6 fields."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from backend.core.ai_models import AIEvidence
from backend.core.policy import OFFICIAL_IDS
from backend.core.rules_loader import StrictModel, Text

FeatureKind = Literal[
    "quantity",
    "unit",
    "location",
    "system",
    "program",
    "date",
    "future_date",
    "measurement",
    "operational",
    "procedure",
    "control",
    "rank",
    "coordination_gap",
    "actor",
    "origin_release",
    "authority_action",
    "release_event",
    "uncertainty",
    "negation",
    "topic",
    "performance",
    "disclosure",
    "dependency",
    "operational_context",
]


class SpecificityFeature(StrictModel):
    kind: FeatureKind
    text: Text
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    source: Literal["regex", "local_ner"] = "regex"

    @model_validator(mode="after")
    def span(self) -> SpecificityFeature:
        if self.char_end <= self.char_start:
            raise ValueError("Specificity evidence must have a nonempty source span")
        return self


class ItemAssessment(StrictModel):
    item_id: Text
    disposition: Literal["clear", "possible"]
    reason: Text
    evidence: tuple[SpecificityFeature, ...] = ()
    rule_anchor: SpecificityFeature | None = None
    ai_evidence: AIEvidence | None = None

    @model_validator(mode="after")
    def official(self) -> ItemAssessment:
        if self.item_id not in OFFICIAL_IDS:
            raise ValueError("Color assessments cannot introduce official items")
        if (
            self.ai_evidence
            and self.disposition == "clear"
            and self.item_id.startswith("L2-")
            and self.ai_evidence.clear_or_possible != "clear"
        ):
            raise ValueError("Possible AI evidence cannot establish a clear List 2 match")
        if self.ai_evidence and self.ai_evidence.item_id != self.item_id:
            raise ValueError("AI assessment must name its owning official item")
        if self.disposition == "clear" and self.item_id.startswith("L2-"):
            if not self.evidence or self.rule_anchor is None or self.rule_anchor.kind != "topic":
                raise ValueError("Clear List 2 assessments require specificity and a rule anchor")
        return self


class ColorAssessment(StrictModel):
    version: Literal["specificity-v1"] = "specificity-v1"
    state: Literal["complete", "error"] = "complete"
    items: tuple[ItemAssessment, ...] = Field(min_length=1)


class FusionInfo(StrictModel):
    version: Literal["source-span-fusion-v1"] = "source-span-fusion-v1"
    specificity_version: Literal["specificity-v1"] = "specificity-v1"
    policy_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    as_of_utc_date: date
    ner_state: Literal["not_used", "ready", "unavailable"]
    ner_model_digest: str | None = None
    state: Literal["complete", "error"]
