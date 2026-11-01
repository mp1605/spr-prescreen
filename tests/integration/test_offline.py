"""Offline state is observable; explicit probes count without sending an external packet."""

import socket

import pytest

from backend.security.airlock import OfflineBlocked


def test_offline_status_and_blocked_probe(client):
    first = client.get("/api/system/offline")
    assert first.status_code == 200
    data = first.json()
    assert data["airlock_installed"] and isinstance(data["blocked_attempts"], int)
    assert data["listener_inspection"] in {"available", "partial", "unavailable"}
    assert isinstance(data["ai_reachable"], bool)
    assert "not an operating-system firewall" in data["native_scope"]
    with pytest.raises(OfflineBlocked):
        socket.create_connection(("example.com", 443), timeout=1)
    after = client.get("/api/system/offline").json()
    assert after["blocked_attempts"] == data["blocked_attempts"] + 1
    assert client.get("/api/health").status_code == 200


def test_startup_validation_does_not_read_runs(project_root, monkeypatch):
    import backend.boot as boot
    from backend.boot import validate_setup
    from backend.core.assets import AssetStatus

    private = project_root / "runs/web-retained/results.json"
    private.parent.mkdir(parents=True)
    private.write_bytes(b"intentionally not a run record")
    monkeypatch.setattr(
        boot,
        "model_status",
        lambda *a, **k: AssetStatus(ready=True, files=1, bytes=1, message="contract"),
    )
    assert not validate_setup(project_root).ai.enabled
