"""Engine output references source segments; it cannot supply invented quotations."""

from __future__ import annotations

from typing import Literal, Protocol

from pydantic import Field, model_validator

from backend.core.ingest_models import ParseResult
from backend.core.models import NonnegativeInt, PositiveInt
from backend.core.policy import OFFICIAL_IDS, ListName
from backend.core.rules_loader import RuleItem, StrictModel, Text
from backend.core.semantic_models import SemanticMatch


class Hit(StrictModel):
    segment_id: Text
    item_id: Text
    list: ListName
    detector: Text
    engine: Literal["rules", "semantic"] = "rules"
    score: float | None = Field(default=None, ge=0, le=1)
    reference: SemanticMatch | None = None
    char_start: NonnegativeInt
    char_end: PositiveInt

    @model_validator(mode="after")
    def validate_hit(self) -> Hit:
        if self.item_id not in OFFICIAL_IDS:
            raise ValueError("Unknown detector item ID")
        prefix = "L1-" if self.list == "list1" else "L2-"
        if not self.item_id.startswith(prefix):
            raise ValueError("Detector item does not belong to its named list")
        if self.char_end <= self.char_start:
            raise ValueError("Hit must have a nonempty source span")
        if self.engine == "semantic":
            if (
                self.score is None
                or self.reference is None
                or self.reference.item_id != self.item_id
                or self.reference.score != self.score
            ):
                raise ValueError("Semantic hits require a matching scored official reference")
        elif self.score is not None or self.reference is not None:
            raise ValueError("Rules hits cannot claim semantic evidence")
        return self


class Engine(Protocol):
    rules_version: str

    def run(
        self, document: ParseResult, list_name: ListName, items: tuple[RuleItem, ...]
    ) -> tuple[Hit, ...]: ...
