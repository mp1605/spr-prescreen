"""Shared CLI boundaries: explicit sources and private atomic report files."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Protocol


class TextWriter(Protocol):
    def write(self, text: str) -> int: ...


def source_allowed(path: Path) -> bool:
    parts = {part.casefold() for part in path.resolve().parts}
    stem = path.stem.casefold()
    return not (
        parts & {"keys", "answer_keys", "answer-keys", "holdout"}
        or stem.endswith("_key")
        or "answer_key" in stem
        or "expected_result" in stem
        or path.name.casefold() == "index.csv"
    )


def _write_private(output: Path, render: Callable[[TextWriter], object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=output.parent, prefix=".report-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            render(handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_report(output: Path, payload: object) -> None:
    def render(handle: TextWriter) -> None:
        json.dump(payload, handle, ensure_ascii=True, indent=2)
        handle.write("\n")

    _write_private(output, render)


def write_text_report(output: Path, text: str) -> None:
    _write_private(output, lambda handle: handle.write(text))
