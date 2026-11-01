"""Bounded browser jobs: process-isolated parsing, real stage updates, cooperative cancel."""

from __future__ import annotations

import multiprocessing
import signal
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from typing import Any

from backend.core.batch_models import TERMINAL, BatchEntry, Phase
from backend.core.engines.ai import AIEngine, AISession
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.ingest import parse_document
from backend.core.ingest_models import ParseResult
from backend.core.rules_loader import RuleRegistry
from backend.core.run_store import RunStore
from backend.core.screen import screen_document
from backend.core.screening_context import ScreeningContext
from backend.core.specificity import SpecificityEngine
from backend.security.airlock import shared_counter


class Cancelled(Exception):
    pass


def initialize_parser(counter: Any = None) -> None:
    # The parent coordinates cancellation and shutdown; terminal SIGINT must not
    # interrupt child queue reads or emit tracebacks during normal shutdown.
    from backend.security.airlock import install_airlock

    install_airlock(counter)
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def parse_upload(name: str, source: Path, cache: Path) -> ParseResult:
    return parse_document(name, source.read_bytes(), cache_directory=cache)


class BatchService:
    def __init__(
        self,
        root: Path,
        rules: RuleRegistry,
        engine: RulesEngine,
        *,
        semantic: SemanticEngine | None = None,
        specificity: SpecificityEngine | None = None,
        ai: AIEngine | None = None,
    ) -> None:
        self.store = RunStore(root)
        self.rules = rules
        self.engine = engine
        self.semantic = semantic
        self.specificity = specificity
        self.ai = ai
        self.contexts = {
            rules.policy_version: ScreeningContext(rules, engine, semantic, specificity)
        }
        self.cache = root / "runs/cache"
        self.stopping = False
        self.workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="spr-batch")
        self.parsers: ProcessPoolExecutor | None = None
        self.store.recover()
        self.on_entry_changed: Callable[[str, str], None] | None = None

    def organize(self, run_id: str, entry_id: str) -> None:
        if self.on_entry_changed:
            self.on_entry_changed(run_id, entry_id)

    def submit(self, run_id: str, entry: BatchEntry) -> None:
        with self.store.lock:
            if self.stopping:
                raise ValueError("Service is stopping")
            if self.parsers is None:
                self.parsers = ProcessPoolExecutor(
                    max_workers=2,
                    mp_context=multiprocessing.get_context("spawn"),
                    initializer=initialize_parser,
                    initargs=(shared_counter(),),
                )
            version = self.store.read(run_id).rules_version
            context = self.contexts.get(version)
            if context is None:
                raise ValueError("This batch policy is unavailable; upload a new batch.")
            snapshot = self.store.read(run_id).ai_settings
            ai = self.ai.session(snapshot) if self.ai and snapshot is not None else None
            self.workers.submit(self._process, run_id, entry, context, ai)

    def _current(self, run_id: str, original: BatchEntry) -> BatchEntry:
        entry = self.store.entry(run_id, original.entry_id)
        if self.stopping or entry.attempt != original.attempt or entry.phase == "cancelled":
            raise Cancelled
        return entry

    def _stage(self, run_id: str, original: BatchEntry, phase: Phase, message: str) -> None:
        with self.store.lock:
            current = self._current(run_id, original)
            self.store.update(
                run_id, current.model_copy(update={"phase": phase, "message": message})
            )
            if phase == "failed":
                self.organize(run_id, original.entry_id)

    def install(self, context: ScreeningContext) -> None:
        with self.store.lock:
            self.contexts[context.rules.policy_version] = context
            self.rules, self.engine = context.rules, context.engine
            self.semantic, self.specificity = context.semantic, context.specificity

    def _process(
        self,
        run_id: str,
        original: BatchEntry,
        context: ScreeningContext,
        ai: AISession | None = None,
    ) -> None:
        start = perf_counter()
        try:
            self._stage(run_id, original, "parsing", "Extracting source text and locations")
            if self.parsers is None:
                raise RuntimeError("Parser pool not available")
            parsed = self.parsers.submit(
                parse_upload,
                original.file_name,
                self.store.source(run_id, original.entry_id),
                self.cache,
            ).result()
            with self.store.lock:
                self._current(run_id, original)
                self.store.save_parse(run_id, original.entry_id, parsed)
            if parsed.status == "rejected":
                self._stage(
                    run_id, original, "rejected", "; ".join(i.message for i in parsed.issues)
                )
                return
            result = screen_document(
                parsed,
                context.rules,
                engine=context.engine,
                semantic=context.semantic.session() if context.semantic else None,
                specificity=context.specificity,
                ai=ai,
                ai_progress=lambda: self._stage(
                    run_id, original, "ai", "Checking optional local AI"
                ),
                progress=lambda name: self._stage(
                    run_id,
                    original,
                    name,
                    f"Checking {name} · Rules + Semantic"
                    if context.semantic
                    else f"Checking {name}",
                ),
            )
            if ai is None:
                self._stage(run_id, original, "ai", "AI off")
            with self.store.lock:
                current = self._current(run_id, original)
                self.store.update(
                    run_id,
                    current.model_copy(
                        update={
                            "phase": "done",
                            "message": "List 1 and List 2 checked · AI " + result.ai_state,
                            "result": result,
                            "seconds": perf_counter() - start,
                        }
                    ),
                )
                self.organize(run_id, original.entry_id)
        except Cancelled:
            return
        except Exception:
            try:
                self._stage(
                    run_id, original, "failed", "Processing failed. Retry or inspect the original."
                )
            except Cancelled:
                return

    def cancel(self, run_id: str) -> None:
        with self.store.lock:
            for entry in self.store.read(run_id).entries:
                if entry.phase not in TERMINAL:
                    self.store.update(
                        run_id,
                        entry.model_copy(
                            update={
                                "phase": "cancelled",
                                "message": "Cancelled. In-flight parser output will be discarded.",
                            }
                        ),
                    )
                    self.organize(run_id, entry.entry_id)

    def retry(self, run_id: str, entry_id: str) -> None:
        with self.store.lock:
            entry = self.store.entry(run_id, entry_id)
            if entry.phase not in {"failed", "cancelled"}:
                raise ValueError("Only failed or cancelled uploads can be retried")
            if not self.store.source(run_id, entry_id).is_file():
                raise ValueError("Original unavailable. Upload the file again.")
            if self.store.read(run_id).rules_version != self.rules.policy_version:
                raise ValueError(
                    "Rules have changed. Upload as a new batch to retain run provenance."
                )
            retry = entry.model_copy(
                update={
                    "phase": "queued",
                    "message": "Waiting to retry",
                    "attempt": entry.attempt + 1,
                    "result": None,
                }
            )
            self.store.update(run_id, retry)
            self.submit(run_id, retry)

    def close(self) -> None:
        with self.store.lock:
            for batch in self.store.list():
                self.cancel(batch.run_id)
            self.stopping = True
        self.workers.shutdown(wait=True, cancel_futures=True)
        if self.parsers is not None:
            self.parsers.shutdown(wait=True, cancel_futures=True)
