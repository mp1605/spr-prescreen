"""Official IDs are stable; there is deliberately no List 1 item 2."""

from typing import Literal

ListName = Literal["list1", "list2"]
LIST1_IDS = tuple(f"L1-{n}" for n in (1, 3, 4, 5, 6, 7, 8, 9))
LIST2_IDS = tuple(f"L2-{n:02}" for n in range(1, 32))
OFFICIAL_IDS = frozenset((*LIST1_IDS, *LIST2_IDS))
DISCLAIMER = "Pre-screen only — a reviewer makes the release decision."
