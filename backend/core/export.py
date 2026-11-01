"""Export only explicitly requested runs, from one locked results/review snapshot."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from backend.cli_io import write_report
from backend.core.annotate import annotate, renderer_digest
from backend.core.annotation_notes import AnnotationError, overridden
from backend.core.export_csv import report_csv
from backend.core.export_io import write_binary
from backend.core.export_models import AnnotationManifest, ExportReport, SourceIntegrity
from backend.core.policy import DISCLAIMER
from backend.core.review_store import ReviewStore
from backend.core.run_store import RunStore


class ExportNotReady(ValueError):
    pass


def download_name(name: str, suffix: str) -> str:
    # Content-Disposition and output paths never incorporate unchecked upload text.
    stem = Path(name).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")[:100] or "document"
    return stem + suffix


class ExportService:
    def __init__(self, store: RunStore, reviews: ReviewStore) -> None:
        self.store, self.reviews = store, reviews
        self.lock = RLock()

    def snapshot(self, run_id: str) -> ExportReport:
        with self.store.lock:
            batch = self.store.read(run_id)
            reviews = {
                entry.entry_id: self.reviews.state(run_id, entry.entry_id)
                for entry in batch.entries
            }
            sources: dict[str, str | None] = {}
            current: dict[str, str | None] = {}
            integrity: dict[str, SourceIntegrity] = {}
            for entry in batch.entries:
                source = self.store.source(run_id, entry.entry_id)
                digest = None
                if source.is_file():
                    with source.open("rb") as handle:
                        digest = hashlib.file_digest(handle, "sha256").hexdigest()
                expected = entry.result.paper_id.removeprefix("sha256:") if entry.result else None
                sources[entry.entry_id] = expected or digest
                current[entry.entry_id] = digest
                integrity[entry.entry_id] = (
                    "verified"
                    if expected and expected == digest
                    else "unavailable"
                    if expected and digest is None
                    else "mismatch"
                    if expected
                    else "not_screened"
                    if digest
                    else "not_retained"
                )
            return ExportReport(
                generated_utc=datetime.now(UTC),
                disclaimer=DISCLAIMER,
                batch=batch,
                source_sha256=sources,
                current_source_sha256=current,
                source_integrity=integrity,
                reviews=reviews,
            )

    def report(self, run_id: str, format: str) -> tuple[bytes, str, str]:
        # Serialize/save together so concurrently requested CSV and JSON downloads each
        # represent their own explicit snapshot; no results or decisions are overwritten.
        with self.lock:
            snapshot = self.snapshot(run_id)
            if format == "json":
                data = (snapshot.model_dump_json(indent=2) + "\n").encode()
                media = "application/json"
            elif format == "csv":
                data = report_csv(snapshot).encode("utf-8-sig")
                media = "text/csv; charset=utf-8"
            else:
                raise ValueError("Unknown report format")
            write_binary(self.store.path(run_id) / f"report.{format}", data)
            return data, media, f"{run_id}-report.{format}"

    def annotated(
        self, run_id: str, entry_id: str, *, notes: bool = False
    ) -> tuple[Path, AnnotationManifest]:
        with self.lock:
            with self.store.lock:
                entry = self.store.entry(run_id, entry_id)
                if entry.phase != "done" or entry.result is None:
                    raise ExportNotReady(
                        "Wait for screening to finish before downloading an annotated copy."
                    )
                paper = entry.result
                parsed = self.store.parsed(run_id, entry_id)
                review = self.reviews.state(run_id, entry_id)
                try:
                    data = self.store.source(run_id, entry_id).read_bytes()
                except FileNotFoundError as exc:
                    raise AnnotationError(
                        "Original file is unavailable. Export the screening report instead."
                    ) from exc
            digest = hashlib.sha256(data).hexdigest()
            if digest != paper.paper_id.removeprefix("sha256:"):
                raise AnnotationError(
                    "Original SHA-256 does not match the stored screening result."
                )
            identity = hashlib.sha256(
                json.dumps(
                    [
                        "annotation-v2",
                        notes,
                        renderer_digest(),
                        paper.model_dump(mode="json"),
                        review.model_dump(mode="json"),
                    ],
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            folder = self.store.path(run_id) / "annotated"
            output = folder / f"{entry_id}-{identity}.{paper.file_type}"
            metadata = output.with_suffix(".manifest.json")
            if output.is_file() and metadata.is_file():
                manifest = AnnotationManifest.model_validate_json(metadata.read_bytes())
                with output.open("rb") as handle:
                    intact = (
                        hashlib.file_digest(handle, "sha256").hexdigest()
                        == manifest.annotated_sha256
                    )
                if (
                    intact
                    and manifest.source_sha256 == digest
                    and manifest.review_revision == review.revision
                ):
                    return output, manifest
            artifact = annotate(data, parsed, paper, review, notes=notes)
            manifest = AnnotationManifest(
                run_id=run_id,
                entry_id=entry_id,
                original_file_name=entry.file_name,
                download_file_name=download_name(entry.file_name, f"-annotated.{paper.file_type}"),
                source_sha256=digest,
                annotated_sha256=hashlib.sha256(artifact.data).hexdigest(),
                rules_version=paper.rules_version,
                ai_state=paper.ai_state,
                review_revision=review.revision,
                created_utc=datetime.now(UTC),
                findings_annotated=sum(not overridden(flag, review) for flag in paper.findings),
                overridden_findings=sum(overridden(flag, review) for flag in paper.findings),
                notes_included=notes,
                warnings=artifact.warnings,
                disclaimer=DISCLAIMER,
            )
            write_binary(output, artifact.data)
            write_report(metadata, manifest.model_dump(mode="json"))
            return output, manifest
