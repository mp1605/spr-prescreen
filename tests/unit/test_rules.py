import hashlib
import json
from pathlib import Path

import pytest
import yaml

from backend.app import create_app
from backend.core.rules_loader import PolicyError, load_rules
from backend.core.settings import load_settings


def write_rules(root: Path, data: dict, *, update_hash: bool = True) -> None:
    path = root / "policies/official_rules.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))
    if update_hash:
        active = root / "policies/active.json"
        manifest = json.loads(active.read_text())
        manifest["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        active.write_text(json.dumps(manifest))


def read_rules(root: Path) -> dict:
    return yaml.safe_load((root / "policies/official_rules.yaml").read_text())


def test_official_counts_order_and_no_short_circuit(project_root):
    rules = load_rules(project_root)
    assert len(rules.list1) == 8
    assert len(rules.list2) == 31
    assert "L1-2" not in {r.id for r in rules.list1}
    assert rules.list_execution_order == ("list1", "list2")
    assert rules.short_circuit is False
    assert all(r.detectors for r in (*rules.list1, *rules.list2))


@pytest.mark.parametrize("change", ["missing", "duplicate", "invented", "reordered"])
def test_invalid_policy_ids_fail_startup(project_root, change):
    data = read_rules(project_root)
    if change == "missing":
        data["list2"].pop()
    elif change == "duplicate":
        data["list2"][1] = data["list2"][0]
    elif change == "invented":
        data["list1"][0]["id"] = "L1-2"
    else:
        data["list2"].reverse()
    write_rules(project_root, data)
    with pytest.raises(PolicyError, match="Policy startup validation failed"):
        create_app(project_root)


@pytest.mark.parametrize("payload", ["list1: [", "[]", "null", "list1: []\nlist1: []\n"])
def test_malformed_yaml_fails_startup_clearly(project_root, payload):
    (project_root / "policies/official_rules.yaml").write_text(payload)
    with pytest.raises(PolicyError, match="YAML|validation failed"):
        create_app(project_root)


@pytest.mark.parametrize("reference", ["L2-99", "L2-01"])
def test_bad_detector_references_rejected(project_root, reference):
    data = read_rules(project_root)
    data["list1"][0]["detectors"] = [
        dict(
            kind="regex",
            name="test",
            item_id=reference,
            pattern="policy",
        )
    ]
    write_rules(project_root, data)
    with pytest.raises(PolicyError, match="detector item ID|owning item"):
        load_rules(project_root)


def test_invalid_regex_rejected(project_root):
    data = read_rules(project_root)
    data["list1"][0]["detectors"] = [
        dict(
            kind="regex",
            name="test",
            item_id="L1-1",
            pattern="[",
        )
    ]
    write_rules(project_root, data)
    with pytest.raises(PolicyError, match="Invalid regex"):
        load_rules(project_root)


def test_invalid_context_regex_rejected_at_startup(project_root):
    data = read_rules(project_root)
    data["list1"][0]["detectors"][0]["context_pattern"] = "["
    write_rules(project_root, data)
    with pytest.raises(PolicyError, match="Invalid context regex"):
        create_app(project_root)


def test_item_without_detectors_cannot_silently_produce_green(project_root):
    data = read_rules(project_root)
    data["list2"][0]["detectors"] = []
    write_rules(project_root, data)
    with pytest.raises(PolicyError, match="No rules detectors configured"):
        create_app(project_root)


def test_official_wording_is_unchanged_by_engineering_detector_updates(project_root):
    baseline = json.loads((project_root / "docs/policy-baseline.json").read_text())
    data = read_rules(project_root)
    for group in ("list1", "list2"):
        for original, current in zip(baseline[group], data[group], strict=True):
            for key in ("id", "text", "category", "examples", "source_pages"):
                assert original.get(key) == current.get(key)


def test_manual_edit_rejected(project_root):
    data = read_rules(project_root)
    data["list1"][0]["text"] += " changed"
    write_rules(project_root, data, update_hash=False)
    with pytest.raises(PolicyError, match="Rules changed outside the admin editor"):
        create_app(project_root)


def test_source_tampering_rejected(project_root):
    with (project_root / "docs/official-lists.pdf").open("ab") as source:
        source.write(b"changed")
    with pytest.raises(PolicyError, match="source PDF failed"):
        create_app(project_root)


@pytest.mark.parametrize(
    "field,value",
    [
        ("short_circuit", True),
        ("list_execution_order", ["list2", "list1"]),
        ("color_rules", {"list1_any_hit": "green"}),
    ],
)
def test_official_execution_and_color_rules_cannot_change(project_root, field, value):
    data = read_rules(project_root)
    data[field] = value
    write_rules(project_root, data)
    with pytest.raises(PolicyError):
        create_app(project_root)


@pytest.mark.parametrize(
    "section,key,value",
    [
        (None, "host", "0.0.0.0"),
        ("evaluation", "sponsor_material_access", True),
        ("evaluation", "exemplar_source", "answer_keys"),
        ("ai", "enabled", True),
        ("semantic", "mid_threshold", 0.9),
    ],
)
def test_unsafe_or_invalid_settings_rejected(project_root, section, key, value):
    path = project_root / "config/settings.yaml"
    data = yaml.safe_load(path.read_text())
    (data[section] if section else data)[key] = value
    path.write_text(yaml.safe_dump(data))
    with pytest.raises(PolicyError, match="Invalid settings"):
        load_settings(project_root)
