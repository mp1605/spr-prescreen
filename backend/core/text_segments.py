"""Deterministic span selection; no policy detection, network, or learned examples."""

from __future__ import annotations

import re
from collections.abc import Iterator

from backend.core.ingest_models import ExcludedSpan, Segment, SourceUnit
from backend.core.models import Location


def excluded_noise(text: str) -> tuple[ExcludedSpan, ...]:
    patterns: tuple[tuple[str, str], ...] = (
        (
            r"(?im)^[ \t]*AI-GENERATED FAKE CONTENT FOR EDUCATIONAL PURPOSES ONLY[^\n]*",
            "educational_banner",
        ),
        (r"(?i)\(fictional author\)", "fictional_author"),
        (r"(?im)^[ \t]*(?:(?:\[\d+\]|\d+[.)]?)\s*)?Fictional source:[^\n]*", "fictional_source"),
        (r"(?im)^[ \t]*Page[ \t]+\d+(?:[ \t]+of[ \t]+\d+)?[ \t]*$", "page_footer"),
    )
    spans = []
    for pattern, reason in patterns:
        for match in re.finditer(pattern, text):
            spans.append(
                ExcludedSpan.model_validate(
                    dict(
                        char_start=match.start(),
                        char_end=match.end(),
                        reason=reason,
                    )
                )
            )
    # A banner can contain the author tag. Retain only disjoint, maximal removals.
    kept: list[ExcludedSpan] = []
    for span in sorted(spans, key=lambda s: (s.char_start, -s.char_end)):
        if not kept or span.char_start >= kept[-1].char_end:
            kept.append(span)
    return tuple(kept)


def _visible_intervals(text: str, excluded: tuple[ExcludedSpan, ...]) -> Iterator[tuple[int, int]]:
    start = 0
    for span in excluded:
        if start < span.char_start:
            yield start, span.char_start
        start = span.char_end
    if start < len(text):
        yield start, len(text)


def _sentence_spans(text: str, start: int, end: int, *, pdf: bool) -> Iterator[tuple[int, int]]:
    """Keep abbreviations together; line wraps do not alter source offsets."""
    abbreviations = {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "gen",
        "col",
        "maj",
        "capt",
        "lt",
        "sgt",
        "etc",
        "vs",
        "fig",
        "no",
    }
    cursor = start
    boundary = re.compile(r"""[.!?]+[”’"')\]]*(?=\s|$)|\n[ \t]*\n""")
    for match in boundary.finditer(text, start, end):
        stop = match.end()
        prefix = text[cursor:stop].rstrip()
        if pdf and match.group().startswith("\n"):
            before = text[cursor : match.start()].rstrip(" \t\r\n\u200b\ufeff\u2060")
            after = text[stop:end].lstrip(" \t\r\n\u200b\ufeff\u2060")
            # MuPDF can split a styled word into a separate block in the middle of a sentence.
            if (
                before
                and after
                and before[-1] not in ".!?"
                and (after[0].islower() or (before.endswith("-") and after[0].isdigit()))
            ):
                continue
        if match.group().startswith("."):
            token = re.search(r"([A-Za-z.]+)\.$", prefix)
            if token and (
                token[1].lower() in abbreviations
                or re.fullmatch(r"(?:[A-Za-z]\.)*[A-Za-z]", token[1])
            ):
                continue
        yield cursor, stop
        cursor = stop
    if cursor < end:
        yield cursor, end


def sentence_intervals(
    text: str, start: int, end: int, *, pdf: bool = False
) -> tuple[tuple[int, int], ...]:
    return tuple(_sentence_spans(text, start, end, pdf=pdf))


def segments_for(unit: SourceUnit) -> tuple[Segment, ...]:
    segments = []
    for lo, hi in _visible_intervals(unit.text, unit.excluded):
        for start, end in _sentence_spans(unit.text, lo, hi, pdf=unit.page is not None):
            while start < end and unit.text[start].isspace():
                start += 1
            while end > start and unit.text[end - 1].isspace():
                end -= 1
            quote = unit.text[start:end]
            if not any(c.isalnum() for c in quote):
                continue
            rectangles = tuple(
                w.bbox for w in unit.words if w.char_start < end and start < w.char_end
            )
            if unit.page is not None and not rectangles:
                continue
            segments.append(
                Segment(
                    segment_id=f"u{unit.unit_id}:{start}-{end}",
                    unit_id=unit.unit_id,
                    text=quote,
                    location=Location(
                        page=unit.page,
                        paragraph=unit.paragraph,
                        heading=unit.heading,
                        char_start=start,
                        char_end=end,
                        bbox=rectangles if unit.page is not None else None,
                    ),
                )
            )
    return tuple(segments)
