"""Publish reviewed detector data using validate/explicit-upload preview/publish."""

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import yaml

from backend.cli_io import write_report
from backend.core.batch import BatchService
from backend.core.engines.local_bge import LocalBGE
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.policy_manager import PolicyManager
from backend.core.policy_models import Preview, PreviewEntry
from backend.core.policy_validate import candidate_registry
from backend.core.rules_loader import load_rules
from backend.core.runtime import configure_offline_environment
from backend.core.settings import load_settings
from backend.core.specificity import SpecificityEngine

ROOT = Path(__file__).resolve().parents[1]


def main():
    configure_offline_environment(ROOT)
    output = ROOT / "reports/accuracy-v2"
    latest = Path(json.loads((output / "latest.json").read_text())["directory"])
    before = load_rules(ROOT)
    candidate = candidate_registry((latest / "candidate-rules.yaml").read_text())
    report = json.loads((latest / "report.json").read_text())
    if not report["trigger_recall"] > 0.90 or not report["paper_color_accuracy"] > 0.90:
        raise ValueError("Development acceptance targets have not passed")
    original = [i.model_dump(exclude={"detectors"}) for i in (*before.list1, *before.list2)]
    revised = [i.model_dump(exclude={"detectors"}) for i in (*candidate.list1, *candidate.list2)]
    assert original == revised, "Official policy wording must remain unchanged"
    if [i.detectors for i in (*before.list1, *before.list2)] == [
        i.detectors for i in (*candidate.list1, *candidate.list2)
    ]:
        raise ValueError("This detector candidate is already active")
    private = output / "publication-runtime"
    for destination in (private, ROOT):
        target = destination / "runs/cache/semantic"
        target.mkdir(parents=True, exist_ok=True)
        for source in (output / "runtime-cache/runs/cache/semantic").iterdir():
            if source.is_file() and not (target / source.name).exists():
                shutil.copy2(source, target / source.name)
    settings = load_settings(ROOT)
    semantic = SemanticEngine(private, before, settings.semantic, provider=LocalBGE(ROOT))
    service = BatchService(
        private,
        before,
        RulesEngine(before),
        semantic=semantic,
        specificity=SpecificityEngine(ROOT, before),
    )
    manager = PolicyManager(ROOT, service, lambda context: None)
    try:
        text = yaml.safe_dump(
            candidate.model_copy(update={"policy_version": before.policy_version}).model_dump(
                mode="json"
            ),
            sort_keys=False,
            allow_unicode=True,
        )
        draft = manager.create()
        draft = manager.edit(draft.draft_id, draft.revision, text)
        draft = manager.validate(draft.draft_id, draft.revision)
        assert draft.validation and draft.validation.valid
        identifier = uuid4().hex
        directory = manager.previews.path(identifier)
        directory.mkdir(parents=True, mode=0o700)
        source = Path("/Users/mpatel/Downloads/SPR Fake Papers with Triggers/Tests")
        entries = []
        for n in range(1, 81):
            paper = next(
                p
                for p in (source / f"SPR-Test-{n:03d}.docx", source / f"SPR-Test-{n:03d}.pdf")
                if p.is_file()
            )
            data = paper.read_bytes()
            copy = directory / f"{n - 1}.source"
            copy.write_bytes(data)
            copy.chmod(0o600)
            entries.append(
                PreviewEntry(file_name=paper.name, sha256=hashlib.sha256(data).hexdigest())
            )
        preview = Preview(
            preview_id=identifier,
            draft_id=draft.draft_id,
            draft_sha256=draft.validation.yaml_sha256,
            base_sha256=draft.base_sha256,
            entries=tuple(entries),
            created_utc=datetime.now(UTC),
        )
        manager.start_preview(draft.draft_id, draft.revision, preview)
        print(
            "Validated; comparing 80 explicit uploads through the policy impact preview", flush=True
        )
        manager.previews.worker.submit(lambda: None).result()
        preview = manager.previews.read(identifier)
        if not preview.eligible:
            raise ValueError("Policy impact preview failed")
        draft = manager.read(draft.draft_id)
        active = manager.publish(
            draft.draft_id,
            draft.revision,
            identifier,
            "User-authorized accuracy development on all 80 exposed papers; "
            "official items and scoring unchanged; no unseen validation claim; AI off.",
        )
        write_report(
            output / "publication.json",
            {
                "policy": active.model_dump(mode="json"),
                "draft_id": draft.draft_id,
                "preview_id": identifier,
                "compared_papers": len(entries),
                "changed_papers": sum(e.changed for e in preview.entries),
                "official_wording_unchanged": True,
                "unseen_validation": False,
                "note": "Preview compares detector snapshots under the revised source code; "
                "the original pre-change full regression is separately preserved.",
            },
        )
        print(f"Published {active.version}", flush=True)
    finally:
        manager.previews.close()
        service.close()


if __name__ == "__main__":
    main()
