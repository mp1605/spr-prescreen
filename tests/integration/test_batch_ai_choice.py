"""A batch can opt in/out without altering admin defaults or silently losing its choice."""

import pytest

from backend.core.settings import load_settings
from tests.ai.conftest import DIGEST, ContractProvider, proposal
from tests.integration.test_admin import login
from tests.integration.test_ai import configure
from tests.integration.test_workflow import base_for, finished, upload, word


def start(client, mode):
    return client.post(
        f"/api/batches?ai_mode={mode}", files=[("files", ("format.docx", word("Animal testing")))]
    )


def test_batch_opt_in_pins_model_without_changing_admin_default(client, project_root):
    provider = ContractProvider([proposal()])
    login(client, project_root)
    assert configure(client, provider, enabled=False).status_code == 200
    client.cookies.clear()
    before = (project_root / "config/settings.yaml").read_bytes()
    response = start(client, "on")
    assert response.status_code == 202, response.text
    batch = finished(client, response.json()["run_id"])
    assert batch["ai_settings"]["enabled"] and batch["ai_settings"]["model_digest"] == DIGEST
    assert batch["entries"][0]["result"]["ai_state"] == "ran"
    assert len(provider.calls) == 1
    assert (project_root / "config/settings.yaml").read_bytes() == before
    assert not client.get("/api/system").json()["ai_enabled"]


def test_batch_opt_out_overrides_enabled_default_without_model_calls(client, project_root):
    provider = ContractProvider([proposal()])
    login(client, project_root)
    assert configure(client, provider).status_code == 200
    client.cookies.clear()
    response = start(client, "off")
    assert response.status_code == 202
    batch = finished(client, response.json()["run_id"])
    assert not batch["ai_settings"]["enabled"]
    assert batch["entries"][0]["result"]["ai_state"] == "off" and not provider.calls
    assert load_settings(project_root).ai.enabled


@pytest.mark.parametrize("mode", ["on", "selective", "full"])
def test_opt_in_fails_before_creating_a_batch_when_model_is_unavailable(client, mode):
    client.app.state.ai_engine.provider = ContractProvider(error=True)
    before = client.get("/api/batches").json()
    response = start(client, mode)
    assert response.status_code == 422 and "not started" in response.json()["detail"]
    assert client.get("/api/batches").json() == before
    assert start(client, "off").status_code == 202


def test_changed_pinned_model_and_insufficient_context_are_not_silently_accepted(
    client, project_root
):
    provider = ContractProvider()
    login(client, project_root)
    assert configure(client, provider).status_code == 200
    provider.digest = "b" * 64
    assert start(client, "on").status_code == 422
    provider.digest = DIGEST
    provider.limit = 2048
    assert start(client, "on").status_code == 422
    assert client.get("/api/batches").json() == []


def test_cancel_and_retry_keep_explicit_batch_ai_choice(client, project_root, monkeypatch):
    provider = ContractProvider([proposal()])
    login(client, project_root)
    assert configure(client, provider).status_code == 200
    service = client.app.state.batch_service
    submit = service.submit
    monkeypatch.setattr(service, "submit", lambda *args: None)
    response = start(client, "on")
    assert response.status_code == 202
    batch = response.json()
    assert client.post(f"/api/batches/{batch['run_id']}/cancel").status_code == 204
    assert configure(client, provider, enabled=False).status_code == 200
    monkeypatch.setattr(service, "submit", submit)
    assert client.post(base_for(batch) + "/retry").status_code == 202
    retried = finished(client, batch["run_id"])
    assert retried["entries"][0]["attempt"] == 2
    assert retried["ai_settings"]["enabled"]
    assert retried["entries"][0]["result"]["ai_state"] == "ran"
    assert len(provider.calls) == 1 and not load_settings(project_root).ai.enabled


def test_unknown_batch_mode_is_rejected_and_legacy_uploads_keep_the_default(client):
    assert start(client, "unexpected").status_code == 422
    legacy = finished(client, upload(client, [("format.docx", word("Animal testing"))])["run_id"])
    assert legacy["entries"][0]["result"]["ai_state"] == "off"


@pytest.mark.parametrize("mode", ["selective", "full"])
def test_new_mode_is_recorded_and_used_in_actual_batch_generation(client, project_root, mode):
    provider = ContractProvider([proposal()])
    login(client, project_root)
    assert configure(client, provider, enabled=False).status_code == 200
    batch = finished(client, start(client, mode).json()["run_id"])
    assert batch["ai_settings"]["scope"] == mode
    result = batch["entries"][0]["result"]
    assert result["ai"]["scope"] == mode and result["ai"]["generation_attempted"]
    assert len(provider.calls) == 1 and result["ai_state"] == "ran"


def test_full_ai_makes_a_new_request_even_for_cached_identical_source(client, project_root):
    provider = ContractProvider([proposal()])
    login(client, project_root)
    assert configure(client, provider, enabled=False).status_code == 200
    data = word("Animal testing")
    first = client.post("/api/batches?ai_mode=full", files=[("files", ("same.docx", data))])
    a = finished(client, first.json()["run_id"])["entries"][0]["result"]
    provider.values = []
    second = client.post("/api/batches?ai_mode=full", files=[("files", ("same.docx", data))])
    b = finished(client, second.json()["run_id"])["entries"][0]["result"]
    assert a["paper_id"] == b["paper_id"] and len(provider.calls) == 2
    assert a["ai"]["accepted"] == 1 and b["ai"]["accepted"] == 0
    assert a["ai"]["generation_attempted"] and b["ai"]["generation_attempted"]
