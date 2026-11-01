"""Resolve only official references; ambiguous descriptions do not become guessed IDs."""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz.fuzz import token_sort_ratio

from backend.core.policy import OFFICIAL_IDS
from backend.core.rules_loader import RuleRegistry
from backend.eval.key_format import KeyFormatError


def _plain(text: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def _official(group: str, number: str) -> str:
    value = f"L1-{int(number)}" if group == "1" else f"L2-{int(number):02}"
    if value not in OFFICIAL_IDS:
        raise KeyFormatError("Key references an unknown official item ID")
    return value


def resolve_items(text: str, registry: RuleRegistry) -> tuple[str, ...]:
    found: set[str] = set()
    for match in re.finditer(r"\bL([12])\s*[-–—]\s*(\d{1,2})\b", text, re.IGNORECASE):
        found.add(_official(match[1], match[2]))
    reference = re.compile(
        r"\blist\s*([12])\s*[,;:#–—-]?\s*(?:items?\s*)?#?\s*"
        r"(\d{1,2}(?:\s*(?:,|and|&)\s*\d{1,2})*)\b",
        re.IGNORECASE,
    )
    for match in reference.finditer(text):
        found.update(_official(match[1], number) for number in re.findall(r"\d+", match[2]))
    if found:
        return tuple(sorted(found))
    value = _plain(text)
    aliases = [
        (item.id, _plain(alias))
        for item in (*registry.list1, *registry.list2)
        for alias in (item.text, item.text.split("(")[0].strip(), item.category or "")
        if alias
    ]
    exact = {item for item, alias in aliases if alias and f" {alias} " in f" {value} "}
    if exact:
        return tuple(sorted(exact))
    scores = {
        item.id: max(token_sort_ratio(value, alias) for ident, alias in aliases if ident == item.id)
        for item in (*registry.list1, *registry.list2)
    }
    ranked = sorted(scores.items(), key=lambda row: (-row[1], row[0]))
    if len(value) >= 8 and ranked[0][1] >= 90 and ranked[0][1] - ranked[1][1] >= 8:
        return (ranked[0][0],)
    raise KeyFormatError("Policy reference is absent or ambiguous; manual mapping is required")
