"""E1: compile registry detectors once, then report source-bound indicators only."""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.core.engines.base import Hit
from backend.core.engines.context import SourceContext
from backend.core.engines.normalize import normalize
from backend.core.ingest_models import ParseResult
from backend.core.policy import ListName
from backend.core.rules_loader import Detector, PolicyError, RuleItem, RuleRegistry


@dataclass(frozen=True)
class CompiledDetector:
    source: Detector
    pattern: re.Pattern[str]
    context: re.Pattern[str] | None


def _compile(detector: Detector) -> CompiledDetector:
    flags = 0 if detector.case_sensitive else re.IGNORECASE
    if detector.kind == "regex":
        pattern = detector.pattern or ""
    else:
        alternatives = [
            re.escape(normalize(term).text).replace(r"\ ", r"\s+")
            for term in sorted(detector.terms, key=len, reverse=True)
        ]
        pattern = r"(?<!\w)(?:" + "|".join(alternatives) + r")(?!\w)"
    return CompiledDetector(
        detector,
        re.compile(pattern, flags),
        re.compile(detector.context_pattern, re.IGNORECASE) if detector.context_pattern else None,
    )


class RulesEngine:
    def __init__(self, registry: RuleRegistry) -> None:
        self.rules_version = registry.policy_version
        self.compiled: dict[str, tuple[CompiledDetector, ...]] = {}
        for item in (*registry.list1, *registry.list2):
            if not item.detectors:
                raise PolicyError(f"No rules detectors configured for official item {item.id}")
            try:
                self.compiled[item.id] = tuple(_compile(d) for d in item.detectors)
            except re.error as exc:
                raise PolicyError(f"Cannot compile detectors for official item {item.id}") from exc

    def run(
        self, document: ParseResult, list_name: ListName, items: tuple[RuleItem, ...]
    ) -> tuple[Hit, ...]:
        context = SourceContext(document)
        hits: list[Hit] = []
        for segment in document.segments:
            normalized = normalize(segment.text)
            for item in items:
                for detector in self.compiled[item.id]:
                    if detector.context is not None and not detector.context.search(
                        context.text(segment.unit_id, detector.source.context_scope)
                    ):
                        continue
                    for match in detector.pattern.finditer(normalized.text):
                        start, end = normalized.source_span(match.start(), match.end())
                        start += segment.location.char_start
                        end += segment.location.char_start
                        if item.id == "L1-5" and match.group().casefold().startswith("draft"):
                            prefix = normalized.text[max(0, match.start() - 140) : match.start()]
                            if re.search(
                                r"(?:\b(?:can|will|could|would|may|to)\s+|"
                                r"\b(?:sort|summarize|generate|analyze|write|produce)\b.{0,100},\s*)$",
                                prefix,
                                re.I,
                            ):
                                # The verb 'draft' does not identify draft source material.
                                continue
                        guard = detector.source.guard
                        if guard == "classification_marking" and not context.marking_allowed(
                            segment.unit_id, start, end, match.group(), detector.pattern
                        ):
                            continue
                        if guard == "byline" and not context.byline_allowed(
                            segment.unit_id, start, end
                        ):
                            continue
                        hits.append(
                            Hit(
                                segment_id=segment.segment_id,
                                item_id=item.id,
                                list=list_name,
                                detector=detector.source.name,
                                char_start=start,
                                char_end=end,
                            )
                        )
        return tuple(hits)
