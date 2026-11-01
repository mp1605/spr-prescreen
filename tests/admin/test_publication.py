"""Mechanical commit/recovery and policy validation contracts; no document datasets."""

import hashlib
import json
from datetime import UTC, datetime

import pytest
import yaml

from backend.core import policy_disk
from backend.core.policy_disk import Publication, commit_publication, recover_publication
from backend.core.policy_validate import validate_candidate
from backend.core.rules_loader import ActivePolicy, PolicyError, load_rules


def transaction(root):
    previous = ActivePolicy.model_validate_json((root / "policies/active.json").read_bytes())
    number = 1 + max(
        int(p.stem.removeprefix("rules_v"))
        for p in (root / "policies/versions").glob("rules_v*.yaml")
    )
    rules = load_rules(root).model_copy(
        update={"policy_version": f"publication-contract-v{number}"}
    )
    text = yaml.safe_dump(rules.model_dump(mode="json"), sort_keys=False)
    active = ActivePolicy(
        version=rules.policy_version,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        published_by="Format QA",
        utc=datetime.now(UTC).isoformat(),
        change_note="Commit contract",
    )
    return Publication(
        previous=previous,
        next=active,
        yaml_text=text,
        archive=f"rules_v{number}.yaml",
        event={
            "event_id": "commit-contract",
            "operation": "publish",
            "version": active.version,
            "sha256": active.sha256,
        },
    )


@pytest.mark.parametrize("stage", ["mirror", "manifest", "audit"])
def test_interrupted_commit_recovers_once_without_losing_policy_or_audit(
    project_root, monkeypatch, stage
):
    command = transaction(project_root)
    binary = policy_disk.write_binary
    report = policy_disk.write_report
    audit = policy_disk.append_audit
    with monkeypatch.context() as patch:
        if stage == "mirror":

            def fail(path, data):
                binary(path, data)
                if path.name == "official_rules.yaml":
                    raise OSError("Mechanical interruption")

            patch.setattr(policy_disk, "write_binary", fail)
        elif stage == "manifest":

            def fail(path, data):
                report(path, data)
                if path.name == "active.json":
                    raise OSError("Mechanical interruption")

            patch.setattr(policy_disk, "write_report", fail)
        else:

            def fail(root, event):
                audit(root, event)
                raise OSError("Mechanical interruption")

            patch.setattr(policy_disk, "append_audit", fail)
        with pytest.raises(PolicyError):
            commit_publication(project_root, command)
    assert (project_root / "policies/publication.json").exists()
    assert load_rules(project_root).policy_version == command.next.version
    recover_publication(project_root)
    events = [
        json.loads(line) for line in (project_root / "policies/audit.log").read_bytes().splitlines()
    ]
    assert sum(e.get("event_id") == "commit-contract" for e in events) == 1
    assert not (project_root / "policies/publication.json").exists()
    assert (project_root / "policies/versions" / command.archive).read_text() == command.yaml_text


def test_prepared_transaction_does_not_hide_external_tampering(project_root, monkeypatch):
    command = transaction(project_root)
    with monkeypatch.context() as patch:
        patch.setattr(policy_disk, "recover_publication_locked", lambda root: None)
        commit_publication(project_root, command)
    with (project_root / "policies/official_rules.yaml").open("ab") as file:
        file.write(b"changed")
    with pytest.raises(PolicyError, match="recovery failed"):
        load_rules(project_root)


@pytest.mark.parametrize("text", ["list1: []\nlist1: []", "x: &value [1]\ny: *value", "[" * 100])
def test_ambiguous_or_excessive_yaml_is_refused(project_root, text):
    assert not validate_candidate(text, load_rules(project_root)).valid


def test_impact_comparison_ignores_new_ids_but_detects_reason_changes(project_root):
    from backend.core.ingest import parse_document
    from backend.core.policy_preview import signature
    from backend.core.screen import screen_document
    from tests.integration.test_workflow import word

    result = screen_document(
        parse_document("format.docx", word("Animal testing")), load_rules(project_root)
    )
    first = result.findings[0]
    renamed = result.model_copy(
        update={"findings": (first.model_copy(update={"finding_id": "new-version-id"}),)}
    )
    changed = result.model_copy(
        update={
            "findings": (first.model_copy(update={"reason": "Updated source-bound assessment"}),)
        }
    )
    assert signature(result) == signature(renamed)
    assert signature(result) != signature(changed)
