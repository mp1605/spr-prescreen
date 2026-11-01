"""Immutable screening contracts. Reviewer decisions are separate records."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from backend.core.ai_models import AIEvidence, AIInfo
from backend.core.color_models import ColorAssessment, FusionInfo
from backend.core.policy import OFFICIAL_IDS, ListName
from backend.core.rules_loader import StrictModel, Text
from backend.core.semantic_models import SemanticInfo, SemanticMatch

PaperID = Annotated[str, Field(pattern=r"^sha256:[a-f0-9]{64}$")]
PositiveInt = Annotated[int, Field(ge=1)]
NonnegativeInt = Annotated[int, Field(ge=0)]
EngineName = Literal["rules", "semantic", "ai"]
Color = Literal["green", "yellow", "red"]
PaperLabel = Literal["No flags found", "Potential flag", "Flag identified", "Incomplete"]
Rect = tuple[float, float, float, float]


class Location(StrictModel):
    page: PositiveInt | None = None
    paragraph: PositiveInt | None = None
    heading: str | None = None
    char_start: NonnegativeInt
    char_end: PositiveInt
    bbox: tuple[Rect, ...] | None = None

    @model_validator(mode="after")
    def validate_span(self) -> Location:
        if (self.page is None) == (self.paragraph is None):
            raise ValueError("Evidence requires exactly one page or paragraph locator")
        if self.char_end <= self.char_start:
            raise ValueError("Evidence char_end must be greater than char_start")
        if self.bbox is not None:
            if self.page is None or not self.bbox:
                raise ValueError(
                    "Bounding rectangles require a PDF page and at least one rectangle"
                )
            for x0, y0, x1, y1 in self.bbox:
                if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
                    raise ValueError("Invalid evidence rectangle")
        return self


class Finding(StrictModel):
    finding_id: Text
    paper_id: PaperID
    list: ListName
    items: tuple[Text, ...] = Field(min_length=1)
    color: Literal["red", "yellow"]
    quote: Text
    location: Location
    reason: Text
    why_unsure: Text | None = None
    engines: tuple[EngineName, ...] = Field(min_length=1)
    score: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)] | None = None
    nearest_exemplar: str | None = None
    semantic_matches: tuple[SemanticMatch, ...] = Field(default=(), max_length=3)
    assessment: ColorAssessment | None = None
    ai_matches: tuple[AIEvidence, ...] = ()

    @model_validator(mode="after")
    def validate_evidence(self) -> Finding:
        if len(set(self.items)) != len(self.items):
            raise ValueError("Finding items must be unique")
        for item in self.items:
            if item not in OFFICIAL_IDS:
                raise ValueError(f"Unknown official item ID: {item}")
            if not item.startswith("L1-" if self.list == "list1" else "L2-"):
                raise ValueError("Finding items must belong to the named list")
        if self.list == "list1" and self.color != "red":
            raise ValueError("List 1 findings must be red")
        if self.color == "yellow" and not self.why_unsure:
            raise ValueError("Yellow findings require why_unsure")
        if len(self.engines) != len(set(self.engines)):
            raise ValueError("Finding engines must be unique")
        if "semantic" in self.engines:
            if not self.semantic_matches or self.score is None:
                raise ValueError("Semantic findings require scored policy references")
            if any(ref.item_id not in self.items for ref in self.semantic_matches):
                raise ValueError("Semantic references must belong to the finding")
            if self.score != max(ref.score for ref in self.semantic_matches):
                raise ValueError("Finding score must agree with its strongest reference")
        elif self.semantic_matches:
            raise ValueError("Semantic references require semantic engine provenance")
        if ("ai" in self.engines) != bool(self.ai_matches):
            raise ValueError("AI findings require source-verified AI evidence")
        for evidence in self.ai_matches:
            if evidence.item_id not in self.items:
                raise ValueError("AI evidence must name a finding item")
            start, end = (
                evidence.char_start - self.location.char_start,
                evidence.char_end - self.location.char_start,
            )
            if not 0 <= start < end <= len(self.quote) or self.quote[start:end] != evidence.quote:
                raise ValueError("AI evidence must be an exact finding source slice")
        if self.assessment:
            if any(
                item.ai_evidence and item.ai_evidence not in self.ai_matches
                for item in self.assessment.items
            ):
                raise ValueError("AI assessments require matching AI engine provenance")
            if {item.item_id for item in self.assessment.items} != set(self.items):
                raise ValueError("Color evidence must assess every finding item exactly once")
            if len(self.assessment.items) != len(self.items):
                raise ValueError("Color item assessments must be unique")
            expected = (
                "red"
                if any(item.disposition == "clear" for item in self.assessment.items)
                else "yellow"
            )
            if self.color != expected:
                raise ValueError("Finding color must reflect its item assessments")
            for assessed in self.assessment.items:
                for fact in (
                    *assessed.evidence,
                    *((assessed.rule_anchor,) if assessed.rule_anchor else ()),
                ):
                    start = fact.char_start - self.location.char_start
                    end = fact.char_end - self.location.char_start
                    if (
                        not 0 <= start < end <= len(self.quote)
                        or self.quote[start:end] != fact.text
                    ):
                        raise ValueError(
                            "Specificity evidence must be an exact finding source slice"
                        )
        return self


class FlagCount(StrictModel):
    total: NonnegativeInt
    red: NonnegativeInt
    yellow: NonnegativeInt

    @model_validator(mode="after")
    def validate_total(self) -> FlagCount:
        if self.total != self.red + self.yellow:
            raise ValueError("Flag total must equal red plus yellow")
        return self


class PaperResult(StrictModel):
    paper_id: PaperID
    file_name: Text
    file_type: Literal["docx", "pdf"]
    screening_stage: Literal["rules_only", "rules_semantic"] = "rules_only"
    semantic: SemanticInfo | None = None
    fusion: FusionInfo | None = None
    color: Color
    label: PaperLabel
    flag_count: FlagCount
    lists_checked: tuple[ListName, ...]
    trace: tuple[str, ...]
    incomplete_pages: tuple[PositiveInt, ...] = ()
    incomplete_reasons: tuple[Text, ...] = ()
    ai_state: Literal["off", "ran", "timeout", "error", "skipped"]
    ai: AIInfo | None = None
    rules_version: Text
    seconds: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    release_decision: Literal["NOT_MADE_BY_TOOL"] = "NOT_MADE_BY_TOOL"
    findings: tuple[Finding, ...]

    @model_validator(mode="after")
    def validate_result(self) -> PaperResult:
        if self.ai and self.ai.state != self.ai_state:
            raise ValueError("AI completion record disagrees with its state")
        if self.ai_state == "off" and any("ai" in flag.engines for flag in self.findings):
            raise ValueError("AI-off results cannot claim AI evidence")
        if any("ai" in flag.engines for flag in self.findings) and self.ai is None:
            raise ValueError("AI findings require paper-level model provenance")
        if (self.screening_stage == "rules_semantic") != (self.semantic is not None):
            raise ValueError("Semantic screening requires its configuration and completion record")
        if self.semantic and self.semantic.state == "error" and not self.incomplete_reasons:
            raise ValueError("Semantic failure must remain visibly incomplete")
        if not self.semantic and any("semantic" in finding.engines for finding in self.findings):
            raise ValueError("Semantic findings require paper-level model provenance")
        if self.semantic:
            for finding in self.findings:
                for reference in finding.semantic_matches:
                    expected = (
                        "high" if reference.score >= self.semantic.high_threshold else "possible"
                    )
                    if reference.score < self.semantic.mid_threshold or reference.band != expected:
                        raise ValueError(
                            "Semantic evidence must agree with the recorded thresholds"
                        )
        if self.fusion:
            if any(f.assessment is None for f in self.findings):
                raise ValueError("Fused findings require item-level color evidence")
            if self.fusion.state == "error" and not self.incomplete_reasons:
                raise ValueError("Failed color assessment must remain visibly incomplete")
        if self.lists_checked != ("list1", "list2"):
            raise ValueError("Both lists must be checked, in order")
        if (
            len(self.trace) != 2
            or self.trace[0] not in ("list1:done", "list1:error")
            or self.trace[1] not in ("list2:done", "list2:error")
        ):
            raise ValueError("Trace must record List 1 then List 2 completion")
        if any(event.endswith(":error") for event in self.trace) and not self.incomplete_reasons:
            raise ValueError("Failed list checks require an explicit incomplete reason")
        if any(f.paper_id != self.paper_id for f in self.findings):
            raise ValueError("Finding paper ID must match its parent")
        if len({f.finding_id for f in self.findings}) != len(self.findings):
            raise ValueError("Finding IDs must be unique within a paper")
        reds = sum(f.color == "red" for f in self.findings)
        yellows = len(self.findings) - reds
        if self.flag_count != FlagCount(total=len(self.findings), red=reds, yellow=yellows):
            raise ValueError("Flag counts must match findings")
        incomplete = bool(self.incomplete_pages or self.incomplete_reasons)
        uncertain = incomplete or self.ai_state in ("timeout", "error")
        expected = "red" if reds else "yellow" if yellows or uncertain else "green"
        if self.color != expected:
            raise ValueError("Paper color must reflect worst finding or uncertainty")
        label = (
            "Flag identified"
            if reds
            else "Incomplete"
            if incomplete
            else "Potential flag"
            if expected == "yellow"
            else "No flags found"
        )
        if self.label != label:
            raise ValueError("Paper label must agree with color and completeness")
        return self


class Decision(StrictModel):
    finding_id: Text
    action: Literal["accept", "override"]
    reason: Text | None = None
    reviewer: Text
    utc: datetime

    @field_validator("utc")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("Decision timestamp must be timezone-aware UTC")
        return value
