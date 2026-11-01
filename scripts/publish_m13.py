"""Publish development-reviewed detector data through the existing admin workflow."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from backend.cli_io import write_report, write_text_report
from backend.core.batch import BatchService
from backend.core.engines.local_bge import LocalBGE
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.policy_manager import PolicyManager
from backend.core.policy_models import Preview, PreviewEntry
from backend.core.policy_validate import candidate_registry
from backend.core.rules_loader import load_rules
from backend.core.settings import load_settings
from backend.core.specificity import SpecificityEngine
from backend.eval.split import case_ids

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path("/Users/mpatel/Downloads/SPR Fake Papers with Triggers/Tests")


def main() -> None:
    before = load_rules(ROOT)
    candidate = candidate_registry((ROOT / "reports/m13/candidate-rules.yaml").read_text())
    if [i.detectors for i in (*before.list1, *before.list2)] == [
        i.detectors for i in (*candidate.list1, *candidate.list2)
    ]:
        raise ValueError("This exact M13 detector candidate is already published")
    text = yaml.safe_dump(
        candidate.model_copy(update={"policy_version": before.policy_version}).model_dump(
            mode="json"
        ),
        sort_keys=False,
        allow_unicode=True,
    )
    settings_path = ROOT / "config/settings.yaml"
    settings = yaml.safe_load(settings_path.read_text())
    settings["semantic"].update(mid_threshold=0.84, high_threshold=0.86)
    write_text_report(settings_path, yaml.safe_dump(settings, sort_keys=False))
    configuration = load_settings(ROOT)
    provider = LocalBGE(ROOT)
    private_root = ROOT / "reports/m13/runtime-root"
    semantic = SemanticEngine(private_root, before, configuration.semantic, provider=provider)
    service = BatchService(
        private_root,
        before,
        RulesEngine(before),
        semantic=semantic,
        specificity=SpecificityEngine(ROOT, before),
    )
    manager = PolicyManager(ROOT, service, lambda context: None)
    try:
        draft = manager.create()
        draft = manager.edit(draft.draft_id, draft.revision, text)
        draft = manager.validate(draft.draft_id, draft.revision)
        if not draft.validation or not draft.validation.valid:
            raise ValueError("Candidate validation failed")
        preview_id = uuid4().hex
        directory = manager.previews.path(preview_id)
        directory.mkdir(parents=True, mode=0o700)
        entries = []
        for n, case_id in enumerate(case_ids("dev")):
            path = next(
                p for p in (SOURCE / f"{case_id}.docx", SOURCE / f"{case_id}.pdf") if p.is_file()
            )
            data = path.read_bytes()
            target = directory / f"{n}.source"
            target.write_bytes(data)
            target.chmod(0o600)
            entries.append(
                PreviewEntry(file_name=path.name, sha256=hashlib.sha256(data).hexdigest())
            )
        preview = Preview(
            preview_id=preview_id,
            draft_id=draft.draft_id,
            draft_sha256=draft.validation.yaml_sha256,
            base_sha256=draft.base_sha256,
            entries=tuple(entries),
            created_utc=datetime.now(UTC),
        )
        manager.start_preview(draft.draft_id, draft.revision, preview)
        print("Admin preview: comparing 60 explicitly supplied development papers", flush=True)
        manager.previews.worker.submit(lambda: None).result()
        preview = manager.previews.read(preview_id)
        if not preview.eligible:
            raise ValueError("Policy impact preview did not complete successfully")
        draft = manager.read(draft.draft_id)
        active = manager.publish(
            draft.draft_id,
            draft.revision,
            preview_id,
            "User-authorized M13 development-only detector improvements; "
            "official wording unchanged; "
            "semantic bands 0.84/0.86; original M12 results preserved; no holdout reuse.",
        )
        write_report(
            ROOT / "reports/m13/publication.json",
            dict(
                policy=active.model_dump(mode="json"),
                draft_id=draft.draft_id,
                preview_id=preview_id,
                compared_papers=len(entries),
                changed_papers=sum(e.changed for e in preview.entries),
                actor_note=(
                    "Engineering publication authorized by the user; "
                    "existing trusted admin service workflow."
                ),
            ),
        )
        print(
            json.dumps(dict(version=active.version, compared=len(entries), published=True)),
            flush=True,
        )
    finally:
        manager.previews.close()
        service.close()


if __name__ == "__main__":
    main()
