"""Merge overlapping source passages within each list, retaining every item and engine."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Literal

from backend.core.color_models import ColorAssessment, FusionInfo, ItemAssessment
from backend.core.engines.base import Hit
from backend.core.engines.context import SourceContext
from backend.core.evidence_heads import substantive_hits
from backend.core.ingest_models import ParseResult, Segment, SourceUnit
from backend.core.item_color import assess_item
from backend.core.models import EngineName, Finding, Location
from backend.core.policy import ListName
from backend.core.rules_loader import RuleRegistry
from backend.core.specificity import SpecificityEngine


@dataclass
class Passage:
    unit: SourceUnit
    list_name: ListName
    start: int
    end: int
    hits: list[Hit]
    segments: list[Segment]


def passages(document: ParseResult, hits: tuple[Hit, ...]) -> tuple[Passage, ...]:
    hits = substantive_hits(hits, document)
    segments = {segment.segment_id: segment for segment in document.segments}
    units = {unit.unit_id: unit for unit in document.units}
    grouped: dict[tuple[ListName, int], list[Hit]] = defaultdict(list)
    for hit in hits:
        grouped[(hit.list, segments[hit.segment_id].unit_id)].append(hit)
    result: list[Passage] = []
    for (list_name, unit_id), group in sorted(grouped.items()):
        current: Passage | None = None
        for hit in sorted(
            group,
            key=lambda h: (
                segments[h.segment_id].location.char_start,
                segments[h.segment_id].location.char_end,
                h.item_id,
                h.engine,
            ),
        ):
            segment = segments[hit.segment_id]
            start, end = segment.location.char_start, segment.location.char_end
            if current is None or start >= current.end:
                current = Passage(units[unit_id], list_name, start, end, [], [])
                result.append(current)
            current.end = max(current.end, end)
            current.hits.append(hit)
            current.segments.append(segment)
    return tuple(result)


def _location(passage: Passage) -> Location:
    unit = passage.unit
    boxes = tuple(
        word.bbox
        for word in unit.words
        if word.char_start < passage.end and passage.start < word.char_end
    )
    if unit.page is not None and not boxes:
        boxes = tuple(
            dict.fromkeys(box for s in passage.segments for box in (s.location.bbox or ()))
        )
    return Location(
        page=unit.page,
        paragraph=unit.paragraph,
        heading=unit.heading,
        char_start=passage.start,
        char_end=passage.end,
        bbox=boxes if unit.page is not None else None,
    )


def fuse_findings(
    document: ParseResult,
    hits: tuple[Hit, ...],
    registry: RuleRegistry,
    assessor: SpecificityEngine,
    *,
    as_of: date,
    profile: str,
) -> tuple[tuple[Finding, ...], FusionInfo]:
    segments = {segment.segment_id: segment for segment in document.segments}
    context = SourceContext(document)
    findings: list[Finding] = []
    failed = False
    needs_ner = any(hit.list == "list2" and hit.engine == "rules" for hit in hits)
    if needs_ner:
        assessor.named("")  # Resolve the optional model before assigning stable finding IDs.
    ner_digest = assessor.ner_model_digest if needs_ner else None
    for passage in passages(document, hits):
        item_ids = tuple(sorted({hit.item_id for hit in passage.hits}))
        assessment_error = False
        try:
            facts = (
                assessor.features(
                    passage.unit, passage.start, passage.end, as_of=as_of, context=context
                )
                if passage.list_name == "list2" and any(h.engine == "rules" for h in passage.hits)
                else ()
            )
            for fact in facts:
                if (
                    not passage.start <= fact.char_start < fact.char_end <= passage.end
                    or passage.unit.text[fact.char_start : fact.char_end] != fact.text
                ):
                    raise ValueError("Specificity model supplied invalid source facts")
            decisions = tuple(
                assess_item(item_id, tuple(passage.hits), facts, segments, passage.unit)
                for item_id in item_ids
            )
        except Exception:
            failed = assessment_error = True
            decisions = tuple(
                ItemAssessment(
                    item_id=item_id,
                    disposition="clear" if passage.list_name == "list1" else "possible",
                    reason="Specificity assessment failed; source inspection is required.",
                )
                for item_id in item_ids
            )
        clear = [decision.item_id for decision in decisions if decision.disposition == "clear"]
        possible = [decision for decision in decisions if decision.disposition == "possible"]
        uncertain = None
        if possible:
            reasons = tuple(dict.fromkeys(decision.reason for decision in possible))
            uncertain = (
                ", ".join(decision.item_id for decision in possible) + ": " + reasons[0]
                if len(reasons) == 1
                else f"{len(possible)} item matches remain possible. {reasons[0]} "
                "See item-level color evidence for the remaining reasons."
            )
        color: Literal["red", "yellow"] = "red" if clear else "yellow"
        names: tuple[EngineName, ...] = ("rules", "semantic", "ai")
        engines = tuple(name for name in names if any(h.engine == name for h in passage.hits))
        references = {
            hit.item_id: hit.reference
            for hit in sorted(passage.hits, key=lambda h: h.score or 0)
            if hit.reference is not None
        }
        nearest = tuple(sorted(references.values(), key=lambda ref: (-ref.score, ref.item_id))[:3])
        identity = "|".join(
            [
                document.paper_id,
                registry.policy_version,
                profile,
                "source-span-fusion-v1",
                assessor.policy_digest,
                ner_digest or "regex-only",
                as_of.isoformat(),
                passage.list_name,
                str(passage.unit.unit_id),
                str(passage.start),
                str(passage.end),
            ]
        )
        findings.append(
            Finding(
                finding_id="finding:" + hashlib.sha256(identity.encode()).hexdigest(),
                paper_id=document.paper_id,
                list=passage.list_name,
                items=item_ids,
                color=color,
                quote=passage.unit.text[passage.start : passage.end],
                location=_location(passage),
                reason=(
                    "List 1 indicator; red review priority."
                    if passage.list_name == "list1"
                    else "Specific source evidence supports " + ", ".join(clear) + "."
                    if clear
                    else "Possible List 2 match; item applicability requires review."
                ),
                why_unsure=uncertain,
                engines=engines,
                score=nearest[0].score if nearest else None,
                semantic_matches=nearest,
                assessment=ColorAssessment(
                    state="error" if assessment_error else "complete", items=decisions
                ),
            )
        )
    return tuple(findings), FusionInfo(
        policy_digest=assessor.policy_digest,
        as_of_utc_date=as_of,
        ner_state=assessor.ner_state if needs_ner else "not_used",
        ner_model_digest=ner_digest,
        state="error" if failed else "complete",
    )
