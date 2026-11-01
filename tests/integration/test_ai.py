"""Optional AI integration: protocol stubs and official phrases, never sponsor papers."""

import hashlib
import io
import time

import pymupdf
import pytest
from docx import Document

from backend.core.settings import load_settings
from tests.ai.conftest import DIGEST, MODEL, ContractProvider, proposal
from tests.integration.test_admin import login
from tests.integration.test_workflow import base_for, finished, upload, word


def configure(client, provider, **settings):
    client.app.state.ai_engine.provider = provider
    status = client.get("/api/ai").json()
    command = {
        "revision": status["revision"],
        "enabled": True,
        "model": MODEL,
        "timeout_seconds": 5,
        "context_tokens": 32768,
        "max_output_tokens": 2048,
        **settings,
    }
    return client.put("/api/admin/ai", json=command)


def test_ai_settings_are_admin_only_versioned_and_local(client, project_root):
    provider = ContractProvider()
    assert configure(client, provider).status_code == 403
    login(client, project_root)
    response = configure(client, provider)
    assert response.status_code == 200, response.text
    status = response.json()
    assert status["settings"]["model_digest"] == DIGEST and load_settings(project_root).ai.enabled
    assert client.get("/api/system").json()["ai_enabled"]
    stale = client.put(
        "/api/admin/ai",
        json={
            "revision": "stale",
            "enabled": False,
            "model": MODEL,
            "timeout_seconds": 5,
            "context_tokens": 32768,
            "max_output_tokens": 2048,
        },
    )
    assert stale.status_code == 409
    disabled = configure(client, provider, enabled=False)
    assert disabled.status_code == 200 and not load_settings(project_root).ai.enabled
    text = (project_root / "config/ai-audit.jsonl").read_text()
    assert "configure_optional_ai" in text and "Animal testing" not in text


def test_missing_model_refuses_enable_but_off_is_always_available(client, project_root):
    login(client, project_root)
    response = configure(client, ContractProvider(error=True))
    assert response.status_code == 422 and not load_settings(project_root).ai.enabled
    assert configure(client, ContractProvider(error=True), enabled=False).status_code == 200
    status = client.get("/api/ai").json()
    assert not status["available"] and status["models"] == []


@pytest.mark.parametrize("format", ["docx", "pdf"])
def test_real_upload_ai_evidence_exports_and_annotation_roundtrip(
    format, client, project_root, orthogonal_semantics
):
    login(client, project_root)
    provider = ContractProvider([proposal()])
    assert configure(client, provider).status_code == 200
    if format == "docx":
        data = word("Animal testing")
    else:
        with pymupdf.open() as document:
            document.new_page().insert_text((50, 80), "Animal testing")
            data = document.tobytes()
    batch = finished(client, upload(client, [(f"format.{format}", data)])["run_id"])
    base = base_for(batch)
    paper = batch["entries"][0]["result"]
    assert paper["ai_state"] == "ran" and paper["ai"]["accepted"] == 1 and len(provider.calls) == 1
    assert paper["findings"][0]["ai_matches"][0]["quote"] == "Animal testing"
    assert "ai" in paper["findings"][0]["engines"]
    original = project_root / "runs" / batch["run_id"] / "results.json"
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    assert (
        client.post(
            base + "/decisions",
            json={
                "revision": 0,
                "reviewer": "AI format QA",
                "action": "override",
                "finding_id": paper["findings"][0]["finding_id"],
            },
        ).status_code
        == 200
    )
    report = client.get(f"/api/batches/{batch['run_id']}/export/json?layout=audit").json()
    assert report["batch"]["ai_settings"]["model_digest"] == DIGEST
    assert report["batch"]["entries"][0]["result"]["ai"]["pipeline_digest"]
    copy = client.get(base + "/annotated?notes=true")
    assert copy.status_code == 200
    if format == "docx":
        doc = Document(io.BytesIO(copy.content))
        assert any("AI verified source quote" in c.text for c in doc.comments)
    else:
        with pymupdf.open(stream=copy.content, filetype="pdf") as document:
            page = document[0]
            assert any("AI verified source quote" in a.info["content"] for a in page.annots())
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    assert (
        b"ai_evidence_json"
        in client.get(f"/api/batches/{batch['run_id']}/export/csv?layout=audit").content
    )


def test_timeout_has_real_ai_stage_keeps_baseline_and_is_not_green(
    client, project_root, orthogonal_semantics
):
    login(client, project_root)
    provider = ContractProvider(delay=5)
    assert configure(client, provider, timeout_seconds=1).status_code == 200
    job = upload(client, [("format.docx", word("List 1"))])
    deadline = time.monotonic() + 5
    saw_ai = False
    while time.monotonic() < deadline:
        batch = client.get("/api/batches/" + job["run_id"]).json()
        phase = batch["entries"][0]["phase"]
        saw_ai = saw_ai or phase == "ai"
        if phase == "done":
            break
        time.sleep(0.02)
    paper = batch["entries"][0]["result"]
    assert saw_ai and paper["ai_state"] == "timeout" and paper["color"] == "yellow"
    assert paper["incomplete_reasons"] and paper["flag_count"]["total"] == 0


def test_batch_captures_ai_setting_and_rescan_uses_new_setting(
    client, project_root, orthogonal_semantics
):
    login(client, project_root)
    provider = ContractProvider([proposal()])
    assert configure(client, provider).status_code == 200
    first = finished(client, upload(client, [("format.docx", word("Animal testing"))])["run_id"])
    assert first["entries"][0]["result"]["ai_state"] == "ran"
    assert configure(client, provider, enabled=False).status_code == 200
    second = finished(
        client, client.post(f"/api/batches/{first['run_id']}/rescan").json()["run_id"]
    )
    assert second["entries"][0]["result"]["ai_state"] == "off"
    assert client.get(base_for(first)).json()["result"]["ai_state"] == "ran"
    assert len(provider.calls) == 1
