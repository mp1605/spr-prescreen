"""Versioned engineering conditions for existing items; no item wording is changed."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from backend.core.color_models import FeatureKind
from backend.core.policy import LIST2_IDS
from backend.core.specificity_patterns import PATTERNS

Requirement = tuple[FeatureKind, ...]
GENERAL: tuple[Requirement, ...] = (
    ("quantity", "performance"),
    ("measurement", "performance"),
    ("quantity", "unit"),
    ("quantity", "location"),
    ("program", "measurement"),
    ("system", "measurement"),
    ("quantity", "system", "operational"),
)
TECH: tuple[Requirement, ...] = (
    ("location", "measurement"),
    ("measurement", "performance"),
    ("disclosure", "operational_context"),
    ("dependency", "operational_context"),
    ("program", "measurement"),
    ("system", "measurement"),
    ("quantity", "unit", "operational"),
    ("quantity", "location", "operational"),
)
ASSET: tuple[Requirement, ...] = (
    ("quantity", "performance"),
    ("dependency", "operational_context"),
    ("quantity", "unit"),
    ("quantity", "location"),
    ("quantity", "system", "operational"),
    ("system", "measurement", "operational"),
    ("measurement", "operational"),
)
CONDITIONS: dict[str, tuple[Requirement, ...]] = {
    "L2-01": GENERAL,
    "L2-02": TECH,
    "L2-03": TECH,
    "L2-04": GENERAL,
    "L2-05": TECH,
    "L2-06": ASSET,
    "L2-07": GENERAL,
    "L2-08": TECH,
    "L2-09": TECH,
    "L2-10": (("quantity", "location", "future_date"), ("quantity", "unit", "future_date")),
    "L2-11": TECH,
    "L2-12": ASSET,
    "L2-13": (
        ("quantity", "unit", "operational"),
        ("system", "measurement", "operational"),
        ("dependency", "operational_context"),
        ("measurement", "performance"),
    ),
    "L2-14": ASSET,
    "L2-15": (
        ("procedure", "operational_context"),
        ("procedure", "measurement", "operational"),
        ("procedure", "unit", "future_date"),
        ("quantity", "unit", "future_date"),
        ("quantity", "location", "future_date"),
    ),
    "L2-16": TECH,
    "L2-17": (
        ("procedure", "system", "measurement"),
        ("procedure", "unit", "measurement"),
        ("procedure", "operational_context"),
        ("disclosure", "operational_context"),
    ),
    "L2-18": (("future_date", "location"), ("future_date", "quantity"), ("quantity", "location")),
    "L2-19": (("origin_release", "location"),),
    "L2-21": (("authority_action",),),
    "L2-24": (("rank",),),
    "L2-25": (
        ("control", "system", "measurement"),
        ("control", "program", "measurement"),
        ("control", "disclosure"),
    ),
    "L2-27": (
        ("coordination_gap", "actor"),
        ("coordination_gap", "unit"),
        ("coordination_gap", "location"),
    ),
    "L2-28": (("coordination_gap", "unit"), ("coordination_gap", "location")),
    "L2-29": (("quantity", "unit"), ("quantity", "system"), ("quantity", "location")),
    "L2-30": TECH,
    "L2-31": (
        ("release_event", "location", "date"),
        ("release_event", "location", "measurement"),
        ("release_event", "quantity", "measurement"),
    ),
}
JUDGMENT = {
    "L2-20": "National or international interest requires reviewer judgment.",
    "L2-22": "Impact on national security policy or foreign relations requires reviewer judgment.",
    "L2-23": "Potential controversy between components or agencies requires reviewer judgment.",
    "L2-26": "A DOPSR designation cannot be established from topic similarity or numbers alone.",
}
NEARBY_CHARACTERS = 180


def policy_digest() -> str:
    if set(CONDITIONS) | set(JUDGMENT) != set(LIST2_IDS):
        raise ValueError("Specificity conditions must cover exactly the official List 2 IDs")
    source = Path(__file__).parent
    sources = {
        name: hashlib.sha256((source / name).read_bytes()).hexdigest()
        for name in (
            "specificity_policy.py",
            "specificity_patterns.py",
            "specificity_disclosure.py",
            "specificity.py",
            "item_color.py",
            "fuse.py",
            "evidence_heads.py",
            "text_segments.py",
            "named_entities.py",
            "engines/context.py",
            "engines/rules.py",
        )
    }
    payload = [
        "specificity-v1",
        CONDITIONS,
        JUDGMENT,
        NEARBY_CHARACTERS,
        [(kind, pattern.pattern, pattern.flags) for kind, pattern in PATTERNS],
        sources,
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
