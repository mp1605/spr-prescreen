"""Revision-protected policy workflow; publication and rollback create immutable versions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from backend.cli_io import write_report
from backend.core.batch import BatchService
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.policy_disk import Publication, commit_publication
from backend.core.policy_models import Draft, PolicyConflict, PolicyInputError, Preview
from backend.core.policy_preview import PreviewService
from backend.core.policy_validate import candidate_registry, validate_candidate
from backend.core.rules_loader import ActivePolicy, RuleRegistry, load_rules, load_yaml
from backend.core.screening_context import ScreeningContext
from backend.core.specificity import SpecificityEngine


class PolicyManager:
    def __init__(
        self, root: Path, service: BatchService, on_install: Callable[[ScreeningContext], None]
    ) -> None:
        self.root, self.service, self.on_install = root, service, on_install
        self.lock = service.store.lock
        self.previews = PreviewService(root, self.lock, self.preview_finished)
        self.previews.ai = service.ai

    def path(self, identifier: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise KeyError("Draft not found")
        return self.root / "policies/drafts" / f"{identifier}.json"

    def read(self, identifier: str) -> Draft:
        try:
            draft = Draft.model_validate_json(self.path(identifier).read_bytes())
        except FileNotFoundError as exc:
            raise KeyError("Draft not found") from exc
        if draft.state == "previewing" and self.previews.active != draft.preview_id:
            # No worker survived a restart. Never treat a partial preview as publishable.
            draft = draft.model_copy(
                update={"state": "validated", "preview_id": None, "revision": draft.revision + 1}
            )
            self.save(draft)
        return draft

    def save(self, draft: Draft) -> Draft:
        write_report(self.path(draft.draft_id), draft.model_dump(mode="json"))
        return draft

    def current(self) -> tuple[RuleRegistry, ActivePolicy]:
        rules = load_rules(self.root)
        active = ActivePolicy.model_validate_json((self.root / "policies/active.json").read_bytes())
        if rules.policy_version != self.service.rules.policy_version:
            raise PolicyConflict(
                "Policy changed in another process. Restart this service before editing."
            )
        return rules, active

    def checked(self, identifier: str, revision: int) -> Draft:
        draft = self.read(identifier)
        if draft.revision != revision:
            raise PolicyConflict("Draft changed in another window. Reload it before continuing.")
        if draft.state == "published":
            raise PolicyConflict("This draft was published. Create a new draft.")
        _, active = self.current()
        if active.sha256 != draft.base_sha256:
            raise PolicyConflict(
                "Active rules changed. Create a fresh draft from the current version."
            )
        return draft

    def history(self) -> list[dict[str, object]]:
        records = []
        audit_path = self.root / "policies/audit.log"
        events = (
            [json.loads(line) for line in audit_path.read_bytes().splitlines()]
            if audit_path.exists()
            else []
        )
        checksums = {
            event["version"]: event["sha256"]
            for event in events
            if "version" in event and "sha256" in event
        }
        paths = [
            p
            for p in (self.root / "policies/versions").glob("rules_v*.yaml")
            if re.fullmatch(r"rules_v\d+\.yaml", p.name)
        ]
        for path in sorted(paths, key=lambda p: int(p.stem.removeprefix("rules_v"))):
            registry = RuleRegistry.model_validate(load_yaml(path))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            expected = checksums.get(registry.policy_version)
            if expected and expected != digest:
                raise PolicyInputError(
                    "An archived policy failed its audit checksum. Inspect policy integrity."
                )
            records.append(
                {
                    "file": path.name,
                    "version": registry.policy_version,
                    "sha256": digest,
                    "restorable": bool(expected)
                    and all(item.detectors for item in (*registry.list1, *registry.list2)),
                }
            )
        return records

    def create(self, restore_from: str | None = None) -> Draft:
        with self.lock:
            rules, active = self.current()
            text = (self.root / "policies/official_rules.yaml").read_text()
            if restore_from:
                if restore_from not in {row["file"] for row in self.history() if row["restorable"]}:
                    raise KeyError("Policy version not found")
                restored = candidate_registry(
                    (self.root / "policies/versions" / restore_from).read_text()
                )
                text = yaml.safe_dump(
                    restored.model_copy(update={"policy_version": rules.policy_version}).model_dump(
                        mode="json"
                    ),
                    sort_keys=False,
                    allow_unicode=True,
                )
            now = datetime.now(UTC)
            return self.save(
                Draft(
                    draft_id=uuid4().hex,
                    created_utc=now,
                    updated_utc=now,
                    base_version=active.version,
                    base_sha256=active.sha256,
                    yaml_text=text,
                    restore_from=restore_from,
                )
            )

    def edit(self, identifier: str, revision: int, text: str) -> Draft:
        with self.lock:
            draft = self.checked(identifier, revision)
            return self.save(
                draft.model_copy(
                    update={
                        "revision": revision + 1,
                        "yaml_text": text,
                        "validation": None,
                        "preview_id": None,
                        "state": "draft",
                        "updated_utc": datetime.now(UTC),
                    }
                )
            )

    def validate(self, identifier: str, revision: int) -> Draft:
        with self.lock:
            draft = self.checked(identifier, revision)
            validation = validate_candidate(draft.yaml_text, self.service.rules)
            return self.save(
                draft.model_copy(
                    update={
                        "validation": validation,
                        "revision": revision + 1,
                        "preview_id": None,
                        "state": "validated" if validation.valid else "draft",
                    }
                )
            )

    def context(self, rules: RuleRegistry) -> ScreeningContext:
        current = self.service.semantic
        semantic = (
            SemanticEngine(self.root, rules, current.settings, provider=current.provider)
            if current
            else None
        )
        return ScreeningContext(
            rules, RulesEngine(rules), semantic, SpecificityEngine(self.root, rules)
        )

    def start_preview(self, identifier: str, revision: int, preview: Preview) -> Draft:
        with self.lock:
            draft = self.checked(identifier, revision)
            if self.previews.active:
                raise PolicyConflict("An impact preview is already running. Wait for it to finish.")
            if (
                not draft.validation
                or not draft.validation.valid
                or draft.validation.yaml_sha256 != preview.draft_sha256
            ):
                raise PolicyInputError("Validate this exact draft before previewing.")
            candidate = candidate_registry(draft.yaml_text).model_copy(
                update={"policy_version": f"preview-{identifier[:8]}-r{revision}"}
            )
            before = self.service.contexts[self.service.rules.policy_version]
            self.previews.submit(preview, before, self.context(candidate))
            return self.save(
                draft.model_copy(
                    update={
                        "state": "previewing",
                        "preview_id": preview.preview_id,
                        "revision": revision + 1,
                    }
                )
            )

    def preview_finished(self, preview: Preview) -> None:
        # Called under the same lock, after the worker has saved its final report.
        draft = Draft.model_validate_json(self.path(preview.draft_id).read_bytes())
        if draft.preview_id == preview.preview_id and draft.state == "previewing":
            self.save(
                draft.model_copy(
                    update={
                        "state": "previewed" if preview.eligible else "validated",
                        "revision": draft.revision + 1,
                    }
                )
            )

    def publish(self, identifier: str, revision: int, preview_id: str, note: str) -> ActivePolicy:
        with self.lock:
            draft = self.checked(identifier, revision)
            preview = self.previews.read(preview_id)
            digest = hashlib.sha256(draft.yaml_text.encode()).hexdigest()
            if (
                draft.preview_id != preview_id
                or draft.state != "previewed"
                or not preview.eligible
                or preview.state != "complete"
                or preview.draft_sha256 != digest
                or preview.base_sha256 != draft.base_sha256
            ):
                raise PolicyInputError(
                    "Complete and inspect an eligible impact preview of this exact draft "
                    "before publication."
                )
            validation = validate_candidate(draft.yaml_text, self.service.rules)
            if not validation.valid:
                raise PolicyInputError("Draft validation no longer passes.")
            numbers = [
                int(Path(str(row["file"])).stem.removeprefix("rules_v")) for row in self.history()
            ]
            number = max(numbers, default=0) + 1
            registry = candidate_registry(draft.yaml_text).model_copy(
                update={"policy_version": f"LOE2-guide-v{number}-admin"}
            )
            context = self.context(registry)
            content = yaml.safe_dump(
                registry.model_dump(mode="json"), sort_keys=False, allow_unicode=True
            )
            _, previous = self.current()
            now = datetime.now(UTC)
            active = ActivePolicy(
                version=registry.policy_version,
                sha256=hashlib.sha256(content.encode()).hexdigest(),
                published_by="local admin",
                utc=now.isoformat(),
                change_note=note.strip(),
            )
            event = {
                "event_id": uuid4().hex,
                "operation": "rollback" if draft.restore_from else "publish",
                "actor": "local admin",
                "utc": now.isoformat(),
                "version": active.version,
                "sha256": active.sha256,
                "previous_sha256": previous.sha256,
                "note": note.strip(),
                "draft_id": identifier,
                "preview_id": preview_id,
                "restored_from": draft.restore_from,
            }
            commit_publication(
                self.root,
                Publication(
                    previous=previous,
                    next=active,
                    yaml_text=content,
                    archive=f"rules_v{number}.yaml",
                    event=event,
                ),
            )
            self.service.install(context)
            self.on_install(context)
            self.save(
                draft.model_copy(
                    update={
                        "state": "published",
                        "published_version": active.version,
                        "revision": revision + 1,
                    }
                )
            )
            return active
