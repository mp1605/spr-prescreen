"""Read only declared model files, never document or evaluation directories."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import Field, ValidationError

from backend.core.rules_loader import StrictModel, Text


class Asset(StrictModel):
    path: Text
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(gt=0)


class ModelManifest(StrictModel):
    embedding_model: Text
    embedding_dimensions: int
    language_model: Text
    assets: tuple[Asset, ...] = Field(min_length=1)


class AssetStatus(StrictModel):
    ready: bool
    files: int
    bytes: int
    message: str


def model_status(root: Path, *, verify_hashes: bool = False) -> AssetStatus:
    try:
        manifest = ModelManifest.model_validate_json((root / "models/manifest.json").read_bytes())
        total = 0
        counted: set[Path] = set()
        for asset in manifest.assets:
            path = (root / asset.path).resolve()
            if not path.is_relative_to((root / "models").resolve()):
                raise ValueError("Model manifest path escapes models directory")
            if path.stat().st_size != asset.bytes:
                raise ValueError(f"Model asset size mismatch: {asset.path}")
            if verify_hashes and hashlib.sha256(path.read_bytes()).hexdigest() != asset.sha256:
                raise ValueError(f"Model asset hash mismatch: {asset.path}")
            if path not in counted:
                total += asset.bytes
                counted.add(path)
        return AssetStatus(
            ready=True,
            files=len(manifest.assets),
            bytes=total,
            message="Local model assets verified"
            if verify_hashes
            else "Local model assets present",
        )
    except (OSError, ValueError, ValidationError, json.JSONDecodeError):
        return AssetStatus(
            ready=False,
            files=0,
            bytes=0,
            message="Local model assets missing or invalid. Run scripts/prepare_models.py.",
        )
