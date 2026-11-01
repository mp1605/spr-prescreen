"""Match normalized Unicode while retaining offsets into unchanged source text."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Normalized:
    text: str
    spans: tuple[tuple[int, int], ...]

    def source_span(self, start: int, end: int) -> tuple[int, int]:
        if not 0 <= start < end <= len(self.spans):
            raise ValueError("Normalized match is outside the source map")
        return self.spans[start][0], self.spans[end - 1][1]


def normalize(text: str) -> Normalized:
    output: list[str] = []
    spans: list[tuple[int, int]] = []
    for offset, original in enumerate(text):
        if original in "\u200b\ufeff\u2060\u00ad":
            continue
        for char in unicodedata.normalize("NFKC", original):
            if char in "\u2010\u2011\u2012\u2013\u2014\ufe63\uff0d":
                char = "-"
            elif char in "\u2018\u2019":
                char = "'"
            if char.isspace():
                char = " "
                if output and output[-1] == " ":
                    spans[-1] = (spans[-1][0], offset + 1)
                    continue
            output.append(char)
            spans.append((offset, offset + 1))
    return Normalized("".join(output), tuple(spans))
