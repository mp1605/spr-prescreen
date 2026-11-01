"""An immutable engine bundle pins a batch to the rules present when it was submitted."""

from dataclasses import dataclass

from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.rules_loader import RuleRegistry
from backend.core.specificity import SpecificityEngine


@dataclass(frozen=True)
class ScreeningContext:
    rules: RuleRegistry
    engine: RulesEngine
    semantic: SemanticEngine | None
    specificity: SpecificityEngine | None
