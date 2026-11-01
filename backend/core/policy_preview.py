"""Bounded asynchronous impact scans of explicit uploads only. No run/corpus discovery."""

from __future__ import annotations

import hashlib
import multiprocessing
import re
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from backend.cli_io import write_report
from backend.core.batch import initialize_parser, parse_upload
from backend.core.engines.ai import AIEngine
from backend.core.models import PaperResult
from backend.core.policy_models import Preview
from backend.core.screen import screen_document
from backend.core.screening_context import ScreeningContext
from backend.core.settings import AISettings
from backend.security.airlock import shared_counter


def signature(paper: PaperResult) -> object:
    return {
        "color": paper.color,
        "label": paper.label,
        "incomplete_reasons": paper.incomplete_reasons,
        "incomplete_pages": paper.incomplete_pages,
        "findings": [
            flag.model_dump(mode="json", exclude={"finding_id", "paper_id"})
            for flag in paper.findings
        ],
    }


class PreviewService:
    def __init__(self, root: Path, lock: RLock, finished: Callable[[Preview], None]) -> None:
        self.root, self.lock, self.finished = root, lock, finished
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="spr-policy-preview")
        self.parsers: ProcessPoolExecutor | None = None
        self.active: str | None = None
        self.ai: AIEngine | None = None

    def path(self, identifier: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise KeyError("Preview not found")
        return self.root / "policies/previews" / identifier

    def read(self, identifier: str) -> Preview:
        try:
            return Preview.model_validate_json(
                (self.path(identifier) / "preview.json").read_bytes()
            )
        except FileNotFoundError as exc:
            raise KeyError("Preview not found") from exc

    def save(self, preview: Preview) -> None:
        write_report(
            self.path(preview.preview_id) / "preview.json", preview.model_dump(mode="json")
        )

    def submit(self, preview: Preview, before: ScreeningContext, after: ScreeningContext) -> None:
        with self.lock:
            if self.active:
                raise ValueError("An impact preview is already running. Wait for it to finish.")
            self.active = preview.preview_id
            self.save(preview)
            if self.parsers is None:
                self.parsers = ProcessPoolExecutor(
                    max_workers=2,
                    mp_context=multiprocessing.get_context("spawn"),
                    initializer=initialize_parser,
                    initargs=(shared_counter(),),
                )
            self.worker.submit(
                self._run, preview, before, after, self.ai.settings if self.ai else None
            )

    def _run(
        self,
        preview: Preview,
        before: ScreeningContext,
        after: ScreeningContext,
        ai_settings: AISettings | None = None,
    ) -> None:
        try:
            preview = preview.model_copy(
                update={
                    "state": "running",
                    "message": "Parsing explicit uploads, then comparing both policy snapshots",
                }
            )
            with self.lock:
                self.save(preview)
            entries = list(preview.entries)
            as_of = datetime.now(UTC).date()
            for index, entry in enumerate(entries):
                assert self.parsers is not None
                source = self.path(preview.preview_id) / f"{index}.source"
                if hashlib.sha256(source.read_bytes()).hexdigest() != entry.sha256:
                    raise ValueError("Preview source changed")
                parsed = self.parsers.submit(
                    parse_upload, entry.file_name, source, self.root / "runs/cache/parse"
                ).result()
                if parsed.status == "rejected":
                    entries[index] = entry.model_copy(
                        update={"message": "Input was rejected; use a permitted readable PDF/DOCX."}
                    )
                else:
                    results = [
                        screen_document(
                            parsed,
                            ctx.rules,
                            engine=ctx.engine,
                            semantic=ctx.semantic.session() if ctx.semantic else None,
                            specificity=ctx.specificity,
                            as_of=as_of,
                            ai=self.ai.session(ai_settings) if self.ai and ai_settings else None,
                        )
                        for ctx in (before, after)
                    ]
                    entries[index] = entry.model_copy(
                        update={
                            "before": results[0],
                            "after": results[1],
                            "changed": signature(results[0]) != signature(results[1]),
                            "message": "Compared both snapshots",
                        }
                    )
                preview = preview.model_copy(update={"entries": tuple(entries)})
                with self.lock:
                    self.save(preview)
            eligible = bool(entries) and all(
                e.before
                and e.after
                and not e.before.incomplete_reasons
                and not e.after.incomplete_reasons
                for e in entries
            )
            preview = preview.model_copy(
                update={
                    "state": "complete",
                    "eligible": eligible,
                    "message": "Impact comparison complete. Sponsor accuracy/recall not measured."
                    if eligible
                    else "Preview includes unreadable or incomplete inputs; "
                    "replace them before publication.",
                }
            )
        except Exception:
            preview = preview.model_copy(
                update={
                    "state": "failed",
                    "eligible": False,
                    "message": "Impact scan failed. Check local model/storage availability "
                    "and retry with explicit files.",
                }
            )
        finally:
            with self.lock:
                self.save(preview)
                self.active = None
                self.finished(preview)

    def close(self) -> None:
        self.worker.shutdown(wait=True, cancel_futures=True)
        if self.parsers:
            self.parsers.shutdown(wait=True, cancel_futures=True)
