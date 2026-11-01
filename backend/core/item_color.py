"""Apply source-bound conditions per item, keeping mixed-certainty items explicit."""

from __future__ import annotations

from backend.core.color_models import ItemAssessment, SpecificityFeature
from backend.core.engines.base import Hit
from backend.core.ingest_models import Segment, SourceUnit
from backend.core.specificity_policy import CONDITIONS, JUDGMENT, NEARBY_CHARACTERS
from backend.core.text_segments import sentence_intervals


def assess_item(
    item_id: str,
    hits: tuple[Hit, ...],
    features: tuple[SpecificityFeature, ...],
    segments: dict[str, Segment],
    unit: SourceUnit,
) -> ItemAssessment:
    if item_id.startswith("L1-"):
        return ItemAssessment(
            item_id=item_id,
            disposition="clear",
            reason="List 1 indicators retain red review priority under the official color rule.",
        )
    if item_id in JUDGMENT:
        return ItemAssessment(item_id=item_id, disposition="possible", reason=JUDGMENT[item_id])
    anchors = [hit for hit in hits if hit.item_id == item_id and hit.engine == "rules"]
    if not anchors:
        return ItemAssessment(
            item_id=item_id,
            disposition="possible",
            reason="Semantic resemblance alone does not establish applicability or specificity.",
        )
    closest: tuple[SpecificityFeature, ...] = ()
    for anchor in anchors:
        segment = segments[anchor.segment_id]
        sentence = next(
            (
                span
                for span in sentence_intervals(
                    unit.text,
                    segment.location.char_start,
                    segment.location.char_end,
                    pdf=unit.page is not None,
                )
                if span[0] <= anchor.char_start < anchor.char_end <= span[1]
            ),
            None,
        )
        if sentence is None:
            continue
        nearby = tuple(
            f
            for f in features
            if sentence[0] <= f.char_start < f.char_end <= sentence[1]
            and max(f.char_start - anchor.char_end, anchor.char_start - f.char_end, 0)
            <= NEARBY_CHARACTERS
        )
        closest = nearby if len(nearby) > len(closest) else closest
        if any(f.kind in {"uncertainty", "negation"} for f in nearby):
            continue
        available = {f.kind for f in nearby}
        for requirement in CONDITIONS[item_id]:
            if set(requirement) <= available:
                evidence = tuple(next(f for f in nearby if f.kind == kind) for kind in requirement)
                return ItemAssessment(
                    item_id=item_id,
                    disposition="clear",
                    evidence=evidence,
                    rule_anchor=SpecificityFeature(
                        kind="topic",
                        text=unit.text[anchor.char_start : anchor.char_end],
                        char_start=anchor.char_start,
                        char_end=anchor.char_end,
                    ),
                    reason="Matched topic with source-bound "
                    + ", ".join(kind.replace("_", " ") for kind in requirement)
                    + ".",
                )
    if any(f.kind in {"uncertainty", "negation"} for f in closest):
        reason = (
            "Conditional, illustrative, negated-disclosure, or ambiguous numeric wording "
            "prevents automatic promotion."
        )
    else:
        options = [
            set(requirement) - {f.kind for f in closest} for requirement in CONDITIONS[item_id]
        ]
        missing = min(options, key=lambda value: (len(value), sorted(value)))
        reason = (
            "Topic identified, but source-bound "
            + ", ".join(sorted(k.replace("_", " ") for k in missing))
            + " is missing or not tied to the same sentence."
        )
    return ItemAssessment(
        item_id=item_id,
        disposition="possible",
        reason=reason,
        evidence=tuple(f for f in closest if f.kind in {"uncertainty", "negation"})[:4],
    )
