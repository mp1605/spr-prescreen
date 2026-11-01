"""Exercise the actual worker boundary, progress transitions, and review isolation."""

import threading

from backend.core.batch_models import BatchEntry
from tests.integration.test_workflow import base_for, finished, upload, word


def test_real_stages_and_duplicate_upload_decisions_are_separate(client, monkeypatch):
    service = client.app.state.batch_service
    phases = {}
    update = service.store.update

    def record(run_id, entry: BatchEntry):
        phases.setdefault(entry.entry_id, []).append(entry.phase)
        update(run_id, entry)

    monkeypatch.setattr(service.store, "update", record)
    data = word("(CUI).")
    batch = finished(client, upload(client, [("same.docx", data), ("same.docx", data)])["run_id"])
    first, second = batch["entries"]
    assert first["entry_id"] != second["entry_id"]
    assert first["result"]["paper_id"] == second["result"]["paper_id"]
    for entry in batch["entries"]:
        assert phases[entry["entry_id"]] == ["parsing", "list1", "list2", "ai", "done"]
    finding = first["result"]["findings"][0]["finding_id"]
    response = client.post(
        base_for(batch) + "/decisions",
        json={
            "revision": 0,
            "reviewer": "One",
            "action": "override",
            "finding_id": finding,
        },
    )
    assert response.status_code == 200
    assert client.get(base_for(batch, 1) + "/decisions").json()["decisions"] == {}


def test_cancel_during_running_engine_discards_old_attempt_even_after_retry(client, monkeypatch):
    service = client.app.state.batch_service
    entered, release = threading.Event(), threading.Event()
    original = service.engine.run

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10), "Test must release its paused engine"
        return original(*args, **kwargs)

    monkeypatch.setattr(service.engine, "run", blocked)
    try:
        batch = upload(client, [("heading.docx", word())])
        assert entered.wait(5)
        assert client.post(f"/api/batches/{batch['run_id']}/cancel").status_code == 204
        cancelled = client.get(base_for(batch)).json()
        assert cancelled["phase"] == "cancelled" and cancelled["result"] is None
        monkeypatch.setattr(service.engine, "run", original)
        assert client.post(base_for(batch) + "/retry").status_code == 202
        done = finished(client, batch["run_id"])
        assert done["entries"][0]["attempt"] == 2
        assert done["entries"][0]["phase"] == "done"
    finally:
        release.set()


def test_incomplete_source_needs_explicit_inspection_after_flag_decisions(client):
    batch = finished(client, upload(client, [("corrupt.pdf", b"not a PDF")])["run_id"])
    base = base_for(batch)
    entry_id = batch["entries"][0]["entry_id"]
    assert batch["entries"][0]["result"]["color"] == "yellow"
    assert not client.get("/api/batches").json()[0]["reviews"][entry_id]["complete"]
    assert (
        client.post(
            base + "/decisions",
            json={
                "revision": 0,
                "reviewer": "One",
                "action": "inspect",
            },
        ).status_code
        == 200
    )
    assert client.get("/api/batches").json()[0]["reviews"][entry_id]["complete"]
    assert client.get(base).json()["result"]["label"] == "Incomplete"
