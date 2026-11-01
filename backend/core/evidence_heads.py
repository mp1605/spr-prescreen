"""Prefer body evidence over a redundant topic heading; preserve all List 1 hits."""

import re

from backend.core.engines.base import Hit
from backend.core.ingest_models import ParseResult


def substantive_hits(hits: tuple[Hit, ...], document: ParseResult) -> tuple[Hit, ...]:
    segments = document.segments
    units = {u.unit_id: u for u in document.units}
    anchors = {(h.segment_id, h.item_id) for h in hits if h.list == "list2"}
    redundant = set()
    for n, segment in enumerate(segments):
        text = segment.text.strip()
        if not text or len(text.split()) > 7 or re.search(r"[\d.!?():/]", text):
            continue
        following = next((s for s in segments[n + 1 : n + 3] if s.text.strip()), None)
        if (
            not following
            or len(following.text.split()) < 15
            or units[following.unit_id].part != units[segment.unit_id].part
        ):
            continue
        for identifier in {item for sid, item in anchors if sid == segment.segment_id}:
            if (following.segment_id, identifier) in anchors:
                redundant.add((segment.segment_id, identifier))
    return tuple(
        h
        for h in hits
        if h.list == "list1" or (h.segment_id, h.item_id) not in redundant
    )
