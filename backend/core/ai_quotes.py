"""Bind quotes to one unique canonical passage and retain original source coordinates."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Literal

from rapidfuzz.fuzz import partial_ratio_alignment, ratio

from backend.core.ai_models import AIEvidence, AIProposal
from backend.core.color_models import SpecificityFeature
from backend.core.engines.normalize import normalize
from backend.core.ingest_models import ParseResult, Segment


@dataclass(frozen=True)
class VerifiedAI:
    segment: Segment
    evidence: AIEvidence
    features: tuple[SpecificityFeature, ...] = ()


def _occurrences(text: str, quote: str) -> list[tuple[int, int]]:
    matches = []
    start = 0
    while (found := text.find(quote, start)) >= 0:
        matches.append((found, found + len(quote)))
        if len(matches) > 1:
            break
        start = found + 1
    return matches


def _alignment(quote: str, text: str) -> tuple[float, int, int] | None:
    aligned = partial_ratio_alignment(quote, text, score_cutoff=90)
    if aligned is None or aligned.src_end - aligned.src_start < 0.9 * len(quote):
        return None
    left, right = aligned.dest_start, aligned.dest_end
    score = ratio(quote, text[left:right], score_cutoff=90)
    return (float(score), left, right) if score >= 90 else None


def verify_quote(proposal: AIProposal, document: ParseResult, deadline: float) -> VerifiedAI | None:
    matches: list[tuple[Segment, int, int]] = []
    kind: Literal["exact", "normalized", "fuzzy"] = "exact"
    score = 100.0
    for segment in document.segments:
        if time.monotonic() > deadline:
            raise TimeoutError
        matches.extend(
            (segment, start, end) for start, end in _occurrences(segment.text, proposal.quote)
        )
    if not matches:
        kind = "normalized"
        quote = normalize(proposal.quote).text
        for segment in document.segments:
            if time.monotonic() > deadline:
                raise TimeoutError
            source = normalize(segment.text)
            matches.extend(
                (segment, *source.source_span(start, end))
                for start, end in _occurrences(source.text, quote)
            )
    if not matches:
        # Short approximate snippets are too ambiguous to navigate reliably.
        quote = normalize(proposal.quote).text
        if len(quote) < 32 or len(quote.split()) < 6:
            return None
        kind = "fuzzy"
        ranked = []
        for segment in document.segments:
            if time.monotonic() > deadline:
                raise TimeoutError
            source = normalize(segment.text)
            if len(source.text) > 16000:
                continue
            aligned = _alignment(quote, source.text)
            if aligned is None:
                continue
            score, left, right = aligned
            actual = source.text[left:right]
            if re.findall(r"\d+(?:[.,]\d+)*", quote) != re.findall(r"\d+(?:[.,]\d+)*", actual):
                continue
            # A second plausible occurrence, even within the same segment, is ambiguous.
            alternatives = (source.text[:left], source.text[right:])
            if any(_alignment(quote, other) is not None for other in alternatives if other):
                return None
            ranked.append((score, segment, *source.source_span(left, right)))
        ranked.sort(key=lambda row: row[0], reverse=True)
        if not ranked or len(ranked) > 1 and ranked[0][0] - ranked[1][0] < 3:
            return None
        score, segment, left, right = ranked[0]
        matches = [(segment, left, right)]
    if len(matches) != 1:
        return None
    segment, start, end = matches[0]
    evidence = AIEvidence(
        item_id=proposal.item_id,
        quote=segment.text[start:end],
        model_quote=proposal.quote,
        char_start=segment.location.char_start + start,
        char_end=segment.location.char_start + end,
        match=kind,
        similarity=score,
        clear_or_possible=proposal.clear_or_possible,
        reason=proposal.reason,
    )
    return VerifiedAI(segment, evidence)
