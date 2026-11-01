"""Recoverable multi-file publication. The journal only finishes an authorized commit."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml

from backend.cli_io import write_report
from backend.core.export_io import write_binary
from backend.core.rules_loader import ActivePolicy, PolicyError, RuleRegistry, StrictModel


class Publication(StrictModel):
    previous: ActivePolicy
    next: ActivePolicy
    yaml_text: str
    archive: str
    event: dict[str, Any]


def append_audit(root: Path, event: dict[str, Any]) -> None:
    path = root / "policies/audit.log"
    if path.exists() and any(
        json.loads(line).get("event_id") == event["event_id"]
        for line in path.read_bytes().splitlines()
    ):
        return
    with path.open("ab") as handle:
        os.chmod(path, 0o600)
        handle.write((json.dumps(event, ensure_ascii=True) + "\n").encode())
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def publication_lock(root: Path) -> Iterator[None]:
    path = root / "policies/.publication.lock"
    with path.open("ab") as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def recover_publication(root: Path) -> None:
    with publication_lock(root):
        recover_publication_locked(root)


def recover_publication_locked(root: Path) -> None:
    folder = root / "policies"
    journal = folder / "publication.json"
    if not journal.exists():
        return
    try:
        transaction = Publication.model_validate_json(journal.read_bytes())
        content = transaction.yaml_text.encode()
        if hashlib.sha256(content).hexdigest() != transaction.next.sha256:
            raise ValueError("Publication checksum mismatch")
        registry = RuleRegistry.model_validate(yaml.safe_load(transaction.yaml_text))
        if registry.policy_version != transaction.next.version:
            raise ValueError("Publication version mismatch")
        if not re.fullmatch(r"rules_v\d+\.yaml", transaction.archive):
            raise ValueError("Publication path invalid")
        archive = folder / "versions" / transaction.archive
        if archive.read_bytes() != content:
            raise ValueError("Publication archive mismatch")
        current = ActivePolicy.model_validate_json((folder / "active.json").read_bytes())
        actual = hashlib.sha256((folder / "official_rules.yaml").read_bytes()).hexdigest()
        if current not in (transaction.previous, transaction.next) or actual not in (
            transaction.previous.sha256,
            transaction.next.sha256,
        ):
            raise ValueError("Files changed outside the prepared publication")
        write_binary(folder / "official_rules.yaml", content)
        write_report(folder / "active.json", transaction.next.model_dump(mode="json"))
        append_audit(root, transaction.event)
        journal.unlink()
    except (OSError, ValueError, KeyError) as exc:
        raise PolicyError(
            "Policy publication recovery failed; preserve the journal and inspect policy integrity."
        ) from exc


def commit_publication(root: Path, transaction: Publication) -> None:
    with publication_lock(root):
        folder = root / "policies"
        current = ActivePolicy.model_validate_json((folder / "active.json").read_bytes())
        actual = hashlib.sha256((folder / "official_rules.yaml").read_bytes()).hexdigest()
        if current != transaction.previous or actual != transaction.previous.sha256:
            raise PolicyError("Active policy changed before publication; refresh the service.")
        archive = folder / "versions" / transaction.archive
        archive.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with archive.open("xb") as handle:
            os.chmod(archive, 0o600)
            handle.write(transaction.yaml_text.encode())
            handle.flush()
            os.fsync(handle.fileno())
        write_report(folder / "publication.json", transaction.model_dump(mode="json"))
        recover_publication_locked(root)
