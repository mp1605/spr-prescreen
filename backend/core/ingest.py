"""Bytes-only ingestion boundary, ready for the later batch API and scanner."""

from __future__ import annotations

import hashlib
import multiprocessing
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.core.docx_ingest import parse_docx
from backend.core.ingest_models import IngestLimits, ParseIssue, ParseResult
from backend.core.pdf_ingest import parse_pdf
from backend.core.store import ParseCache, parse_payload
from backend.core.text_segments import segments_for


@dataclass(frozen=True)
class DocumentInput:
    file_name: str
    data: bytes


def safe_name(name: str) -> str:
    return name.replace("\\", "/").rsplit("/", 1)[-1].strip() or "unnamed"


def _identity(name: str, data: bytes) -> tuple[str, str, Literal["pdf", "docx"] | None]:
    name = safe_name(name)
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    kind: Literal["pdf", "docx"] | None = None
    if suffix == "pdf":
        kind = "pdf"
    elif suffix == "docx":
        kind = "docx"
    return "sha256:" + hashlib.sha256(data).hexdigest(), name, kind


def _with_metadata(result: ParseResult, name: str, state: str) -> ParseResult:
    return ParseResult.model_validate(
        parse_payload(result) | {"file_name": name, "cache_state": state}
    )


def parse_document(
    file_name: str,
    data: bytes,
    *,
    cache_directory: Path | None = None,
    limits: IngestLimits | None = None,
) -> ParseResult:
    limits = limits or IngestLimits()
    paper_id, name, kind = _identity(file_name, data)
    identity = dict(paper_id=paper_id, file_name=name, file_type=kind, byte_count=len(data))
    if kind is None or len(data) > limits.max_file_bytes:
        issue = (
            ParseIssue(code="unsupported_format", message="Only PDF and DOCX files are accepted.")
            if kind is None
            else ParseIssue(
                code="file_too_large", message="File exceeds the configured byte limit."
            )
        )
        return ParseResult.model_validate(identity | dict(status="rejected", issues=[issue]))

    cache = ParseCache(cache_directory, limits) if cache_directory is not None else None
    if cache is not None:
        cached = cache.read(paper_id, kind)
        if cached is not None and cached.byte_count == len(data):
            return _with_metadata(cached, name, "hit")
    try:
        units, issues = parse_pdf(data, limits) if kind == "pdf" else parse_docx(data, limits)
        unit_segments = {unit.unit_id: segments_for(unit) for unit in units}
        segments = tuple(segment for group in unit_segments.values() for segment in group)
        for unit in units:
            if (
                unit.page is not None
                and not unit_segments[unit.unit_id]
                and not any(i.page == unit.page for i in issues)
            ):
                issues.append(
                    ParseIssue(
                        code="unreadable_page",
                        page=unit.page,
                        message="Page has no screening text after documented noise removal.",
                    )
                )
        if not segments and not issues:
            issues.append(
                ParseIssue(code="no_readable_text", message="No screening text could be extracted.")
            )
        result = ParseResult.model_validate(
            identity
            | dict(
                status="incomplete" if issues else "complete",
                units=units,
                segments=segments,
                issues=issues,
                cache_state="miss" if cache else "disabled",
            )
        )
    except Exception:
        result = ParseResult.model_validate(
            identity
            | dict(
                status="incomplete",
                issues=[
                    ParseIssue(
                        code="parser_error",
                        message="Extraction failed; human source inspection is required.",
                    ),
                ],
            )
        )
    if cache is not None:
        try:
            cache.write(result)
        except OSError:
            # Cache availability does not change the evidence or completeness of a fresh parse.
            result = _with_metadata(result, name, "unavailable")
    return result


def _parse_worker(args: tuple[DocumentInput, Path | None, IngestLimits]) -> ParseResult:
    document, cache, limits = args
    return parse_document(document.file_name, document.data, cache_directory=cache, limits=limits)


def parse_many(
    documents: Iterable[DocumentInput],
    *,
    cache_directory: Path | None = None,
    limits: IngestLimits | None = None,
    workers: int = 2,
) -> tuple[ParseResult, ...]:
    """Bounded, ordered parsing. A corrupt file yields its own incomplete result."""
    from backend.security.airlock import install_airlock, shared_counter

    install_airlock()
    limits = limits or IngestLimits()
    if not 1 <= workers <= 4:
        raise ValueError("Use between 1 and 4 parsing workers")
    inputs: list[DocumentInput] = []
    for document in documents:
        if len(inputs) == limits.max_batch_files:
            raise ValueError("Batch exceeds the configured file-count limit")
        inputs.append(document)
    args = [(document, cache_directory, limits) for document in inputs]
    if workers == 1 or not args:
        return tuple(_parse_worker(arg) for arg in args)
    with ProcessPoolExecutor(
        max_workers=workers,
        mp_context=multiprocessing.get_context("spawn"),
        initializer=install_airlock,
        initargs=(shared_counter(),),
    ) as pool:
        futures = [pool.submit(_parse_worker, arg) for arg in args]
        results = []
        for document, future in zip(inputs, futures, strict=True):
            try:
                results.append(future.result())
            except Exception:
                paper_id, name, kind = _identity(document.file_name, document.data)
                results.append(
                    ParseResult(
                        paper_id=paper_id,
                        file_name=name,
                        file_type=kind,
                        byte_count=len(document.data),
                        status="incomplete",
                        issues=(
                            ParseIssue(
                                code="parser_error",
                                message="Parsing worker failed; other files continue.",
                            ),
                        ),
                    )
                )
    return tuple(results)
