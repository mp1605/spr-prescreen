"""One-to-one maximum-cardinality passage matching, independent of the detectors."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from rapidfuzz.fuzz import partial_ratio

from backend.core.models import Finding
from backend.eval.models import GoldTrigger, Passage


def _tokens(quote: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", quote).casefold()
    normalized = normalized.translate(dict.fromkeys(map(ord, "\u200b\ufeff\u2060\u00ad")))
    return re.findall(r"\w+", normalized)


def text_similarity(predicted: str, gold: str) -> float:
    p, g = _tokens(predicted), _tokens(gold)
    if not g or not p:
        return 0.0
    overlap = sum((Counter(p) & Counter(g)).values()) / len(g)
    fuzzy = partial_ratio(" ".join(p), " ".join(g)) / 100.0
    return max(overlap / 0.50, fuzzy / 0.80)


def grouped_passages(findings: tuple[Finding, ...]) -> tuple[Passage, ...]:
    """Deduplicate identical evidence across lists before trigger-level scoring."""
    groups: dict[tuple[int | None, int | None, int, int, str], list[Finding]] = {}
    for finding in findings:
        loc = finding.location
        key = (loc.page, loc.paragraph, loc.char_start, loc.char_end, finding.quote)
        groups.setdefault(key, []).append(finding)
    paired: list[list[Finding]] = []
    for evidence in groups.values():
        by_list = {name: [f for f in evidence if f.list == name] for name in ("list1", "list2")}
        for index in range(max(len(group) for group in by_list.values())):
            paired.append([group[index] for group in by_list.values() if index < len(group)])
    return tuple(
        Passage(
            finding_ids=tuple(f.finding_id for f in group),
            quote=group[0].quote,
            items=tuple(sorted({i for f in group for i in f.items})),
            color="red" if any(f.color == "red" for f in group) else "yellow",
        )
        for group in paired
    )


def match_passages(
    predictions: tuple[Passage, ...], gold: tuple[GoldTrigger, ...]
) -> dict[int, int]:
    """Return gold-index → prediction-index. One broad flag can match only one trigger."""
    edges: list[list[int]] = []
    for passage in predictions:
        candidates = [
            n
            for n, trigger in enumerate(gold)
            if set(passage.items) & set(trigger.items)
            and text_similarity(passage.quote, trigger.quote) >= 1.0
        ]
        edges.append(
            sorted(
                candidates,
                key=lambda n: (-text_similarity(passage.quote, gold[n].quote), gold[n].tag),
            )
        )
    matched: dict[int, int] = {}

    def augment(prediction: int, visited: set[int]) -> bool:
        for target in edges[prediction]:
            if target in visited:
                continue
            visited.add(target)
            if target not in matched or augment(matched[target], visited):
                matched[target] = prediction
                return True
        return False

    for index in range(len(predictions)):
        augment(index, set())
    return matched
