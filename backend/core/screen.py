"""Ordered E1/E2 screening. Engine failure never suppresses another engine or list."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime
from time import perf_counter

from backend.core.engines.ai import AISession
from backend.core.engines.base import Engine, Hit
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticSession, digest
from backend.core.fuse import fuse_findings
from backend.core.ingest_models import ParseResult, Segment
from backend.core.models import Color, EngineName, Finding, FlagCount, PaperLabel, PaperResult
from backend.core.policy import ListName
from backend.core.rules_loader import PolicyError, RuleItem, RuleRegistry
from backend.core.specificity import SpecificityEngine


def _validated_hits(
    hits: tuple[Hit, ...],
    segments: dict[str, Segment],
    items: tuple[RuleItem, ...],
    list_name: ListName,
    engine_name: str = "rules",
) -> tuple[tuple[Hit, ...], bool]:
    allowed = {item.id: item for item in items}
    valid: list[Hit] = []
    invalid = False
    for hit in hits:
        segment = segments.get(hit.segment_id)
        if (
            segment is None
            or hit.item_id not in allowed
            or hit.list != list_name
            or hit.engine != engine_name
            or (hit.reference is not None and hit.reference.text != allowed[hit.item_id].text)
            or not segment.location.char_start
            <= hit.char_start
            < hit.char_end
            <= segment.location.char_end
        ):
            invalid = True
        else:
            valid.append(hit)
    return tuple(valid), invalid


def _findings(
    document: ParseResult,
    hits: tuple[Hit, ...],
    registry: RuleRegistry,
    list_name: ListName,
    profile: str = "",
) -> tuple[Finding, ...]:
    grouped: dict[str, list[Hit]] = defaultdict(list)
    for hit in hits:
        grouped[hit.segment_id].append(hit)
    findings: list[Finding] = []
    for segment in document.segments:
        group = grouped.get(segment.segment_id)
        if not group:
            continue
        identity = f"{document.paper_id}|{registry.policy_version}|{list_name}|{segment.segment_id}"
        if profile:
            identity += "|" + profile
        names = "; ".join(sorted({hit.detector for hit in group}))
        references = tuple(
            sorted(
                (hit.reference for hit in group if hit.reference is not None),
                key=lambda ref: (-ref.score, ref.item_id),
            )[:3]
        )
        engine_names: tuple[EngineName, ...] = ("rules", "semantic")
        engines = tuple(name for name in engine_names if any(h.engine == name for h in group))
        uncertainty = (
            "Semantic similarity is an uncalibrated retrieval signal, not a probability or "
            "determination that the item applies. A reviewer must inspect the source."
            if references
            else "Pattern indicator only; item applicability and sensitive specificity require "
            "human review. Specificity checks are not active in this screening stage."
        )
        findings.append(
            Finding(
                finding_id="finding:" + hashlib.sha256(identity.encode()).hexdigest(),
                paper_id=document.paper_id,
                list=list_name,
                items=tuple(sorted({hit.item_id for hit in group})),
                color="red" if list_name == "list1" else "yellow",
                quote=segment.text,
                location=segment.location,
                reason=f"Official-list indicator: {names}. A reviewer determines applicability.",
                why_unsure=uncertainty if list_name == "list2" or references else None,
                engines=engines,
                score=references[0].score if references else None,
                semantic_matches=references,
            )
        )
    return tuple(findings)


def screen_document(
    document: ParseResult,
    registry: RuleRegistry,
    *,
    engine: Engine | None = None,
    progress: Callable[[ListName], None] | None = None,
    semantic: SemanticSession | None = None,
    specificity: SpecificityEngine | None = None,
    as_of: date | None = None,
    ai: AISession | None = None,
    ai_progress: Callable[[], None] | None = None,
) -> PaperResult:
    start = perf_counter()
    if document.file_type is None:
        raise ValueError("Unsupported inputs do not have a paper-screening result")
    engine = engine or RulesEngine(registry)
    if engine.rules_version != registry.policy_version:
        raise PolicyError("Detector version does not match the active rules registry")
    if semantic and semantic.rules_version != registry.policy_version:
        raise PolicyError("Semantic version does not match the active rules registry")
    if specificity and specificity.registry.policy_version != registry.policy_version:
        raise PolicyError("Specificity version does not match the active rules registry")
    segments = {segment.segment_id: segment for segment in document.segments}
    findings: list[Finding] = []
    all_hits: list[Hit] = []
    incomplete = [issue.message for issue in document.issues]
    trace: list[str] = []
    lists: tuple[tuple[ListName, tuple[RuleItem, ...]], ...] = (
        ("list1", registry.list1),
        ("list2", registry.list2),
    )
    for list_name, items in lists:
        if progress is not None:
            progress(list_name)
        combined: list[Hit] = []
        failed = False
        for name, current in (("rules", engine), ("semantic", semantic)):
            if current is None:
                continue
            try:
                hits, invalid = _validated_hits(
                    current.run(document, list_name, items), segments, items, list_name, name
                )
                combined.extend(hits)
                if invalid:
                    raise ValueError("Engine supplied invalid source references")
            except Exception:
                failed = True
                if name == "semantic" and semantic is not None:
                    semantic.failed = True
                incomplete.append(
                    f"{list_name} {name} screening did not complete reliably; "
                    "human source inspection is required."
                )
        profile = (
            digest(
                semantic.info().model_dump(
                    mode="json", exclude={"state", "segments", "chunks", "cache_state", "seconds"}
                )
            )
            if semantic
            else ""
        )
        all_hits.extend(combined)
        if specificity is None:
            findings.extend(_findings(document, tuple(combined), registry, list_name, profile))
        trace.append(f"{list_name}:{'error' if failed else 'done'}")
    fusion = None
    if specificity:
        fused, fusion = fuse_findings(
            document,
            tuple(all_hits),
            registry,
            specificity,
            as_of=as_of or datetime.now(UTC).date(),
            profile=profile,
        )
        findings = list(fused)
        if fusion.state == "error":
            incomplete.append(
                "Specificity assessment did not complete reliably; source inspection is required."
            )
    red = sum(f.color == "red" for f in findings)
    yellow = len(findings) - red
    color: Color = "red" if red else "yellow" if yellow or incomplete else "green"
    label: PaperLabel = (
        "Flag identified"
        if red
        else "Incomplete"
        if incomplete
        else "Potential flag"
        if yellow
        else "No flags found"
    )
    result = PaperResult(
        paper_id=document.paper_id,
        file_name=document.file_name,
        file_type=document.file_type,
        color=color,
        label=label,
        flag_count=FlagCount(total=len(findings), red=red, yellow=yellow),
        lists_checked=("list1", "list2"),
        trace=tuple(trace),
        incomplete_pages=document.incomplete_pages,
        incomplete_reasons=tuple(dict.fromkeys(incomplete)),
        ai_state="off",
        rules_version=registry.policy_version,
        seconds=perf_counter() - start,
        findings=tuple(findings),
        screening_stage="rules_semantic" if semantic else "rules_only",
        semantic=semantic.info() if semantic else None,
        fusion=fusion,
    )

    if ai is not None:
        if ai_progress is not None:
            ai_progress()
        return ai.run(document, result, registry, specificity)
    return result
