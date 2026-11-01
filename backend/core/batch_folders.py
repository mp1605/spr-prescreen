"""Readable batch copies are projections of immutable sources and human review events."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from backend.cli_io import write_report
from backend.core.batch_models import TERMINAL, BatchEntry, BatchRecord, ReviewState
from backend.core.export_io import write_binary
from backend.core.run_store import RunStore

FolderName = Literal["Approved", "Flagged", "Pending Review"]
FOLDERS: tuple[FolderName, ...] = ("Approved", "Flagged", "Pending Review")


class BatchFolders:
    def __init__(self, store: RunStore) -> None:
        self.store = store
        self.root = store.directory / "Batch Documents"
        self.errors: dict[tuple[str, str], str] = {}
        self._paths: dict[str, Path] = {}

    def _batch_path(self, run_id: str) -> Path:
        if run_id in self._paths:
            return self._paths[run_id]
        batch = self.store.read(run_id)
        created = batch.created
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        local = created.astimezone(ZoneInfo("America/Chicago"))
        count = len(batch.entries)
        label = f"{local:%Y-%m-%d_%I-%M-%S-%p}_{count}-{'file' if count == 1 else 'files'}"
        number = 1
        while True:
            candidate = self.root / (label if number == 1 else f"{label}_Batch-{number}")
            if candidate.is_symlink():
                raise ValueError("Batch document folders cannot be symbolic links")
            if not candidate.exists():
                break
            manifest = candidate / "manifest.json"
            if manifest.is_symlink():
                raise ValueError("Batch manifest cannot be a symbolic link")
            if manifest.is_file():
                index = json.loads(manifest.read_bytes())
                if isinstance(index, dict) and index.get("run_id") == run_id:
                    break
            number += 1
        self._paths[run_id] = candidate
        return candidate

    def path(self, run_id: str, folder: FolderName | None = None) -> Path:
        self.store.path(run_id)  # Reuse the strict run-ID validation.
        if self.store.directory.is_symlink() or self.root.is_symlink():
            raise ValueError("Batch document folders cannot be symbolic links")
        result = self._batch_path(run_id)
        for path in (self.store.directory, self.root, result, *(result / f for f in FOLDERS)):
            if path.is_symlink():
                raise ValueError("Batch document folders cannot be symbolic links")
        return result / folder if folder else result

    def prepare(self, run_id: str) -> None:
        with self.store.lock:
            # Recheck ownership: two batches may have the same timestamp and file count.
            self._paths.pop(run_id, None)
            destination = self.path(run_id)
            legacy = self.root / run_id
            if legacy.is_symlink():
                raise ValueError("Batch document folders cannot be symbolic links")
            if legacy.exists():
                if any(
                    p.is_symlink()
                    for p in (legacy / "manifest.json", *(legacy / f for f in FOLDERS))
                ):
                    raise ValueError("Legacy batch folders cannot contain symbolic links")
                if destination.exists():
                    raise ValueError(
                        "Both old and new batch folders exist; preserve both and reconcile them"
                    )
                legacy.rename(destination)
            for path in (self.root, destination, *(destination / f for f in FOLDERS)):
                path.mkdir(parents=True, exist_ok=True, mode=0o700)
            manifest = destination / "manifest.json"
            if manifest.is_symlink():
                raise ValueError("Batch manifest cannot be a symbolic link")
            if not manifest.exists():
                write_report(manifest, {"run_id": run_id, "documents": {}})

    def migrate_existing(self) -> int:
        """Rename existing readable copies, leaving source records and review logs intact."""
        moved = 0
        with self.store.lock:
            for batch in self.store.list():
                if any(entry.phase not in TERMINAL for entry in batch.entries):
                    continue
                if not (self.root / batch.run_id).exists():
                    continue
                try:
                    self.prepare(batch.run_id)
                    moved += 1
                except (OSError, ValueError):
                    for entry in batch.entries:
                        self.errors[(batch.run_id, entry.entry_id)] = (
                            "Batch folder rename failed. Check storage "
                            "and use Update batch folders."
                        )
        return moved

    @staticmethod
    def filename(batch: BatchRecord, entry: BatchEntry) -> str:
        number = next(
            n for n, value in enumerate(batch.entries, 1) if value.entry_id == entry.entry_id
        )
        stem = (
            re.sub(r"[^\w .()-]+", "_", Path(entry.file_name).stem).strip(" .")[:120] or "Document"
        )
        extension = (
            entry.result.file_type
            if entry.result
            else Path(entry.file_name).suffix.lstrip(".").lower()
        )
        if extension not in {"pdf", "docx"}:
            raise ValueError("Only PDF/DOCX originals can be organized")
        return f"{number:03d}_{stem}.{extension}"

    @staticmethod
    def folder(entry: BatchEntry, state: ReviewState) -> FolderName:
        if state.approved:
            if entry.phase != "done" or not entry.result or entry.result.color != "green":
                raise ValueError("Only a reviewed green paper belongs in Approved")
            return "Approved"
        if entry.result and entry.result.color in {"red", "yellow"}:
            return "Flagged"
        return "Pending Review"

    def destination(self, batch: BatchRecord, entry: BatchEntry, state: ReviewState) -> Path:
        return self.path(batch.run_id, self.folder(entry, state)) / self.filename(batch, entry)

    def decorate(self, batch: BatchRecord, entry: BatchEntry, state: ReviewState) -> ReviewState:
        if entry.phase == "rejected":
            return state
        try:
            target = self.destination(batch, entry, state)
            if target.is_symlink():
                raise ValueError("Organized documents cannot be symbolic links")
            ready = target.is_file()
            missing = (
                self.path(batch.run_id).exists()
                and not ready
                and entry.phase in {"done", "failed", "cancelled"}
            )
            error = self.errors.get((batch.run_id, entry.entry_id))
            if missing and not error:
                error = "Document folders need updating. Use Update batch folders."
            return state.model_copy(
                update={"storage_file": str(target) if ready else None, "storage_error": error}
            )
        except (OSError, ValueError):
            return state.model_copy(
                update={
                    "storage_error": "Document storage is unavailable. Check folder permissions "
                    "and use Update batch folders."
                }
            )

    def synchronize(self, batch: BatchRecord, entry: BatchEntry, state: ReviewState) -> None:
        self.prepare(batch.run_id)
        source = self.store.source(batch.run_id, entry.entry_id)
        if entry.phase == "rejected":
            return
        if not source.is_file():
            raise ValueError("Retained original is missing; approval was refused")
        if any(
            p.is_symlink() for p in (source, source.parent, self.store.path(batch.run_id))
        ) or not source.resolve().is_relative_to(self.store.path(batch.run_id).resolve()):
            raise ValueError("Original document is outside its batch")
        data = source.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if entry.result and digest != entry.result.paper_id.removeprefix("sha256:"):
            raise ValueError("Original document changed since screening; approval was refused")
        target = self.destination(batch, entry, state)
        manifest = self.path(batch.run_id) / "manifest.json"
        if manifest.is_symlink():
            raise ValueError("Batch manifest cannot be a symbolic link")
        index = (
            json.loads(manifest.read_bytes())
            if manifest.is_file()
            else {"run_id": batch.run_id, "documents": {}}
        )
        if not isinstance(index, dict) or not isinstance(index.get("documents"), dict):
            raise ValueError("Batch manifest is damaged")
        copies = [self.path(batch.run_id, f) / target.name for f in FOLDERS]
        for copy in copies:
            if copy.is_symlink():
                raise ValueError("Organized documents cannot be symbolic links")
            if copy.exists() and not copy.is_file():
                raise ValueError("A document destination is occupied by a directory")
            if copy.is_file() and hashlib.sha256(copy.read_bytes()).hexdigest() != digest:
                raise ValueError(
                    "An organized copy was modified. Contents were preserved; "
                    "restore it before updating folders"
                )
        if not target.exists():
            previous = next((copy for copy in copies if copy.is_file()), None)
            if previous:
                previous.replace(target)
            else:
                write_binary(target, data)
        for copy in copies:
            if copy != target and copy.is_file():
                copy.unlink()  # Only identical managed copies; the immutable original remains.
        index["documents"][entry.entry_id] = {
            "original_file_name": entry.file_name,
            "file_name": target.name,
            "folder": target.parent.name,
            "source_sha256": digest,
            "scanner_color": entry.result.color if entry.result else None,
            "reviewer_approved": state.approved,
            "approval": state.approval_event.model_dump(mode="json")
            if state.approval_event
            else None,
            "review_revision": state.revision,
            "copy_type": "original_format_original_bytes",
        }
        write_report(manifest, index)
        self.errors.pop((batch.run_id, entry.entry_id), None)

    def attempt(self, batch: BatchRecord, entry: BatchEntry, state: ReviewState) -> None:
        try:
            self.synchronize(batch, entry, state)
        except (OSError, ValueError):
            self.errors[(batch.run_id, entry.entry_id)] = (
                "Document copy could not be organized. Check storage permissions "
                "and use Update batch folders."
            )
