"""Extract literal source facts. Similarity alone never establishes a clear List 2 match."""

from __future__ import annotations

import calendar
import re
from datetime import date
from pathlib import Path
from threading import RLock
from typing import Literal

from backend.core.color_models import FeatureKind, SpecificityFeature
from backend.core.engines.context import SourceContext
from backend.core.engines.normalize import normalize
from backend.core.ingest_models import SourceUnit
from backend.core.named_entities import EntityProvider, LocalEntities
from backend.core.rules_loader import RuleRegistry
from backend.core.specificity_patterns import DATE, FUTURE, MONTH_ONLY, PATTERNS, URI
from backend.core.specificity_policy import policy_digest
from backend.core.text_segments import sentence_intervals


class SpecificityEngine:
    def __init__(
        self,
        root: Path,
        registry: RuleRegistry,
        *,
        entities: EntityProvider | None = None,
        use_local_entities: bool = True,
    ) -> None:
        self.root, self.registry = root, registry
        self.provider = entities
        self.use_local_entities = use_local_entities
        self.ner_state: Literal["not_used", "ready", "unavailable"] = "not_used"
        self.ner_model_digest: str | None = None
        self.policy_digest = policy_digest()
        self.lock = RLock()
        self.rank_patterns = tuple(
            re.compile(detector.pattern or "", 0 if detector.case_sensitive else re.I)
            for item in registry.list2
            for detector in item.detectors
            if detector.guard == "byline"
        )

    def named(self, text: str) -> tuple[SpecificityFeature, ...]:
        with self.lock:
            if self.ner_state == "unavailable":
                return ()
            try:
                if self.provider is None:
                    if not self.use_local_entities:
                        return ()
                    self.provider = LocalEntities(self.root)
                entities = self.provider.entities(text)
                result = []
                for entity in entities:
                    if not 0 <= entity.start < entity.end <= len(text):
                        raise ValueError("Entity model returned invalid source coordinates")
                    if entity.kind != "location":
                        continue  # An arbitrary organization is not proof of a DoD collaborator.
                    result.append(
                        SpecificityFeature(
                            kind=entity.kind,
                            text=text[entity.start : entity.end],
                            char_start=entity.start,
                            char_end=entity.end,
                            source="local_ner",
                        )
                    )
                self.ner_state, self.ner_model_digest = "ready", self.provider.identity
                return tuple(result)
            except (OSError, ValueError, RuntimeError):
                self.ner_state = "unavailable"
                return ()

    def features(
        self, unit: SourceUnit, start: int, end: int, *, as_of: date, context: SourceContext
    ) -> tuple[SpecificityFeature, ...]:
        text = unit.text[start:end]
        if len(text) > 50_000:
            raise ValueError("Specificity passage resource limit exceeded")
        normalized = normalize(text)
        uri_spans = [match.span() for match in URI.finditer(normalized.text)]
        facts: list[SpecificityFeature] = []

        def add(kind: FeatureKind, left: int, right: int) -> None:
            if any(left < hi and lo < right for lo, hi in uri_spans):
                return
            lo, hi = normalized.source_span(left, right)
            facts.append(
                SpecificityFeature(
                    kind=kind, text=text[lo:hi], char_start=start + lo, char_end=start + hi
                )
            )
            if len(facts) > 512:
                raise ValueError("Specificity feature resource limit exceeded")

        for kind, pattern in PATTERNS:
            for match in pattern.finditer(normalized.text):
                if kind == "date" and any(
                    lo <= match.start() < match.end() <= hi
                    for lo, hi in (m.span() for m in DATE.finditer(normalized.text))
                ):
                    # The calendar parser below owns full dates, including invalid ones.
                    continue
                if kind == "uncertainty" and match.group().lower() in {"could", "would"}:
                    if (
                        match.group().lower() == "would"
                        and re.search(
                            r"\b(?:is|are)\s+scheduled\s+to\b[^.!?]+\band\b[^.!?]*$",
                            normalized.text[: match.start()],
                            re.I,
                        )
                        and re.match(
                            r"would\s+(?:help|ease|improve|reduce)\b",
                            normalized.text[match.start() :],
                            re.I,
                        )
                    ):
                        # A hoped-for benefit does not negate an explicit scheduled fact.
                        continue
                    lo, hi = normalized.source_span(*match.span())
                    sentence = next(
                        (
                            span
                            for span in sentence_intervals(
                                text, 0, len(text), pdf=unit.page is not None
                            )
                            if span[0] <= lo < hi <= span[1]
                        ),
                        (lo, hi),
                    )
                    if re.search(
                        r"\b(?:measured|found|discovered|demonstrated|revealed|revealing|reported|"
                        r"rehearsed|noted|identified)\b",
                        text[sentence[0] : sentence[1]],
                        re.I,
                    ):
                        # A reported capability/failure need not be hypothetical.
                        continue
                if kind == "quantity":
                    prefix = normalized.text[max(0, match.start() - 35) : match.start()]
                    number = re.match(r"\d+", match.group())
                    if re.search(
                        r"\b(?:chapter|section|figure|table|page|reference)\s*$", prefix, re.I
                    ):
                        continue
                    if (
                        number
                        and 1900 <= int(number.group()) <= 2099
                        and not re.search(
                            r"\b(?:only|total|of|has|have|operates|assigned|authorized|available)\s*$",
                            prefix,
                            re.I,
                        )
                    ):
                        add("uncertainty", *match.span())
                        continue
                add(kind, *match.span())
        for match in DATE.finditer(normalized.text):
            value = _date(match.group())
            if value is None:
                continue
            add("date", *match.span())
            # A named month without a day is current/future if its month has not passed.
            month_only = bool(re.fullmatch(r"[A-Za-z]+\s+\d{4}", match.group()))
            if (
                value >= as_of
                or month_only
                and (value.year, value.month) >= (as_of.year, as_of.month)
            ):
                add("future_date", *match.span())
        for match in MONTH_ONLY.finditer(normalized.text):
            lo, hi = normalized.source_span(*match.span())
            sentence = next(
                (
                    bounds
                    for bounds in sentence_intervals(text, 0, len(text), pdf=unit.page is not None)
                    if bounds[0] <= lo < hi <= bounds[1]
                ),
                (lo, hi),
            )
            surrounding = text[max(sentence[0], lo - 80) : min(sentence[1], hi + 30)]
            if not DATE.search(normalize(surrounding).text) and FUTURE.search(surrounding):
                add("future_date", *match.span())
        for pattern in self.rank_patterns:
            for match in pattern.finditer(normalized.text):
                lo, hi = normalized.source_span(*match.span())
                if context.byline_allowed(unit.unit_id, start + lo, start + hi):
                    add("rank", *match.span())
        for fact in self.named(text):
            raw_uri = [normalized.source_span(lo, hi) for lo, hi in uri_spans]
            if any(fact.char_start < hi and lo < fact.char_end for lo, hi in raw_uri):
                continue
            facts.append(
                fact.model_copy(
                    update={
                        "char_start": fact.char_start + start,
                        "char_end": fact.char_end + start,
                    }
                )
            )
        unique = {(f.kind, f.char_start, f.char_end): f for f in facts}
        return tuple(sorted(unique.values(), key=lambda f: (f.char_start, f.char_end, f.kind)))


def _date(text: str) -> date | None:
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text)
        month, remainder = text.split(maxsplit=1)
        parts = remainder.replace(",", "").split()
        number = next(
            index for index, name in enumerate(calendar.month_name) if name.lower() == month.lower()
        )
        return date(int(parts[-1]), number, int(parts[0]) if len(parts) > 1 else 1)
    except (ValueError, StopIteration):
        return None
