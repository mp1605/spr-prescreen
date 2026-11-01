"""Validate policy data before any HTTP listener is started."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.core.policy import LIST1_IDS, LIST2_IDS, OFFICIAL_IDS

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]


class PolicyError(ValueError):
    """Actionable configuration error, without document content."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Detector(StrictModel):
    kind: Literal["regex", "keywords"]
    name: Text
    item_id: Text
    pattern: str | None = None
    terms: tuple[Text, ...] = ()
    case_sensitive: bool = False
    guard: Literal["none", "classification_marking", "acknowledgment", "byline"] = "none"
    context_pattern: str | None = None
    context_scope: Literal["unit", "nearby", "document"] = "unit"

    @model_validator(mode="after")
    def validate_detector(self) -> Detector:
        if self.item_id not in OFFICIAL_IDS:
            raise ValueError(f"Unknown detector item ID: {self.item_id}")
        if self.kind == "regex":
            if not self.pattern or self.terms:
                raise ValueError("Regex detectors require a pattern and no terms")
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"Invalid regex for detector {self.name}: {exc}") from exc
        elif not self.terms or self.pattern is not None:
            raise ValueError("Keyword detectors require terms and no pattern")
        if self.guard in ("classification_marking", "byline") and self.kind != "regex":
            raise ValueError("Marking and byline guards require regex detectors")
        if self.guard == "acknowledgment" and not self.context_pattern:
            raise ValueError("Acknowledgment detectors require a context pattern")
        if self.context_pattern is not None:
            try:
                re.compile(self.context_pattern)
            except re.error as exc:
                raise ValueError(f"Invalid context regex for detector {self.name}: {exc}") from exc
        return self


class RuleItem(StrictModel):
    id: Text
    text: Text
    source_pages: tuple[Annotated[int, Field(ge=1)], ...] = Field(min_length=1)
    category: Text | None = None
    examples: Text | None = None
    detectors: tuple[Detector, ...] = ()

    @model_validator(mode="after")
    def validate_references(self) -> RuleItem:
        if self.id not in OFFICIAL_IDS:
            raise ValueError(f"Unknown official item ID: {self.id}")
        if any(d.item_id != self.id for d in self.detectors):
            raise ValueError(f"Detector reference must name its owning item {self.id}")
        names = [d.name for d in self.detectors]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate detector name on {self.id}")
        return self


class ColorRules(StrictModel):
    list1_any_hit: Literal["red"]
    list2_clear_match: Literal["red"]
    list2_possible_match: Literal["yellow"]
    judgment_item_default: Literal["yellow"]
    unreadable_or_uncertain: Literal["yellow"]
    aggregation: Literal["worst_color_wins"]


class RuleRegistry(StrictModel):
    policy_version: Text
    source_document: Literal["docs/official-lists.pdf"]
    source_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    list_execution_order: tuple[Literal["list1"], Literal["list2"]]
    short_circuit: Literal[False]
    color_rules: ColorRules
    list1: tuple[RuleItem, ...]
    list2: tuple[RuleItem, ...]

    @model_validator(mode="after")
    def validate_official_ids(self) -> RuleRegistry:
        if tuple(item.id for item in self.list1) != LIST1_IDS:
            raise ValueError("List 1 must contain exactly L1-1, L1-3 through L1-9, in order")
        if tuple(item.id for item in self.list2) != LIST2_IDS:
            raise ValueError("List 2 must contain exactly L2-01 through L2-31, in order")
        return self


class ActivePolicy(StrictModel):
    version: Text
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    published_by: Text
    utc: Text
    change_note: Text


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject ambiguous duplicate keys instead of silently keeping the last value."""


def _unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[str, object]:
    result: dict[str, object] = {}
    construct = cast(Callable[..., object], loader.construct_object)
    for key_node, value_node in node.value:
        key = construct(key_node, deep=deep)
        if not isinstance(key, str):
            raise PolicyError("YAML mapping keys must be strings")
        if key in result:
            raise PolicyError(f"Duplicate YAML key: {key}")
        result[key] = construct(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_yaml(path: Path) -> object:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise PolicyError(f"Invalid YAML configuration at {path.name}: {exc}") from exc


def load_rules(root: Path) -> RuleRegistry:
    from backend.core.policy_disk import publication_lock, recover_publication_locked

    with publication_lock(root):
        recover_publication_locked(root)
        return _read_rules(root)


def _read_rules(root: Path) -> RuleRegistry:
    path = root / "policies/official_rules.yaml"
    try:
        registry = RuleRegistry.model_validate(load_yaml(path))
        active = ActivePolicy.model_validate_json((root / "policies/active.json").read_bytes())
        if hashlib.sha256(path.read_bytes()).hexdigest() != active.sha256:
            raise PolicyError("Rules changed outside the admin editor — re-publish as admin")
        if active.version != registry.policy_version:
            raise PolicyError("Active policy version does not match registry")
        source = root / registry.source_document
        if hashlib.sha256(source.read_bytes()).hexdigest() != registry.source_sha256:
            raise PolicyError("Official policy source PDF failed its SHA-256 integrity check")
        return registry
    except (OSError, ValidationError) as exc:
        raise PolicyError(f"Policy startup validation failed: {exc}") from exc
