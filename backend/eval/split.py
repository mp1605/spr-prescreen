"""Frozen split metadata from MASTER_PROMPT.md. No dataset files are opened."""

from __future__ import annotations

import re
from typing import Literal

HOLDOUT_NUMBERS = frozenset(
    {6, 11, 14, 15, 16, 26, 35, 37, 44, 49, 56, 60, 61, 62, 65, 71, 73, 74, 79, 80}
)


def case_number(case_id: str) -> int:
    match = re.fullmatch(r"SPR-Test-(\d{3})", case_id)
    if not match or not 1 <= int(match[1]) <= 80:
        raise ValueError("Split requires a canonical SPR-Test-001 through SPR-Test-080 ID")
    return int(match[1])


def split_for(case_id: str) -> Literal["dev", "holdout"]:
    return "holdout" if case_number(case_id) in HOLDOUT_NUMBERS else "dev"


def case_ids(split: Literal["dev", "holdout"]) -> tuple[str, ...]:
    if split not in ("dev", "holdout"):
        raise ValueError("Unknown evaluation split")
    return tuple(
        f"SPR-Test-{n:03}" for n in range(1, 81) if (n in HOLDOUT_NUMBERS) == (split == "holdout")
    )
