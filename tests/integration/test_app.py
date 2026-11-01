import os

import pytest


def test_health_reports_actual_policy(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert (data["list1_count"], data["list2_count"]) == (8, 31)
    assert data["screening_available"] is True
    assert data["screening_stage"] == "rules_semantic"
    assert data["milestone"] == "M12" and data["detector_count"] > 0
    assert data["evaluation_harness_available"] and data["sponsor_evaluation_state"] == "deferred"
    assert data["release_decision"] == "NOT_MADE_BY_TOOL"


@pytest.mark.parametrize("path", ["/", "/rules", "/system", "/offline", "/items"])
def test_spa_routes_and_security_headers(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert '<div id="root">' in response.text
    assert "script-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_policy_is_read_only_and_source_is_available(client):
    assert len(client.get("/api/rules").json()["list2"]) == 31
    assert client.post("/api/rules", json={}).status_code == 405
    source = client.get("/api/rules/source")
    assert source.status_code == 200 and source.content.startswith(b"%PDF")


@pytest.mark.parametrize(
    "path", ["/api/unknown", "/unknown", "/data/keys", "/MASTER_PROMPT.md", "/scorecard"]
)
def test_missing_features_and_private_files_are_not_spa_successes(client, path):
    assert client.get(path).status_code == 404


def test_untrusted_host_rejected(client):
    assert client.get("/api/health", headers={"host": "external.invalid"}).status_code == 400


def test_no_network_model_downloads_at_runtime(client):
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["HF_HUB_DISABLE_TELEMETRY"] == "1"
    data = client.get("/api/system").json()
    assert data["ai_enabled"] is False
    assert data["sponsor_material_access"] is False
    assert data["airlock_installed"] is True
