"""Validate indicator edits while protecting the official policy and execution contract."""

from __future__ import annotations

import hashlib
import json

import yaml
from pydantic import ValidationError

from backend.core.engines.rules import RulesEngine
from backend.core.policy_models import FieldChange, ValidationReport
from backend.core.rules_loader import PolicyError, RuleRegistry, UniqueKeyLoader


def candidate_registry(text: str) -> RuleRegistry:
    if len(text.encode()) > 524288:
        raise PolicyError("Draft exceeds the 512 KiB limit.")
    events = list(yaml.parse(text))
    if any(isinstance(e, yaml.events.AliasEvent) or getattr(e, "anchor", None) for e in events):
        raise PolicyError("YAML aliases and anchors are not permitted in rule drafts.")
    if len(events) > 20000:
        raise PolicyError("Draft exceeds the YAML structure limit.")
    depth = 0
    for event in events:
        if isinstance(event, (yaml.events.MappingStartEvent, yaml.events.SequenceStartEvent)):
            depth += 1
            if depth > 32:
                raise PolicyError("Draft exceeds the YAML nesting limit.")
        elif isinstance(event, (yaml.events.MappingEndEvent, yaml.events.SequenceEndEvent)):
            depth -= 1
    registry = RuleRegistry.model_validate(yaml.load(text, Loader=UniqueKeyLoader))
    detectors = [d for item in (*registry.list1, *registry.list2) for d in item.detectors]
    if len(detectors) > 1000 or any(
        len(d.pattern or "") > 8192 or len(d.context_pattern or "") > 8192 for d in detectors
    ):
        raise PolicyError("Draft exceeds the detector resource limits.")
    RulesEngine(registry)
    return registry


def validate_candidate(text: str, baseline: RuleRegistry) -> ValidationReport:
    digest = hashlib.sha256(text.encode()).hexdigest()
    changes = []
    errors = []
    try:
        registry = candidate_registry(text)
        for field in (
            "policy_version",
            "source_document",
            "source_sha256",
            "list_execution_order",
            "short_circuit",
            "color_rules",
        ):
            before = baseline.model_dump(mode="json")[field]
            after = registry.model_dump(mode="json")[field]
            if before != after:
                changes.append(
                    FieldChange(
                        field=field,
                        before=json.dumps(before),
                        after=json.dumps(after),
                        protected=True,
                    )
                )
        for before, after in zip(
            (*baseline.list1, *baseline.list2), (*registry.list1, *registry.list2), strict=True
        ):
            for field in ("text", "source_pages", "category", "examples", "detectors"):
                old = before.model_dump(mode="json")[field]
                new = after.model_dump(mode="json")[field]
                if old != new:
                    protected = field != "detectors"
                    changes.append(
                        FieldChange(
                            item_id=before.id,
                            field=field,
                            before=json.dumps(old, ensure_ascii=False),
                            after=json.dumps(new, ensure_ascii=False),
                            protected=protected,
                        )
                    )
        if any(c.protected for c in changes):
            errors.append(
                "Official wording, categories, examples, source, numbering, version "
                "and execution rules are protected. Edit detectors only."
            )
        count = sum(len(item.detectors) for item in (*registry.list1, *registry.list2))
    except (PolicyError, ValidationError, yaml.YAMLError, ValueError) as exc:
        errors.append(str(exc))
        count = 0
    return ValidationReport(
        valid=not errors,
        errors=tuple(errors),
        changes=tuple(changes),
        yaml_sha256=digest,
        detector_count=count,
    )
