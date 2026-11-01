"""One-shot holdout claim, ready for the later authorized evaluation runner."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from backend.cli_io import write_report


def claim_holdout(directory: Path, fingerprint: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        raise ValueError("Frozen evaluation fingerprint must be a SHA-256 digest")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "holdout-claim.json"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ValueError("Holdout has already been claimed; a second run is refused") from None
    with os.fdopen(descriptor, "w") as handle:
        json.dump(
            dict(fingerprint=fingerprint, status="started", utc=datetime.now(UTC).isoformat()),
            handle,
        )
        handle.flush()
        os.fsync(handle.fileno())
    return path


def finish_holdout(directory: Path, fingerprint: str, *, succeeded: bool) -> None:
    path = directory / "holdout-claim.json"
    data = json.loads(path.read_text())
    if data.get("fingerprint") != fingerprint or data.get("status") != "started":
        raise ValueError("Holdout claim identity or state does not match")
    data.update(
        status="complete" if succeeded else "failed", finished_utc=datetime.now(UTC).isoformat()
    )
    write_report(path, data)
