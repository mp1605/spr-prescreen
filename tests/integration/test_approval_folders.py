"""Human approval and local filing contracts, using mechanical format fixtures only."""

import json
import shutil
from pathlib import Path

import pymupdf
import pytest

from backend.core.review_store import ReviewStore
from tests.integration.test_workflow import base_for, finished, upload, word


def approve(client, batch, revision=0, **extra):
    return client.post(
        base_for(batch) + "/decisions",
        json={
            "action": "approve",
            "reviewer": "Reviewer",
            "revision": revision,
            **extra,
        },
    )


@pytest.mark.parametrize("extension", ["docx", "pdf"])
def test_green_approval_files_original_and_undo_restores_pending(
    client, project_root, orthogonal_semantics, extension
):
    data = word()
    if extension == "pdf":
        with pymupdf.open() as doc:
            doc.new_page().insert_text((30, 40), "List 1")
            data = doc.tobytes()
    batch = finished(client, upload(client, [(f"heading.{extension}", data)])["run_id"])
    entry = batch["entries"][0]
    assert entry["result"]["color"] == "green"
    root = Path(client.get(f"/api/batches/{batch['run_id']}/folders").json()["path"])
    pending = root / "Pending Review" / f"001_heading.{extension}"
    approved = root / "Approved" / pending.name
    # Complete is published under the same lock as folder organization.
    client.get(base_for(batch) + "/decisions")
    assert pending.read_bytes() == data and not approved.exists()
    result_path = project_root / "runs" / batch["run_id"] / "results.json"
    snapshot = result_path.read_bytes()
    response = approve(client, batch)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["approved"] and state["inspected"] and not state["storage_error"]
    assert approved.read_bytes() == data and not pending.exists()
    assert state["storage_file"] == str(approved)
    assert client.get(base_for(batch) + "/original").content == data
    assert result_path.read_bytes() == snapshot
    progress = client.get("/api/batches").json()[0]["reviews"][entry["entry_id"]]
    assert progress["approved"] and progress["complete"]
    service = client.app.state.batch_service
    assert (
        ReviewStore(service.store, client.app.state.batch_folders)
        .state(batch["run_id"], entry["entry_id"])
        .approved
    )
    manifest = json.loads((root / "manifest.json").read_bytes())["documents"][entry["entry_id"]]
    assert manifest["reviewer_approved"] and manifest["approval"]["reviewer"] == "Reviewer"
    assert approve(client, batch).status_code == 409
    assert approve(client, batch, revision=1).status_code == 409
    undo = {
        "action": "undo",
        "reviewer": "Other",
        "revision": 1,
        "target_event": state["approval_event"]["event_id"],
    }
    assert client.post(base_for(batch) + "/decisions", json=undo).status_code == 409
    undo["reviewer"] = "Reviewer"
    undone = client.post(base_for(batch) + "/decisions", json=undo).json()
    assert not undone["approved"] and not undone["inspected"]
    assert pending.read_bytes() == data and not approved.exists()
    assert [event["action"] for event in undone["events"]] == ["approve", "undo"]


def test_red_yellow_share_flagged_and_cannot_be_approved(client, orthogonal_semantics):
    batch = finished(
        client,
        upload(client, [("red.docx", word("(CUI).")), ("yellow.pdf", b"invalid pdf")])["run_id"],
    )
    assert {entry["result"]["color"] for entry in batch["entries"]} == {"red", "yellow"}
    for index, entry in enumerate(batch["entries"]):
        base = base_for(batch, index)
        state = client.get(base + "/decisions").json()
        assert Path(state["storage_file"]).parent.name == "Flagged"
        response = client.post(
            base + "/decisions", json={"action": "approve", "revision": 0, "reviewer": "Reviewer"}
        )
        assert response.status_code == 409
        for revision, flag in enumerate(entry["result"]["findings"]):
            response = client.post(
                base + "/decisions",
                json={
                    "action": "override",
                    "revision": revision,
                    "reviewer": "Reviewer",
                    "finding_id": flag["finding_id"],
                    "reason": "Manual review",
                },
            )
            assert response.status_code == 200
        state = client.get(base + "/decisions").json()
        assert not state["approved"] and Path(state["storage_file"]).parent.name == "Flagged"
    status = client.get(f"/api/batches/{batch['run_id']}/folders").json()
    assert status["counts"]["Flagged"] == 2 and status["counts"]["Approved"] == 0


def test_duplicate_names_batch_isolation_and_old_batch_repair(
    client, project_root, orthogonal_semantics
):
    data = word()
    batch = finished(client, upload(client, [("same.docx", data), ("same.docx", data)])["run_id"])
    root = Path(client.get(f"/api/batches/{batch['run_id']}/folders").json()["path"])
    client.get(base_for(batch) + "/decisions")
    assert {p.name for p in (root / "Pending Review").iterdir()} == {
        "001_same.docx",
        "002_same.docx",
    }
    assert approve(client, batch).status_code == 200
    shutil.rmtree(root)
    response = client.post(f"/api/batches/{batch['run_id']}/folders")
    assert response.status_code == 200 and not response.json()["errors"]
    assert (root / "Approved/001_same.docx").read_bytes() == data
    assert (root / "Pending Review/002_same.docx").read_bytes() == data
    other = finished(client, upload(client, [("same.docx", data)])["run_id"])
    assert not client.get(base_for(other) + "/decisions").json()["approved"]
    assert root != Path(client.get(f"/api/batches/{other['run_id']}/folders").json()["path"])


@pytest.mark.parametrize("damage", ["source", "copy", "missing", "symlink"])
def test_damaged_or_redirected_storage_refuses_approval_without_audit(
    client, project_root, orthogonal_semantics, damage, tmp_path
):
    batch = finished(client, upload(client, [("heading.docx", word())])["run_id"])
    state = client.get(base_for(batch) + "/decisions").json()
    store = client.app.state.batch_service.store
    source = store.source(batch["run_id"], batch["entries"][0]["entry_id"])
    copy = Path(state["storage_file"])
    if damage == "source":
        source.write_bytes(b"changed")
    elif damage == "copy":
        copy.write_bytes(b"keep this edit")
    elif damage == "missing":
        source.unlink()
    else:
        destination = copy.parent.parent / "Approved"
        destination.rmdir()
        destination.symlink_to(tmp_path, target_is_directory=True)
    assert approve(client, batch).status_code == 422
    state = client.get(base_for(batch) + "/decisions").json()
    assert not state["approved"] and state["revision"] == 0
    if damage == "copy":
        assert copy.read_bytes() == b"keep this edit"


def test_projection_failure_reports_saved_approval_and_can_be_repaired(
    client, orthogonal_semantics, monkeypatch
):
    batch = finished(client, upload(client, [("heading.docx", word())])["run_id"])
    folders = client.app.state.batch_folders
    synchronize = folders.synchronize

    def fail_after_event(record, entry, state):
        if state.approved:
            raise OSError("disk full")
        return synchronize(record, entry, state)

    monkeypatch.setattr(folders, "synchronize", fail_after_event)
    response = approve(client, batch)
    assert response.status_code == 200
    state = response.json()
    assert state["approved"] and state["storage_error"] and not state["storage_file"]
    monkeypatch.setattr(folders, "synchronize", synchronize)
    fixed = client.post(f"/api/batches/{batch['run_id']}/folders").json()
    assert not fixed["errors"] and fixed["counts"]["Approved"] == 1
    assert client.get(base_for(batch) + "/decisions").json()["revision"] == 1
