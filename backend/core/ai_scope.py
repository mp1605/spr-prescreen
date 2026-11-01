"""Select source by current baseline evidence, never by filenames, keys or past outcomes."""

from collections import defaultdict
from typing import Literal

from backend.core.ingest_models import ParseResult, Segment
from backend.core.models import Finding, PaperResult


def source_for_ai(
    document: ParseResult, baseline: PaperResult, scope: Literal["full", "selective"]
) -> ParseResult:
    if scope == "full":
        return document
    grouped: dict[tuple[int | None, int | None], list[Finding]] = defaultdict(list)
    for flag in baseline.findings:
        grouped[(flag.location.page, flag.location.paragraph)].append(flag)
    units = {u.unit_id: u for u in document.units}
    chosen: set[int] = set()
    segments = document.segments
    for index, segment in enumerate(segments):
        location = segment.location
        matches = grouped.get((location.page, location.paragraph), ())
        if not any(
            location.char_start < f.location.char_end
            and f.location.char_start < location.char_end
            and units[segment.unit_id].text[f.location.char_start : f.location.char_end] == f.quote
            for f in matches
        ):
            continue
        chosen.add(index)
        unit = units[segment.unit_id]
        for neighbor in (index - 1, index + 1):
            if 0 <= neighbor < len(segments):
                other = units[segments[neighbor].unit_id]
                if other.part == unit.part and other.heading == unit.heading:
                    chosen.add(neighbor)
    selected: tuple[Segment, ...] = tuple(s for i, s in enumerate(segments) if i in chosen)
    return document.model_copy(update={"segments": selected})
