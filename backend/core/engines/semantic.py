"""E2 uses only official policy text. No corpus discovery or feedback retrieval occurs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import RLock
from time import perf_counter

import numpy as np

from backend.core.engines.base import Hit
from backend.core.engines.local_bge import EmbeddingProvider, LocalBGE
from backend.core.engines.vector_cache import MAX_CHUNKS, Matrix, VectorCache, normalized
from backend.core.ingest_models import ParseResult
from backend.core.policy import ListName
from backend.core.rules_loader import RuleItem, RuleRegistry
from backend.core.semantic_models import SemanticInfo, SemanticMatch
from backend.core.settings import SemanticSettings


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True).encode()).hexdigest()


class SemanticEngine:
    def __init__(
        self,
        root: Path,
        registry: RuleRegistry,
        settings: SemanticSettings,
        *,
        provider: EmbeddingProvider | None = None,
        cache: bool = True,
    ) -> None:
        self.root, self.registry, self.settings = root, registry, settings
        self.items = (*registry.list1, *registry.list2)
        self.reference_digest = digest([(item.id, item.text) for item in self.items])
        self.provider = provider
        self.references: Matrix | None = None
        self.cache = VectorCache(root / "runs/cache/semantic" if cache else None)
        self.lock = RLock()
        self.state = "not_loaded"

    def session(self) -> SemanticSession:
        return SemanticSession(self)

    def vectors(self, document: ParseResult) -> tuple[Matrix, tuple[int, ...], str, str]:
        with self.lock:
            try:
                if self.provider is None:
                    self.provider = LocalBGE(self.root)
                provider = self.provider
                identity = digest(["official-bge-v1", "token510-overlap64", provider.identity])
                if self.references is None:
                    key = digest([identity, self.reference_digest, "references"])
                    cached = self.cache.read(key, 39)
                    if cached is None:
                        cached = normalized(provider.embed([item.text for item in self.items]), 39)
                        self.cache.write(key, cached)
                    self.references = cached
                chunks: list[str] = []
                owners: list[int] = []
                for index, segment in enumerate(document.segments):
                    pieces = provider.chunks(segment.text)
                    if not pieces or any(not piece.strip() for piece in pieces):
                        raise ValueError("Missing semantic text window")
                    chunks.extend(pieces)
                    owners.extend([index] * len(pieces))
                    if len(chunks) > MAX_CHUNKS:
                        raise ValueError("Semantic resource limit exceeded")
                key = digest(
                    [
                        identity,
                        document.paper_id,
                        document.parser_version,
                        [(s.segment_id, s.text) for s in document.segments],
                        chunks,
                    ]
                )
                vectors = self.cache.read(key, len(chunks))
                state = "hit"
                if vectors is None:
                    vectors = normalized(provider.embed(chunks), len(chunks))
                    state = "miss" if self.cache.write(key, vectors) else "unavailable"
                    if self.cache.directory is None:
                        state = "not_used"
                self.state = "ready"
                return vectors, tuple(owners), state, provider.identity
            except Exception:
                self.state = "unavailable"
                raise


class SemanticSession:
    """One paper, one embedding pass, with matching restricted to the current list."""

    def __init__(self, host: SemanticEngine) -> None:
        self.host = host
        self.rules_version = host.registry.policy_version
        self.values: Matrix | None = None
        self.owners: tuple[int, ...] = ()
        self.cache_state = "not_used"
        self.model_digest: str | None = None
        self.failed = False
        self.seconds = 0.0
        self.segments = 0
        self.paper_digest: str | None = None

    def run(
        self, document: ParseResult, list_name: ListName, items: tuple[RuleItem, ...]
    ) -> tuple[Hit, ...]:
        if self.failed:
            raise ValueError("Semantic screening did not complete")
        if not document.segments:
            return ()
        started = perf_counter()
        try:
            identity = digest(
                [document.paper_id, [(s.segment_id, s.text) for s in document.segments]]
            )
            if self.paper_digest is not None and self.paper_digest != identity:
                raise ValueError("Semantic sessions cannot be reused across papers")
            self.paper_digest = identity
            if self.values is None:
                self.segments = len(document.segments)
                self.values, self.owners, self.cache_state, self.model_digest = self.host.vectors(
                    document
                )
            expected = (
                self.host.registry.list1 if list_name == "list1" else self.host.registry.list2
            )
            if items != expected:
                raise ValueError("Semantic policy snapshot changed")
            indexes = [self.host.items.index(item) for item in items]
            if self.host.references is None:
                raise ValueError("Official references unavailable")
            scores = np.clip(self.values @ self.host.references[indexes].T, -1, 1)
            by_segment = np.full((self.segments, len(items)), -1, dtype=np.float32)
            np.maximum.at(by_segment, np.asarray(self.owners), scores)
            hits: list[Hit] = []
            for row, segment in enumerate(document.segments):
                for column, item in enumerate(items):
                    score = float(by_segment[row, column])
                    if score < self.host.settings.mid_threshold:
                        continue
                    reference = SemanticMatch(
                        item_id=item.id,
                        text=item.text,
                        score=score,
                        band="high" if score >= self.host.settings.high_threshold else "possible",
                    )
                    hits.append(
                        Hit(
                            segment_id=segment.segment_id,
                            item_id=item.id,
                            list=list_name,
                            detector="Official policy semantic similarity",
                            engine="semantic",
                            char_start=segment.location.char_start,
                            char_end=segment.location.char_end,
                            score=score,
                            reference=reference,
                        )
                    )
            return tuple(hits)
        except Exception:
            self.failed = True
            raise
        finally:
            self.seconds += perf_counter() - started

    def info(self) -> SemanticInfo:
        return SemanticInfo.model_validate(
            dict(
                reference_digest=self.host.reference_digest,
                model_digest=self.model_digest,
                high_threshold=self.host.settings.high_threshold,
                mid_threshold=self.host.settings.mid_threshold,
                state="error" if self.failed else "complete",
                segments=self.segments,
                chunks=len(self.owners),
                cache_state=self.cache_state,
                seconds=self.seconds,
            )
        )
