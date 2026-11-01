"""Real PDF/DOCX artifacts follow current review decisions without changing source results."""

import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pymupdf
import pytest
from docx import Document
from lxml import etree

import backend.core.batch_folders as folder_module
from backend.core.review_store import ReviewStore
from tests.integration.test_workflow import base_for, finished, upload, word


def highlight_colors(data, extension):
    if extension == "docx":
        with ZipFile(io.BytesIO(data)) as archive:
            tree = etree.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        return tree.xpath("//w:highlight/@w:val", namespaces=ns)
    with pymupdf.open(stream=data, filetype="pdf") as document:
        return [
            "red" if tuple(annotation.colors["stroke"]) == (1, 0, 0) else "yellow"
            for page in document
            for annotation in page.annots()
            if annotation.type[0] == 8
        ]


@pytest.fixture(params=["docx", "pdf"])
def flagged_copy(request, client, orthogonal_semantics):
    extension = request.param
    data = word("(CUI). Animal testing.")
    if extension == "pdf":
        with pymupdf.open() as document:
            document.new_page().insert_text((40, 70), "(CUI). Animal testing.")
            data = document.tobytes()
    batch = finished(client, upload(client, [(f"official-atoms.{extension}", data)])["run_id"])
    base = base_for(batch)
    state = client.get(base + "/decisions").json()
    return batch, base, extension, data, Path(state["storage_file"])


def decide(client, base, action, **extra):
    state = client.get(base + "/decisions").json()
    response = client.post(
        base + "/decisions",
        json={"action": action, "revision": state["revision"], "reviewer": "Copy QA", **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_managed_copy_and_download_apply_accept_override_and_undo(client, flagged_copy):
    batch, base, extension, original, copy = flagged_copy
    paper = batch["entries"][0]["result"]
    red = next(flag for flag in paper["findings"] if flag["color"] == "red")
    yellow = next(flag for flag in paper["findings"] if flag["color"] == "yellow")
    assert sorted(highlight_colors(copy.read_bytes(), extension)) == ["red", "yellow"]
    assert copy.read_bytes() != original
    decide(client, base, "accept", finding_id=red["finding_id"])
    overridden = decide(
        client, base, "override", finding_id=red["finding_id"], reason="Source context checked"
    )
    assert not overridden["storage_error"]
    assert highlight_colors(copy.read_bytes(), extension) == ["yellow"]
    downloaded = client.get(base + "/annotated?notes=true")
    assert downloaded.status_code == 200
    assert highlight_colors(downloaded.content, extension) == ["yellow"]
    details = client.get(base + "/annotation-manifest?notes=true").json()
    assert details["findings_annotated"] == 1 and details["overridden_findings"] == 1
    if extension == "docx":
        assert len(Document(io.BytesIO(copy.read_bytes())).comments) == 0
        with ZipFile(io.BytesIO(copy.read_bytes())) as archive:
            tree = etree.fromstring(archive.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        assert set(tree.xpath("//w:rPr/w:shd/@w:fill", namespaces=ns)) == {"FFFF00"}
        assert any(
            "Reviewer decision: override" in comment.text
            for comment in Document(io.BytesIO(downloaded.content)).comments
        )
    else:
        with pymupdf.open(stream=copy.read_bytes(), filetype="pdf") as doc:
            assert all(annotation.type[0] == 8 for annotation in doc[0].annots())
        with pymupdf.open(stream=downloaded.content, filetype="pdf") as doc:
            assert any(
                "Reviewer decision: override" in annotation.info.get("content", "")
                for annotation in doc[0].annots()
            )
    decide(
        client,
        base,
        "undo",
        finding_id=red["finding_id"],
        target_event=overridden["decisions"][red["finding_id"]]["event_id"],
    )
    assert sorted(highlight_colors(copy.read_bytes(), extension)) == ["red", "yellow"]
    decide(client, base, "override", finding_id=red["finding_id"], reason="Checked")
    state = decide(client, base, "override", finding_id=yellow["finding_id"], reason="Checked")
    assert highlight_colors(copy.read_bytes(), extension) == []
    assert client.get(base).json()["result"] == paper
    assert client.get(base + "/original").content == original
    record = json.loads((copy.parent.parent / "manifest.json").read_bytes())["documents"][
        batch["entries"][0]["entry_id"]
    ]
    assert record["source_sha256"] == hashlib.sha256(original).hexdigest()
    assert record["document_sha256"] == hashlib.sha256(copy.read_bytes()).hexdigest()
    assert record["review_revision"] == state["revision"] and record["active_highlights"] == 0
    assert record["notes_included"] is False
    assert all(decision["action"] == "override" for decision in record["review_decisions"].values())
    before = copy.read_bytes()
    assert client.post(f"/api/batches/{batch['run_id']}/folders").status_code == 200
    assert copy.read_bytes() == before


def test_old_original_copy_is_upgraded_using_saved_decisions(client, flagged_copy):
    batch, base, extension, original, copy = flagged_copy
    store = client.app.state.batch_service.store
    entry = batch["entries"][0]
    red = next(flag for flag in entry["result"]["findings"] if flag["color"] == "red")
    from backend.core.batch_models import ReviewCommand

    ReviewStore(store).apply(
        batch["run_id"],
        entry["entry_id"],
        ReviewCommand(
            action="override", revision=0, reviewer="Copy QA", finding_id=red["finding_id"]
        ),
    )
    manifest = copy.parent.parent / "manifest.json"
    index = json.loads(manifest.read_bytes())
    record = index["documents"][entry["entry_id"]]
    for key in ("document_sha256", "renderer_digest"):
        record.pop(key, None)
    record["copy_type"] = "original_format_original_bytes"
    manifest.write_text(json.dumps(index))
    copy.write_bytes(original)
    folders = client.app.state.batch_folders
    assert folders.refresh_existing(ReviewStore(store, folders).states) == 1
    assert highlight_colors(copy.read_bytes(), extension) == ["yellow"]
    assert client.get(base + "/original").content == original


def test_interrupted_copy_write_is_repairable_without_losing_saved_decision(
    client, flagged_copy, monkeypatch
):
    batch, base, extension, _, copy = flagged_copy
    red = next(flag for flag in batch["entries"][0]["result"]["findings"] if flag["color"] == "red")
    real_write = folder_module.write_binary

    def interrupted(path, data):
        real_write(path, data)
        raise OSError("interrupted after atomic replace")

    monkeypatch.setattr(folder_module, "write_binary", interrupted)
    state = decide(client, base, "override", finding_id=red["finding_id"], reason="Checked")
    assert state["revision"] == 1 and state["storage_error"]
    monkeypatch.setattr(folder_module, "write_binary", real_write)
    repaired = client.post(f"/api/batches/{batch['run_id']}/folders").json()
    assert not repaired["errors"]
    assert highlight_colors(copy.read_bytes(), extension) == ["yellow"]
    assert client.get(base + "/decisions").json()["revision"] == 1


def test_render_failure_preserves_previous_copy_and_can_be_repaired(client, flagged_copy):
    batch, base, extension, _, copy = flagged_copy
    entry = batch["entries"][0]
    red = next(flag for flag in entry["result"]["findings"] if flag["color"] == "red")
    store = client.app.state.batch_service.store
    parsed_path = store.path(batch["run_id"], entry["entry_id"]) / "parsed.json"
    parsed = parsed_path.read_bytes()
    before = copy.read_bytes()
    parsed_path.unlink()
    state = decide(client, base, "override", finding_id=red["finding_id"], reason="Checked")
    assert state["storage_error"] and copy.read_bytes() == before
    record = json.loads((copy.parent.parent / "manifest.json").read_bytes())["documents"][
        entry["entry_id"]
    ]
    assert record["copy_type"] == "review_copy_stale" and record["review_revision"] == 0
    assert record["active_highlights"] == 2 and record["overridden_findings"] == 0
    parsed_path.write_bytes(parsed)
    assert not client.post(f"/api/batches/{batch['run_id']}/folders").json()["errors"]
    assert highlight_colors(copy.read_bytes(), extension) == ["yellow"]


def test_user_modified_highlighted_copy_is_preserved(client, flagged_copy):
    batch, base, _, _, copy = flagged_copy
    red = next(flag for flag in batch["entries"][0]["result"]["findings"] if flag["color"] == "red")
    edited = copy.read_bytes() + b"\nmanual file change"
    copy.write_bytes(edited)
    state = decide(client, base, "override", finding_id=red["finding_id"], reason="Checked")
    assert state["storage_error"] and state["revision"] == 1
    assert copy.read_bytes() == edited
