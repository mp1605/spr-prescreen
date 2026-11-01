"""Neutral key-format objects. No source paths, detector state, or exemplar bank."""

from __future__ import annotations

from dataclasses import dataclass


class KeyFormatError(ValueError):
    """Fail closed when key formatting cannot be interpreted without guessing."""


@dataclass(frozen=True)
class KeyRun:
    start: int
    end: int
    bold: bool
    superscript: bool = False


@dataclass(frozen=True)
class KeyParagraph:
    text: str
    runs: tuple[KeyRun, ...]
    superscript_required: bool


@dataclass(frozen=True)
class KeyTable:
    rows: tuple[tuple[str, ...], ...]
    paragraphs: tuple[KeyParagraph, ...] = ()


KeyBlock = KeyParagraph | KeyTable
