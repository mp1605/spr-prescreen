"""Bounded, pickle-free vector cache. A corrupt cache is a miss, never trusted evidence."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pydantic import Field

from backend.core.rules_loader import StrictModel

Matrix = NDArray[np.float32]
MAX_CHUNKS = 4096
DIMENSIONS = 384


def normalized(values: Matrix, rows: int) -> Matrix:
    if values.shape != (rows, DIMENSIONS) or not np.isfinite(values).all():
        raise ValueError("Embedding dimensions or values are invalid")
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if np.any(norms < 1e-8):
        raise ValueError("Embedding vectors must be nonzero")
    return np.asarray(values / norms, dtype=np.float32)


class VectorHeader(StrictModel):
    key: str = Field(pattern=r"^[a-f0-9]{64}$")
    rows: int = Field(ge=1, le=MAX_CHUNKS)
    dimensions: int = Field(default=DIMENSIONS, ge=DIMENSIONS, le=DIMENSIONS)
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


class VectorCache:
    def __init__(self, directory: Path | None) -> None:
        self.directory = directory

    def _path(self, key: str) -> Path:
        if (
            self.directory is None
            or len(key) != 64
            or any(c not in "0123456789abcdef" for c in key)
        ):
            raise ValueError("Invalid vector cache key")
        return self.directory / f"{key}.vectors"

    def read(self, key: str, rows: int) -> Matrix | None:
        if self.directory is None:
            return None
        try:
            with self._path(key).open("rb") as handle:
                header = VectorHeader.model_validate_json(handle.readline(1024))
                if header.key != key or header.rows != rows:
                    return None
                payload = handle.read(rows * DIMENSIONS * 4 + 1)
            if len(payload) != rows * DIMENSIONS * 4:
                return None
            if hashlib.sha256(payload).hexdigest() != header.digest:
                return None
            values = np.frombuffer(payload, dtype="<f4").reshape(rows, DIMENSIONS)
            if not np.isfinite(values).all() or not np.allclose(
                np.linalg.norm(values, axis=1), 1, atol=1e-4
            ):
                return None
            return np.asarray(values, dtype=np.float32)
        except (OSError, ValueError):
            return None

    def write(self, key: str, values: Matrix) -> bool:
        if self.directory is None:
            return False
        temporary: Path | None = None
        try:
            path = self._path(key)
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Preserve the exact float32 values returned to the caller. Re-normalizing
            # here can change one bit and make warm results differ from cold results.
            if values.ndim != 2 or values.shape[1] != DIMENSIONS or not np.isfinite(values).all():
                raise ValueError("Invalid cached vector dimensions or values")
            if not np.allclose(np.linalg.norm(values, axis=1), 1, atol=1e-4):
                raise ValueError("Cached vectors must already be normalized")
            payload = values.astype("<f4").tobytes()
            header = VectorHeader(
                key=key, rows=len(values), digest=hashlib.sha256(payload).hexdigest()
            )
            with tempfile.NamedTemporaryFile(
                dir=self.directory, prefix=".vectors-", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(header.model_dump_json().encode() + b"\n" + payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            return True
        except OSError:
            return False
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
