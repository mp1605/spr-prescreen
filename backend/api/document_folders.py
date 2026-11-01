"""Explicit, repairable projection of a batch into readable local folders."""

from typing import Any

from fastapi import APIRouter

from backend.core.batch_folders import FOLDERS, BatchFolders
from backend.core.review_store import ReviewStore
from backend.core.run_store import RunStore


def document_folders_router(
    store: RunStore, reviews: ReviewStore, folders: BatchFolders
) -> APIRouter:
    router = APIRouter(prefix="/api/batches/{run_id}/folders")

    @router.get("")
    def status(run_id: str) -> dict[str, Any]:
        with store.lock:
            batch = store.read(run_id)
            states = reviews.states(run_id)
            counts = dict.fromkeys(FOLDERS, 0)
            errors = []
            for entry in batch.entries:
                state = states[entry.entry_id]
                if state.storage_file:
                    counts[folders.folder(entry, state)] += 1
                if state.storage_error:
                    errors.append(f"{entry.file_name}: {state.storage_error}")
            return {
                "path": str(folders.path(run_id)),
                "exists": folders.path(run_id).is_dir(),
                "counts": counts,
                "errors": errors,
            }

    @router.post("")
    def update(run_id: str) -> dict[str, Any]:
        with store.lock:
            batch = store.read(run_id)
            states = reviews.states(run_id)
            folders.prepare(run_id)
            for entry in batch.entries:
                if entry.phase in {"done", "failed", "cancelled"}:
                    folders.attempt(batch, entry, states[entry.entry_id])
            return status(run_id)

    return router
