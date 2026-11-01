"""Private atomic run snapshots and originals. Only browser-run directories are read."""

from __future__ import annotations

import os
import re
from pathlib import Path
from threading import RLock

from backend.cli_io import write_report
from backend.core.batch_models import TERMINAL, BatchEntry, BatchRecord
from backend.core.ingest_models import ParseResult
from backend.core.store import parse_payload


class RunStore:
    def __init__(self, root: Path) -> None:
        self.directory = root / "runs"
        self.lock = RLock()

    def path(self, run_id: str, entry_id: str | None = None) -> Path:
        if not re.fullmatch(r"web-[a-f0-9]{32}", run_id):
            raise KeyError("Run not found")
        path = self.directory / run_id
        if entry_id is not None:
            if not re.fullmatch(r"[a-f0-9]{32}", entry_id):
                raise KeyError("Upload not found")
            path = path / entry_id
        return path

    def read(self, run_id: str) -> BatchRecord:
        try:
            return BatchRecord.model_validate_json(
                (self.path(run_id) / "results.json").read_bytes()
            )
        except FileNotFoundError as exc:
            raise KeyError("Run not found") from exc

    def save(self, record: BatchRecord) -> None:
        write_report(self.path(record.run_id) / "results.json", record.model_dump(mode="json"))

    def list(self) -> tuple[BatchRecord, ...]:
        with self.lock:
            paths = sorted(self.directory.glob("web-*/results.json"))
            return tuple(
                sorted(
                    (self.read(p.parent.name) for p in paths),
                    key=lambda batch: batch.created,
                    reverse=True,
                )
            )

    def entry(self, run_id: str, entry_id: str) -> BatchEntry:
        batch = self.read(run_id)
        for entry in batch.entries:
            if entry.entry_id == entry_id:
                return entry
        raise KeyError("Upload not found")

    def update(self, run_id: str, entry: BatchEntry) -> None:
        with self.lock:
            batch = self.read(run_id)
            entries = tuple(entry if e.entry_id == entry.entry_id else e for e in batch.entries)
            self.save(batch.model_copy(update={"entries": entries, "revision": batch.revision + 1}))

    def source(self, run_id: str, entry_id: str) -> Path:
        return self.path(run_id, entry_id) / "source.bin"

    def save_source(self, run_id: str, entry_id: str, data: bytes) -> None:
        path = self.source(run_id, entry_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            handle.write(data)

    def save_parse(self, run_id: str, entry_id: str, parsed: ParseResult) -> None:
        write_report(self.path(run_id, entry_id) / "parsed.json", parse_payload(parsed))

    def parsed(self, run_id: str, entry_id: str) -> ParseResult:
        return ParseResult.model_validate_json(
            (self.path(run_id, entry_id) / "parsed.json").read_bytes()
        )

    def recover(self) -> None:
        """Do not silently resume jobs or reread originals after a process restart."""
        for batch in self.list():
            for entry in batch.entries:
                if entry.phase not in TERMINAL:
                    self.update(
                        batch.run_id,
                        entry.model_copy(
                            update={
                                "phase": "failed",
                                "message": "Interrupted by service restart. Retry this file.",
                            }
                        ),
                    )
