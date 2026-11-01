"""Bounded-memory reads. Oversize rejections retain a full-file SHA-256 identity."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.cli_io import source_allowed
from backend.core.ingest import DocumentInput, parse_many
from backend.core.ingest_models import IngestLimits, ParseIssue, ParseResult
from backend.core.rules_loader import StrictModel, Text


class InputProblem(StrictModel):
    file_name: Text
    paper_id: Literal[None] = None
    status: Literal["incomplete"] = "incomplete"
    review_color: Literal["yellow"] = "yellow"
    code: Literal["input_unreadable"] = "input_unreadable"
    screening_state: Literal["NOT_SCREENED"] = "NOT_SCREENED"


@dataclass(frozen=True)
class LoadedBatch:
    slots: tuple[DocumentInput | ParseResult, ...]
    input_errors: tuple[InputProblem, ...]
    limits: IngestLimits

    def parse(self, cache_directory: Path | None, workers: int) -> tuple[ParseResult, ...]:
        inputs = [slot for slot in self.slots if isinstance(slot, DocumentInput)]
        parsed = iter(
            parse_many(inputs, cache_directory=cache_directory, limits=self.limits, workers=workers)
        )
        return tuple(slot if isinstance(slot, ParseResult) else next(parsed) for slot in self.slots)


def read_batch(paths: Sequence[Path], limits: IngestLimits) -> LoadedBatch:
    if len(paths) > limits.max_batch_files:
        raise ValueError("Batch exceeds the 100-file limit.")
    if any(not source_allowed(path) for path in paths):
        raise ValueError(
            "Answer keys, expected-result files, indexes, and holdout directories are blocked."
        )
    slots: list[DocumentInput | ParseResult] = []
    errors: list[InputProblem] = []
    for path in paths:
        try:
            slots.append(read_input(path, limits))
        except OSError:
            errors.append(InputProblem(file_name=path.name))
    return LoadedBatch(tuple(slots), tuple(errors), limits)


def read_input(path: Path, limits: IngestLimits) -> DocumentInput | ParseResult:
    if not path.is_file():
        raise OSError("Input is not a regular file")
    digest = hashlib.sha256()
    chunks: list[bytes] = []
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            if size <= limits.max_file_bytes:
                chunks.append(chunk)
            else:
                chunks.clear()
    if size <= limits.max_file_bytes:
        return DocumentInput(path.name, b"".join(chunks))
    kind: Literal["pdf", "docx"] | None = None
    if path.suffix.casefold() == ".pdf":
        kind = "pdf"
    elif path.suffix.casefold() == ".docx":
        kind = "docx"
    return ParseResult(
        paper_id="sha256:" + digest.hexdigest(),
        file_name=path.name,
        file_type=kind,
        byte_count=size,
        status="rejected",
        issues=(
            ParseIssue(
                code="file_too_large",
                message="File exceeds the configured byte limit.",
            ),
        ),
    )
