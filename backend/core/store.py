"""Atomic, versioned parse cache. No original documents or evaluation sources are opened."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import Field

from backend.core.ingest_models import PARSER_VERSION, IngestLimits, ParseResult
from backend.core.rules_loader import StrictModel


def parse_payload(result: ParseResult) -> dict[str, object]:
    return result.model_dump(mode="json", exclude={"review_color", "incomplete_pages"})


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()
    ).hexdigest()


class CacheEntry(StrictModel):
    cache_version: Literal[1]
    limits_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    result_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    result: ParseResult


class ParseCache:
    def __init__(self, directory: Path, limits: IngestLimits) -> None:
        self.directory = directory
        self.limits_digest = _digest(limits.model_dump(mode="json"))

    def _path(self, paper_id: str, file_type: str) -> Path:
        digest = paper_id.removeprefix("sha256:")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid cache document ID")
        if file_type not in ("pdf", "docx"):
            raise ValueError("Invalid cache format")
        return (
            self.directory
            / f"{digest}.{file_type}.v{PARSER_VERSION}.{self.limits_digest[:16]}.json"
        )

    def read(self, paper_id: str, file_type: str) -> ParseResult | None:
        try:
            entry = CacheEntry.model_validate_json(self._path(paper_id, file_type).read_bytes())
            result = entry.result
            if (
                entry.limits_digest != self.limits_digest
                or result.parser_version != PARSER_VERSION
                or result.paper_id != paper_id
                or result.file_type != file_type
                or _digest(parse_payload(result)) != entry.result_digest
            ):
                return None
            return result
        except (OSError, ValueError):
            return None

    def write(self, result: ParseResult) -> None:
        if result.file_type is None:
            return
        payload = parse_payload(result)
        entry = dict(
            cache_version=1,
            limits_digest=self.limits_digest,
            result_digest=_digest(payload),
            result=payload,
        )
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.directory,
                prefix=".parse-",
                suffix=".tmp",
                delete=False,
            ) as file:
                path = Path(file.name)
                json.dump(entry, file, ensure_ascii=True, separators=(",", ":"))
                file.flush()
                os.fsync(file.fileno())
            os.replace(path, self._path(result.paper_id, result.file_type))
        finally:
            if path is not None:
                path.unlink(missing_ok=True)
