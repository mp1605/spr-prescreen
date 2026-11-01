"""Pinned, local-only BGE adapter with explicit tokenizer windows and CPU inference."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from threading import RLock
from typing import Protocol

import numpy as np
from tokenizers import Tokenizer

from backend.core.assets import ModelManifest, model_status
from backend.core.engines.vector_cache import Matrix, normalized
from backend.core.runtime import configure_offline_environment


class EmbeddingProvider(Protocol):
    identity: str

    def chunks(self, text: str) -> tuple[str, ...]: ...
    def embed(self, texts: Sequence[str]) -> Matrix: ...


def token_windows(tokenizer: Tokenizer, text: str) -> tuple[str, ...]:
    """Cover all tokens, including tails beyond the model's 512-token input limit."""
    offsets = tokenizer.encode(text, add_special_tokens=False).offsets
    if not offsets:
        raise ValueError("Screening text did not produce tokens")
    windows: list[str] = []
    start = 0
    while start < len(offsets):
        end = min(start + 510, len(offsets))
        while True:
            left, right = offsets[start][0], offsets[end - 1][1]
            if not 0 <= left < right <= len(text):
                raise ValueError("Tokenizer supplied invalid source offsets")
            piece = text[left:right]
            if len(tokenizer.encode(piece, add_special_tokens=False).ids) <= 510:
                break
            end -= 1
            if end <= start:
                raise ValueError("Text cannot fit a semantic window")
        windows.append(piece)
        if len(windows) > 4096:
            raise ValueError("Semantic window limit exceeded")
        if end == len(offsets):
            break
        start = max(start + 1, end - 64)
    return tuple(windows)


class LocalBGE:
    def __init__(self, root: Path) -> None:
        configure_offline_environment(root)
        status = model_status(root, verify_hashes=True)
        if not status.ready:
            raise ValueError("Local semantic model assets are unavailable or invalid")
        manifest = ModelManifest.model_validate_json((root / "models/manifest.json").read_bytes())
        tokenizers = [
            a
            for a in manifest.assets
            if a.path.endswith("/tokenizer.json") and "fastembed/" in a.path
        ]
        if len(tokenizers) != 1 or manifest.embedding_dimensions != 384:
            raise ValueError("Semantic model manifest is invalid")
        directory = (root / tokenizers[0].path).parent
        self.identity = hashlib.sha256(
            json.dumps(
                [(a.path, a.sha256) for a in manifest.assets if "fastembed/" in a.path],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        self.lock = RLock()
        # Disable telemetry before importing fastembed, which also imports ONNX Runtime.
        import onnxruntime as ort  # type: ignore[import-untyped]

        ort.disable_telemetry_events()
        from fastembed import TextEmbedding

        self.model = TextEmbedding(
            model_name="BAAI/bge-small-en-v1.5",
            cache_dir=str(root / "models/fastembed"),
            specific_model_path=str(directory),
            local_files_only=True,
            threads=2,
            providers=["CPUExecutionProvider"],
        )

    def chunks(self, text: str) -> tuple[str, ...]:
        return token_windows(self.tokenizer, text)

    def embed(self, texts: Sequence[str]) -> Matrix:
        with self.lock:
            values = np.asarray(
                list(self.model.embed(list(texts), batch_size=64)), dtype=np.float32
            )
        return normalized(values, len(texts))
