"""Normal upload reruns detectors; caches contain source representations, not expected results."""

from pathlib import Path

from tests.conftest import ROOT
from tests.integration.test_workflow import finished, upload, word


def test_identical_source_uses_parse_cache_but_runs_both_lists_again(client, monkeypatch):
    service = client.app.state.batch_service
    original = service.engine.run
    calls = []

    def tracked(document, list_name, items):
        calls.append((document.paper_id, list_name))
        return original(document, list_name, items)

    monkeypatch.setattr(service.engine, "run", tracked)
    data = word("(CUI)")
    first = finished(client, upload(client, [("first.docx", data)])["run_id"])
    second = finished(client, upload(client, [("renamed.docx", data)])["run_id"])
    assert first["run_id"] != second["run_id"]
    assert first["entries"][0]["result"]["paper_id"] == second["entries"][0]["result"]["paper_id"]
    assert [name for _, name in calls] == ["list1", "list2", "list1", "list2"]
    parsed = service.store.parsed(second["run_id"], second["entries"][0]["entry_id"])
    assert parsed.cache_state == "hit"
    assert second["entries"][0]["result"]["file_name"] == "renamed.docx"


def test_changed_content_with_same_filename_is_screened_from_new_bytes(
    client, orthogonal_semantics
):
    first = finished(client, upload(client, [("same.docx", word("List 1"))])["run_id"])
    second = finished(client, upload(client, [("same.docx", word("(CUI)"))])["run_id"])
    a, b = first["entries"][0]["result"], second["entries"][0]["result"]
    assert a["paper_id"] != b["paper_id"] and a["color"] == "green" and b["color"] == "red"
    assert any("L1-1" in f["items"] and "(CUI)" in f["quote"] for f in b["findings"])


def test_upload_does_not_read_keys_gold_or_archived_scorecards(client, project_root, monkeypatch):
    original_open = Path.open
    forbidden = [
        ROOT / "reports",
        project_root / "reports",
        ROOT / "data/keys",
        project_root / "data/keys",
        Path("/Users/mpatel/Downloads/SPR Fake Papers with Triggers/Keys"),
    ]
    attempted = []

    def guarded(path, *args, **kwargs):
        if any(path.is_relative_to(root) for root in forbidden) or path.name == "gold.jsonl":
            attempted.append(str(path))
            raise AssertionError("Runtime attempted to read evaluation data")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    batch = finished(client, upload(client, [("ordinary.docx", word("(CUI)"))])["run_id"])
    assert batch["entries"][0]["result"]["color"] == "red"
    assert not attempted
