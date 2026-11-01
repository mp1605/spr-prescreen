"""Local upload boundary and resumable SSE notifications. Never discover scanner inputs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.datastructures import UploadFile

from backend.cli_io import source_allowed
from backend.core.batch import BatchService
from backend.core.batch_ai import BatchAIMode, batch_ai_settings
from backend.core.batch_models import TERMINAL, BatchEntry, BatchRecord, BatchView, ReviewProgress
from backend.core.ingest import safe_name
from backend.core.ingest_models import IngestLimits
from backend.core.review_store import ReviewStore


def batches_router(service: BatchService, reviews: ReviewStore) -> APIRouter:
    router = APIRouter(prefix="/api/batches")
    store = service.store
    limits = IngestLimits()

    @router.get("", response_model=list[BatchView])
    def list_batches() -> list[BatchView]:
        result: list[BatchView] = []
        for batch in store.list():
            progress: dict[str, ReviewProgress] = {}
            states = reviews.states(batch.run_id)
            for entry in batch.entries:
                state = states[entry.entry_id]
                paper = entry.result
                count = len(state.decisions)
                complete = bool(
                    paper
                    and entry.phase == "done"
                    and (
                        count == paper.flag_count.total
                        if paper.flag_count.total
                        else state.inspected
                    )
                )
                if paper and paper.incomplete_reasons:
                    complete = complete and state.inspected
                progress[entry.entry_id] = ReviewProgress(
                    reviewed=count, complete=complete, approved=state.approved
                )
            result.append(BatchView(**batch.model_dump(), reviews=progress))
        return result

    @router.post("", response_model=BatchRecord, status_code=202)
    async def upload(request: Request, ai_mode: BatchAIMode = "default") -> BatchRecord:
        snapshot = await batch_ai_settings(service.ai, ai_mode)
        run_id = "web-" + uuid4().hex
        entries: list[BatchEntry] = []
        try:
            async with request.form(max_files=limits.max_batch_files, max_fields=0) as form:
                files = list(form.multi_items())
                if not files or any(not isinstance(value, UploadFile) for _, value in files):
                    raise HTTPException(422, "Upload between 1 and 100 PDF/DOCX files")
                for _, value in files:
                    if not isinstance(value, UploadFile):
                        continue
                    name = safe_name(value.filename or "unnamed")
                    entry = BatchEntry(entry_id=uuid4().hex, file_name=name)
                    reason: str | None = None
                    if not source_allowed(Path(value.filename or name)):
                        reason = (
                            "Answer keys and evaluation metadata are excluded from scanner inputs."
                        )
                    elif Path(name).suffix.lower() not in {".pdf", ".docx"}:
                        reason = "Unsupported format. Choose PDF or DOCX."
                    elif value.size is not None and value.size > limits.max_file_bytes:
                        reason = "File exceeds the 25 MiB limit."
                    if reason is None:
                        data = await value.read(limits.max_file_bytes + 1)
                        if len(data) > limits.max_file_bytes:
                            reason = "File exceeds the 25 MiB limit."
                        else:
                            store.save_source(run_id, entry.entry_id, data)
                    if reason:
                        entry = entry.model_copy(update={"phase": "rejected", "message": reason})
                    entries.append(entry)
            with store.lock:
                batch = BatchRecord(
                    run_id=run_id,
                    created=datetime.now(UTC),
                    rules_version=service.rules.policy_version,
                    ai_settings=snapshot,
                    entries=tuple(entries),
                )
                store.save(batch)
                for entry in entries:
                    if entry.phase == "queued":
                        service.submit(run_id, entry)
            return batch
        except Exception:
            # Remove only this request's newly created, unpublished upload directory.
            if not (store.path(run_id) / "results.json").exists():
                shutil.rmtree(store.path(run_id), ignore_errors=True)
            raise

    @router.post("/{run_id}/rescan", response_model=BatchRecord, status_code=202)
    def rescan(run_id: str) -> BatchRecord:
        with store.lock:
            previous = store.read(run_id)
            if any(entry.phase not in TERMINAL for entry in previous.entries):
                raise HTTPException(409, "Wait for the current batch to finish before rescanning.")
            identifier = "web-" + uuid4().hex
            entries = []
            try:
                for old in previous.entries:
                    entry = BatchEntry(entry_id=uuid4().hex, file_name=old.file_name)
                    source = store.source(run_id, old.entry_id)
                    if old.phase == "rejected" or not source.is_file():
                        entry = entry.model_copy(
                            update={
                                "phase": "rejected",
                                "message": "No retained original is available for this entry. "
                                + old.message,
                            }
                        )
                    elif source.stat().st_size > limits.max_file_bytes:
                        entry = entry.model_copy(
                            update={
                                "phase": "rejected",
                                "message": "Retained original exceeds the 25 MiB limit; "
                                "inspect the source.",
                            }
                        )
                    else:
                        data = source.read_bytes()
                        if (
                            old.result
                            and "sha256:" + hashlib.sha256(data).hexdigest() != old.result.paper_id
                        ):
                            entry = entry.model_copy(
                                update={
                                    "phase": "rejected",
                                    "message": "Retained original hash changed; "
                                    "inspect and explicitly upload the source.",
                                }
                            )
                        else:
                            store.save_source(identifier, entry.entry_id, data)
                    entries.append(entry)
                record = BatchRecord(
                    run_id=identifier,
                    created=datetime.now(UTC),
                    rules_version=service.rules.policy_version,
                    ai_settings=service.ai.settings if service.ai else None,
                    entries=tuple(entries),
                )
                store.save(record)
                for entry in entries:
                    if entry.phase == "queued":
                        service.submit(identifier, entry)
                return record
            except Exception:
                if not (store.path(identifier) / "results.json").exists():
                    shutil.rmtree(store.path(identifier), ignore_errors=True)
                raise

    @router.get("/{run_id}", response_model=BatchRecord)
    def batch(run_id: str) -> BatchRecord:
        return store.read(run_id)

    @router.post("/{run_id}/cancel", status_code=204)
    def cancel(run_id: str) -> None:
        service.cancel(run_id)

    @router.post("/{run_id}/papers/{entry_id}/retry", status_code=202)
    def retry(run_id: str, entry_id: str) -> dict[str, str]:
        service.retry(run_id, entry_id)
        return {"status": "queued"}

    @router.get("/{run_id}/events")
    async def events(run_id: str, request: Request) -> StreamingResponse:
        store.read(run_id)

        async def stream() -> AsyncIterator[str]:
            previous = request.headers.get("last-event-id", "")
            ticks = 0
            while not await request.is_disconnected():
                batch = store.read(run_id)
                terminal = all(e.phase in TERMINAL for e in batch.entries)
                if str(batch.revision) != previous or terminal:
                    payload = json.dumps({"revision": batch.revision, "terminal": terminal})
                    yield f"id: {batch.revision}\nevent: progress\ndata: {payload}\n\n"
                    previous = str(batch.revision)
                if terminal:
                    return
                ticks += 1
                if ticks % 50 == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.2)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    return router
