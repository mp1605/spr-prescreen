"""Evaluation-only contracts; scanner modules never import or consume gold data."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from backend.core.models import Color, PaperID, PaperResult
from backend.core.policy import OFFICIAL_IDS
from backend.core.rules_loader import StrictModel, Text


class GoldTrigger(StrictModel):
    tag: str = Field(pattern=r"^T[1-9]\d*$")
    quote: Text
    items: tuple[Text, ...] = Field(min_length=1)
    color: Literal["red", "yellow"]
    reason: Text

    @model_validator(mode="after")
    def validate_items(self) -> GoldTrigger:
        if len(set(self.items)) != len(self.items) or not set(self.items) <= OFFICIAL_IDS:
            raise ValueError("Gold items must be unique official IDs")
        if any(item.startswith("L1-") for item in self.items) and self.color != "red":
            raise ValueError("List 1 gold triggers must be red")
        return self


class GoldCase(StrictModel):
    case_id: Text
    expected_color: Color
    paper_id: PaperID | None = None
    source_key_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    triggers: tuple[GoldTrigger, ...] = ()
    decoys: tuple[Text, ...] = ()
    reference_good: bool = False

    @model_validator(mode="after")
    def validate_case(self) -> GoldCase:
        if len({trigger.tag for trigger in self.triggers}) != len(self.triggers):
            raise ValueError("Gold tags must be unique within a case")
        expected = (
            "red"
            if any(t.color == "red" for t in self.triggers)
            else "yellow"
            if self.triggers
            else "green"
        )
        if self.expected_color != expected:
            raise ValueError("Expected paper color does not agree with its gold triggers")
        if len(set(self.decoys)) != len(self.decoys):
            raise ValueError("Decoys must be unique within a case")
        if self.reference_good and self.triggers:
            raise ValueError("Reference-good cases cannot contain known triggers")
        return self


class PredictionCase(StrictModel):
    case_id: Text
    result: PaperResult


class Passage(StrictModel):
    finding_ids: tuple[Text, ...]
    quote: Text
    items: tuple[Text, ...]
    color: Literal["red", "yellow"]


class CaseScore(StrictModel):
    case_id: Text
    expected_color: Color
    actual_color: Color
    trigger_count: int
    matched_count: int
    false_alarms: tuple[Passage, ...]
    missed: tuple[GoldTrigger, ...]
    decoy_hits: tuple[Text, ...]
    matches: tuple[tuple[str, tuple[str, ...]], ...]


class EvaluationReport(StrictModel):
    kind: Literal["format_contract", "sponsor_evaluation"]
    paper_count: int
    trigger_count: int
    matched_triggers: int
    trigger_recall: float | None
    list1_recall: float | None
    list2_recall: float | None
    list1_trigger_count: int
    list2_trigger_count: int
    item_accuracy: float | None
    flag_color_accuracy: float | None
    paper_color_accuracy: float
    confusion: dict[str, dict[str, int]]
    false_alarms: int
    greens_wrongly_flagged: int
    decoy_count: int
    decoys_flagged: int
    decoy_flag_rate: float | None
    false_alarms_on_reference_papers: int
    reference_paper_count: int = 0
    incomplete_papers: int
    seconds_per_paper_ai_off: float | None
    seconds_per_paper_ai_on: float | None
    weighted_cost: int
    rules_versions: tuple[str, ...]
    cases: tuple[CaseScore, ...]
    matching_policy: str
    cost_assumption: str = "3 × missed triggers + 1 × false alarms; engineering assumption"
