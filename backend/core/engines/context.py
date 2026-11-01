"""Guard context is source-local and independent of evaluation data."""

from __future__ import annotations

import re
from typing import Literal

from backend.core.engines.normalize import normalize
from backend.core.ingest_models import ParseResult, SourceUnit


class SourceContext:
    def __init__(self, document: ParseResult) -> None:
        self.units = {u.unit_id: u for u in document.units}
        self.ordered = document.units
        self.positions = {u.unit_id: i for i, u in enumerate(document.units)}
        self.normalized = {u.unit_id: normalize(u.text) for u in document.units}
        self.document_context = {
            part: " ".join(
                normalize(
                    " ".join(
                        u.text[a:b]
                        for a, b in zip(
                            (0, *(s.char_end for s in u.excluded)),
                            (*(s.char_start for s in u.excluded), len(u.text)),
                            strict=True,
                        )
                    )
                ).text
                for u in document.units
                if u.part == part
            )
            for part in {u.part for u in document.units}
        }

    def neighbors(self, unit_id: int) -> tuple[SourceUnit, ...]:
        unit = self.units[unit_id]
        index = self.positions[unit_id]
        return tuple(
            other
            for other in self.ordered[max(0, index - 2) : index + 3]
            if other.part == unit.part
            and (other.heading == unit.heading or other.unit_id == unit_id)
        )

    def text(self, unit_id: int, scope: Literal["unit", "nearby", "document"]) -> str:
        unit = self.units[unit_id]
        if scope == "document":
            return self.document_context[unit.part]
        selected = self.neighbors(unit_id) if scope == "nearby" else (unit,)
        return " ".join(
            normalize(u.heading or "").text + " " + self.normalized[u.unit_id].text
            for u in selected
        )

    def letter_sequence(self, unit_id: int, start: int) -> bool:
        tokens: list[tuple[int, int, int, str]] = []
        for unit in self.neighbors(unit_id):
            normalized = self.normalized[unit.unit_id]
            for match in re.finditer(r"\(([A-Za-z])\)", normalized.text):
                lo, hi = normalized.source_span(match.start(), match.end())
                tokens.append((unit.unit_id, lo, hi, match[1].upper()))
        for offset in range(max(0, len(tokens) - 2)):
            group = tokens[offset : offset + 3]
            if not any(t[0] == unit_id and t[1] == start for t in group):
                continue
            letters = [ord(t[3]) for t in group]
            if letters[1] - letters[0] != 1 or letters[2] - letters[1] != 1:
                continue
            if all(
                a[0] != b[0] or b[1] - a[2] <= 160 for a, b in zip(group, group[1:], strict=False)
            ):
                return True
        return False

    def marking_allowed(
        self, unit_id: int, start: int, end: int, token: str, pattern: re.Pattern[str]
    ) -> bool:
        if token.upper() == "(TS)":
            # An explicitly expanded ordinary acronym is not a portion marking.
            prefix = self.units[unit_id].text[:start]
            expansion = re.search(r"\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\s*$", prefix)
            if (
                expansion
                and "".join(word[0] for word in expansion.groups()) == "TS"
                and expansion.group().strip().casefold() != "top secret"
            ):
                return False
        if token.upper() not in ("(C)", "(S)"):
            return True
        if token not in ("(C)", "(S)") or self.letter_sequence(unit_id, start):
            return False
        unit = self.units[unit_id]
        prefix = unit.text[:start]
        if unit.page is not None:
            paragraphs = list(re.finditer(r"\n\s*\n", prefix))
            if paragraphs:
                prefix = prefix[paragraphs[-1].end() :]
        if not normalize(prefix).text.strip():
            return True
        normalized = self.normalized[unit_id]
        for other in pattern.finditer(normalized.text):
            lo, hi = normalized.source_span(other.start(), other.end())
            if lo == start:
                continue
            a, b = (hi, start) if hi <= start else (end, lo)
            if 0 <= b - a <= 12 and not normalize(unit.text[a:b]).text.strip(" ,;:/-"):
                return True
        return False

    def byline_allowed(self, unit_id: int, start: int, end: int) -> bool:
        unit = self.units[unit_id]
        if unit.part not in ("pdf", "word/document.xml"):
            return False
        line_start = unit.text.rfind("\n", 0, start) + 1
        line_end = unit.text.find("\n", end)
        if line_end == -1:
            line_end = len(unit.text)
        prefix = normalize(unit.text[line_start:start]).text.strip()
        suffix = normalize(unit.text[end:line_end]).text.strip(" ,:;-")
        # Affiliation/title and stripped author annotations are not part of the name.
        suffix = suffix.split(",", 1)[0]
        suffix = re.sub(r"\([^)]*\)", "", suffix).strip()
        cue = re.match(r"(?i)^(?:by\b|authors?\s*:)\s*", prefix)
        if cue:
            name_text = prefix[cue.end() :] + " " + suffix
            names = re.findall(r"[^\W\d_][\w'’-]*\.?", name_text)
            if names and len(names) <= 7 and all(name[0].isupper() for name in names):
                return True
        front = [u for u in self.ordered if u.part == unit.part and u.text.strip()][:8]
        if unit.page is not None:
            if unit.page != 1 or len(unit.text[:start].splitlines()) > 20:
                return False
        elif unit not in front:
            return False
        # A standalone opening rank/name line is a possible byline; prose mentions are excluded.
        surrounding = (prefix + " " + suffix).strip(" ,")
        words = re.findall(r"[^\W\d_][\w'’-]*\.?", surrounding)
        return bool(words) and len(words) <= 7 and all(word[0].isupper() for word in words)
