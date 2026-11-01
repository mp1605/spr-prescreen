"""Browser API contracts with official text and minimal format fixtures, never sponsor papers."""

from __future__ import annotations

import hashlib
import io
import json
import time

import pymupdf
import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.batch_models import BatchEntry
from tests.conftest import ROOT


def word(text="List 1"):
    document = Document()
    document.add_paragraph(text)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def upload(client, files):
    response = client.post("/api/batches", files=[("files", file) for file in files])
    assert response.status_code == 202, response.text
    return response.json()


def finished(client, run_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        data = client.get(f"/api/batches/{run_id}").json()
        if all(
            entry["phase"] in {"done", "rejected", "failed", "cancelled"}
            for entry in data["entries"]
        ):
            return data
        time.sleep(0.02)
    pytest.fail("Browser batch did not finish within 30 seconds")


def base_for(batch, index=0):
    return f"/api/batches/{batch['run_id']}/papers/{batch['entries'][index]['entry_id']}"


@pytest.fixture
def reviewed_paper(client):
    batch = upload(client, [("official.docx", word("(CUI). Unmanned aerial vehicles."))])
    return finished(client, batch["run_id"])


def test_eighty_mixed_files_are_isolated_and_have_exact_evidence(
    client, project_root, orthogonal_semantics
):
    files = [(f"heading-{i}.docx", word()) for i in range(77)]
    files += [
        ("official.pdf", (ROOT / "docs/official-lists.pdf").read_bytes()),
        ("corrupt.pdf", b"not a PDF"),
        ("unsupported.txt", b"List 1"),
    ]
    batch = finished(client, upload(client, files)["run_id"])
    assert len(batch["entries"]) == 80
    assert sum(entry["phase"] == "done" for entry in batch["entries"]) == 79
    green = batch["entries"][0]["result"]
    assert green["color"] == "green" and green["label"] == "No flags found"
    damaged = batch["entries"][78]["result"]
    assert damaged["color"] == "yellow" and damaged["label"] == "Incomplete"
    assert batch["entries"][79]["phase"] == "rejected"
    source = client.get(base_for(batch, 77) + "/document").json()
    result = batch["entries"][77]["result"]
    assert result["trace"] == ["list1:done", "list2:done"]
    for flag in result["findings"]:
        location = flag["location"]
        unit = next(unit for unit in source["units"] if unit["page"] == location["page"])
        assert unit["text"][location["char_start"] : location["char_end"]] == flag["quote"]
        assert location["bbox"]
    png = client.get(base_for(batch, 77) + "/pages/1.png")
    assert png.status_code == 200 and png.content.startswith(b"\x89PNG")
    assert client.get(base_for(batch, 77) + "/pages/0.png").status_code == 422
    assert client.get(base_for(batch) + "/pages/1.png").status_code == 404
    original = client.get(base_for(batch, 77) + "/original")
    assert original.content == (ROOT / "docs/official-lists.pdf").read_bytes()
    assert original.headers["content-disposition"].startswith("attachment;")
    assert (project_root / "data/keys").exists() is False


def test_decisions_undo_revision_and_reload_preserve_raw_results(
    client, reviewed_paper, project_root
):
    batch = reviewed_paper
    base = base_for(batch)
    result = batch["entries"][0]["result"]
    assert len(result["findings"]) >= 2
    finding = result["findings"][0]["finding_id"]
    snapshot = project_root / "runs" / batch["run_id"] / "results.json"
    before = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    command = {"revision": 0, "action": "accept", "finding_id": finding, "reviewer": "Reviewer"}
    accepted = client.post(base + "/decisions", json=command).json()
    assert accepted["revision"] == 1
    assert client.post(base + "/decisions", json=command).status_code == 409
    command |= {"revision": 1, "action": "override", "reason": "Context does not support this item"}
    overridden = client.post(base + "/decisions", json=command).json()
    assert overridden["decisions"][finding]["action"] == "override"
    undo = {
        "revision": 2,
        "action": "undo",
        "finding_id": finding,
        "reviewer": "Reviewer",
        "target_event": overridden["decisions"][finding]["event_id"],
    }
    restored = client.post(base + "/decisions", json=undo).json()
    assert restored["decisions"][finding]["action"] == "accept"
    assert len(restored["events"]) == 3
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == before
    assert client.get(base).json()["result"] == result
    # New factory/store instance, not merely a frontend cache reload.
    with TestClient(create_app(project_root), base_url="http://127.0.0.1") as second:
        assert second.get(base + "/decisions").json() == restored
    assert snapshot.stat().st_mode & 0o777 == 0o600
    audit = snapshot.with_name("decisions.jsonl")
    assert audit.stat().st_mode & 0o777 == 0o600
    assert [json.loads(line)["action"] for line in audit.read_text().splitlines()] == [
        "accept",
        "override",
        "undo",
    ]


def test_wrong_finding_and_undo_owner_rejected(client, reviewed_paper):
    base = base_for(reviewed_paper)
    command = {"revision": 0, "action": "accept", "finding_id": "unknown", "reviewer": "One"}
    assert client.post(base + "/decisions", json=command).status_code == 422
    finding = reviewed_paper["entries"][0]["result"]["findings"][0]["finding_id"]
    command["finding_id"] = finding
    state = client.post(base + "/decisions", json=command).json()
    undo = {
        "revision": 1,
        "action": "undo",
        "finding_id": finding,
        "reviewer": "Two",
        "target_event": state["events"][0]["event_id"],
    }
    assert client.post(base + "/decisions", json=undo).status_code == 409
    assert client.get(base + "/decisions").json()["revision"] == 1
    assert (
        client.post(
            base + "/decisions", json=command | {"reviewer": " ", "revision": 1}
        ).status_code
        == 422
    )


def test_flagless_source_inspection_is_explicit_and_undoable(client, orthogonal_semantics):
    batch = finished(client, upload(client, [("heading.docx", word())])["run_id"])
    base = base_for(batch)
    assert (
        client.get("/api/batches").json()[0]["reviews"][batch["entries"][0]["entry_id"]]["complete"]
        is False
    )
    state = client.post(
        base + "/decisions", json={"action": "inspect", "reviewer": "One", "revision": 0}
    ).json()
    assert state["inspected"]
    assert (
        client.get("/api/batches").json()[0]["reviews"][batch["entries"][0]["entry_id"]]["complete"]
        is True
    )
    state = client.post(
        base + "/decisions",
        json={
            "action": "undo",
            "reviewer": "One",
            "revision": 1,
            "target_event": state["events"][0]["event_id"],
        },
    ).json()
    assert not state["inspected"]


def test_sse_terminal_snapshot_and_reconnection(client, reviewed_paper):
    path = f"/api/batches/{reviewed_paper['run_id']}/events"
    response = client.get(path)
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in response.text and '"terminal": true' in response.text
    assert response.headers["cache-control"] == "no-store"
    revision = client.get(f"/api/batches/{reviewed_paper['run_id']}").json()["revision"]
    assert '"terminal": true' in client.get(path, headers={"last-event-id": str(revision)}).text


def test_upload_limits_keys_and_paths_visible_without_scanning(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Excluded input was submitted to scanner")

    monkeypatch.setattr(client.app.state.batch_service, "submit", forbidden)
    batch = upload(
        client,
        [
            ("nested/official_KEY.docx", b""),
            ("INDEX.csv", b""),
            ("keys/official.docx", b""),
            ("oversize.pdf", b"0" * (25 * 1024**2 + 1)),
        ],
    )
    assert all(entry["phase"] == "rejected" for entry in batch["entries"])
    assert all("/" not in entry["file_name"] for entry in batch["entries"])
    too_many = client.post(
        "/api/batches", files=[("files", (f"{i}.docx", b"")) for i in range(101)]
    )
    assert too_many.status_code == 400
    assert len(client.get("/api/batches").json()) == 1
    assert client.post("/api/batches", data={}).status_code == 422


def test_cross_site_writes_and_private_files_rejected(client, reviewed_paper):
    base = base_for(reviewed_paper)
    assert (
        client.post(
            base + "/decisions", json={}, headers={"origin": "https://example.com"}
        ).status_code
        == 403
    )
    assert client.get("/api/batches/web-" + "0" * 32).status_code == 404
    assert client.get(base + "/../../config/admin.json").status_code == 404
    assert client.get("/runs/anything/source.bin").status_code == 404


def test_cancel_and_retry_use_attempt_tokens(client, monkeypatch):
    service = client.app.state.batch_service
    submit = service.submit
    monkeypatch.setattr(service, "submit", lambda *args: None)
    batch = upload(client, [("heading.docx", word())])
    entry = BatchEntry.model_validate(batch["entries"][0])
    run_id = batch["run_id"]
    assert client.post(f"/api/batches/{run_id}/cancel").status_code == 204
    assert client.get(base_for(batch)).json()["phase"] == "cancelled"
    from backend.core.batch import Cancelled

    with pytest.raises(Cancelled):
        service._current(run_id, entry)
    monkeypatch.setattr(service, "submit", submit)
    assert client.post(base_for(batch) + "/retry").status_code == 202
    result = finished(client, run_id)
    assert result["entries"][0]["attempt"] == 2 and result["entries"][0]["phase"] == "done"
    with pytest.raises(Cancelled):
        service._current(run_id, entry)
    assert client.post(base_for(batch) + "/retry").status_code == 422


def test_restart_marks_interrupted_files_and_keeps_original(client, monkeypatch, project_root):
    service = client.app.state.batch_service
    monkeypatch.setattr(service, "submit", lambda *args: None)
    batch = upload(client, [("heading.docx", word())])
    service.store.recover()
    entry = client.get(base_for(batch)).json()
    assert entry["phase"] == "failed" and "restart" in entry["message"]
    assert service.store.source(batch["run_id"], entry["entry_id"]).is_file()
    assert (
        client.post(
            base_for(batch) + "/decisions",
            json={"action": "inspect", "revision": 0, "reviewer": "One"},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_pdf_keeps_original_orientation_and_unrotated_evidence_coordinates(client, rotation):
    with pymupdf.open() as doc:
        page = doc.new_page(width=400, height=250)
        page.insert_text((20, 40), "(CUI).")
        page.set_rotation(rotation)
        data = doc.tobytes()
    batch = finished(client, upload(client, [("rotation.pdf", data)])["run_id"])
    source = client.get(base_for(batch) + "/document").json()
    unit = source["units"][0]
    assert (unit["width"], unit["height"]) == (400, 250)
    image = client.get(base_for(batch) + "/pages/1.png").content
    pixmap = pymupdf.Pixmap(image)
    assert source["page_rotations"] == {"1": rotation}
    assert pixmap.width / pixmap.height == (250 / 400 if rotation in (90, 270) else 400 / 250)
    assert batch["entries"][0]["result"]["findings"][0]["location"]["bbox"][0][1] < 40
