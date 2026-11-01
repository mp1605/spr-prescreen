"""Gold JSONL serialization only; dataset loading remains outside the scanner."""

from __future__ import annotations

import json
from pathlib import Path

from backend.cli_io import write_text_report
from backend.eval.models import GoldCase


def gold_jsonl(cases: tuple[GoldCase, ...]) -> str:
    if not cases or len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Gold JSONL requires nonempty unique case IDs")
    return "".join(
        json.dumps(case.model_dump(mode="json"), ensure_ascii=True) + "\n" for case in cases
    )


def parse_gold_jsonl(text: str) -> tuple[GoldCase, ...]:
    try:
        cases = tuple(
            GoldCase.model_validate_json(line) for line in text.split("\n") if line.strip()
        )
        gold_jsonl(cases)  # Enforce the same uniqueness/nonempty contract on reads.
        return cases
    except ValueError:
        raise ValueError("Invalid gold JSONL or duplicate case IDs") from None


def write_gold_jsonl(path: Path, cases: tuple[GoldCase, ...]) -> None:
    write_text_report(path, gold_jsonl(cases))
