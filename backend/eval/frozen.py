"""Verify the recorded scanner freeze without changing thresholds or engine code."""

import hashlib
import json
from pathlib import Path


def verify_frozen_scanner(root: Path) -> str:
    manifest = json.loads((root / "reports/M11-build-manifest.json").read_text())
    records = []
    for record in manifest["files"]:
        name = record["path"]
        if not (
            name.startswith(("backend/core/", "backend/security/", "policies/"))
            or name in {"config/settings.yaml", "MASTER_PROMPT.md", "docs/official-lists.pdf"}
        ):
            continue
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("Frozen scanner/configuration changed; evaluation refused: " + name)
        records.append(record)
    if len(records) < 50:
        raise ValueError("Scanner freeze manifest is incomplete")
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
