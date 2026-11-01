"""Deferred scorecard responses never open datasets, reports, keys or prior user runs."""

from pathlib import Path

import pytest


@pytest.mark.parametrize("split", ["dev", "holdout"])
def test_scorecard_is_explicitly_unmeasured_without_file_access(client, split, monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Scorecard status must not access files or discover datasets")

    monkeypatch.setattr(Path, "read_bytes", blocked)
    monkeypatch.setattr(Path, "read_text", blocked)
    monkeypatch.setattr(Path, "glob", blocked)
    monkeypatch.setattr(Path, "rglob", blocked)
    response = client.get("/api/evaluation/scorecard/" + split)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["split"] == split and data["state"] == "deferred"
    assert data["report"] is None
    assert data["sponsor_accuracy_measured"] is data["sponsor_material_access"] is False
    assert data["release_decision"] == "NOT_MADE_BY_TOOL"
    assert response.headers["cache-control"] == "no-store"


def test_no_scorecard_run_or_key_upload_control_is_exposed(client):
    assert client.get("/api/evaluation/scorecard/unknown").status_code == 422
    assert client.post("/api/evaluation/scorecard/dev", json={}).status_code == 405
    # The existing SPA GET fallback rejects unmatched POSTs with Method Not Allowed.
    assert client.post("/api/evaluation/run", json={}).status_code == 405
