"""Admin workflow contracts with official words and typed/format inputs only."""

import hashlib
import os
import time

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.rules_loader import load_rules
from backend.security.auth import AuthFailure, AuthService, initialize_admin
from tests.integration.test_workflow import base_for, finished, upload, word

PASSWORD = "format-contract-password"


def login(client, root):
    initialize_admin(root, PASSWORD)
    response = client.post("/api/admin/login", json={"password": PASSWORD})
    assert response.status_code == 200
    return response


def create(client):
    response = client.post("/api/admin/rules/drafts", json={})
    assert response.status_code == 201, response.text
    return response.json()


def changed_yaml(draft, term="List 1"):
    data = yaml.safe_load(draft["yaml_text"])
    data["list2"][0]["detectors"].append(
        {
            "kind": "keywords",
            "name": "Official heading format contract",
            "item_id": "L2-01",
            "terms": [term],
        }
    )
    return yaml.safe_dump(data, sort_keys=False)


def edit_validate(client, draft, text):
    base = "/api/admin/rules/drafts/" + draft["draft_id"]
    response = client.put(base, json={"revision": draft["revision"], "yaml_text": text})
    assert response.status_code == 200, response.text
    draft = response.json()
    response = client.post(base + "/validate", json={"revision": draft["revision"]})
    assert response.status_code == 200, response.text
    return response.json()


def preview(client, draft, data=None):
    base = "/api/admin/rules/drafts/" + draft["draft_id"]
    response = client.post(
        base + f"/preview?revision={draft['revision']}",
        files=[("files", ("heading.docx", data or word("List 1")))],
    )
    assert response.status_code == 202, response.text
    identifier = response.json()["preview"]["preview_id"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        report = client.get("/api/admin/rules/previews/" + identifier).json()
        if report["state"] not in ("queued", "running"):
            break
        time.sleep(0.02)
    assert report["state"] == "complete", report
    draft = client.get(base).json()
    return draft, report


def publish(client, draft):
    response = client.post(
        "/api/admin/rules/drafts/" + draft["draft_id"] + "/publish",
        json={
            "revision": draft["revision"],
            "preview_id": draft["preview_id"],
            "change_note": "Official format contract",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_reviewer_is_read_only_for_every_admin_policy_route(client):
    paths = [
        ("get", "/rules/history", None),
        ("get", "/rules/drafts", None),
        ("post", "/rules/drafts", {}),
        ("get", "/rules/drafts/" + "a" * 32, None),
        ("put", "/rules/drafts/" + "a" * 32, {"revision": 0, "yaml_text": "x"}),
        ("post", "/rules/drafts/" + "a" * 32 + "/validate", {"revision": 0}),
        (
            "post",
            "/rules/drafts/" + "a" * 32 + "/publish",
            {"revision": 0, "preview_id": "a" * 32, "change_note": "format"},
        ),
        ("get", "/rules/previews/" + "a" * 32, None),
    ]
    for method, path, payload in paths:
        assert client.request(method, "/api/admin" + path, json=payload).status_code == 403
    assert (
        client.post(
            "/api/admin/rules/drafts/" + "a" * 32 + "/preview?revision=0",
            files=[("files", ("format.docx", word()))],
        ).status_code
        == 403
    )
    assert client.get("/api/rules").status_code == 200


def test_credentials_cookie_logout_rate_limit_and_expiry(client, project_root):
    response = login(client, project_root)
    content = (project_root / "config/admin.json").read_text()
    assert PASSWORD not in content and "$argon2id$" in content
    assert os.stat(project_root / "config/admin.json").st_mode & 0o777 == 0o600
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "max-age=1800" in cookie
    assert client.get("/api/admin/session").json()["authenticated"]
    assert client.post("/api/admin/logout").status_code == 204
    assert not client.get("/api/admin/session").json()["authenticated"]
    auth = client.app.state.auth_service
    clock = [0.0]
    auth.clock = lambda: clock[0]
    auth.attempts.clear()
    for _ in range(5):
        assert client.post("/api/admin/login", json={"password": "invalid"}).status_code == 403
    denied = client.post("/api/admin/login", json={"password": PASSWORD})
    assert denied.status_code == 429 and int(denied.headers["retry-after"]) > 0
    clock[0] = 61
    assert client.post("/api/admin/login", json={"password": PASSWORD}).status_code == 200
    clock[0] += 1801
    assert client.get("/api/admin/rules/history").status_code == 403


def test_reset_invalidates_sessions_and_restart_requires_login(project_root):
    initialize_admin(project_root, PASSWORD)
    auth = AuthService(project_root)
    token, _ = auth.login(PASSWORD)
    assert auth.status(token).authenticated
    initialize_admin(project_root, PASSWORD + "new", reset=True)
    assert not auth.status(token).authenticated
    assert not AuthService(project_root).status(token).authenticated
    with pytest.raises(AuthFailure, match="already initialized"):
        initialize_admin(project_root, PASSWORD)


@pytest.mark.parametrize("password", ["short", "x" * 1025])
def test_bad_setup_password_refused(project_root, password):
    with pytest.raises(AuthFailure, match="12 and 1024"):
        initialize_admin(project_root, password)


def test_official_wording_and_regex_fail_validation_with_visible_diff(client, project_root):
    login(client, project_root)
    draft = create(client)
    data = yaml.safe_load(draft["yaml_text"])
    data["list2"][0]["text"] += " modified"
    draft = edit_validate(client, draft, yaml.safe_dump(data))
    assert not draft["validation"]["valid"]
    assert any(c["protected"] and c["field"] == "text" for c in draft["validation"]["changes"])
    data = yaml.safe_load(draft["yaml_text"])
    data["list2"][0]["text"] = "Animal testing"
    data["list2"][0]["detectors"][0] = {
        "kind": "regex",
        "item_id": "L2-01",
        "name": "Invalid format",
        "pattern": "[",
    }
    draft = edit_validate(client, draft, yaml.safe_dump(data))
    assert not draft["validation"]["valid"] and "Invalid regex" in str(
        draft["validation"]["errors"]
    )


def test_publish_preview_rollback_and_new_scans_use_version_while_old_results_stay_immutable(
    client, project_root, orthogonal_semantics
):
    login(client, project_root)
    versions = client.get("/api/admin/rules/history").json()["versions"]
    baseline_version = load_rules(project_root).policy_version
    baseline_archive = next(v["file"] for v in versions if v["version"] == baseline_version)
    next_number = 1 + max(
        int(v["file"].removeprefix("rules_v").removesuffix(".yaml")) for v in versions
    )
    old = finished(client, upload(client, [("heading.docx", word("List 1"))])["run_id"])
    old_path = project_root / "runs" / old["run_id"] / "results.json"
    before = hashlib.sha256(old_path.read_bytes()).hexdigest()
    assert old["entries"][0]["result"]["color"] == "green"
    draft = create(client)
    draft = edit_validate(client, draft, changed_yaml(draft))
    assert draft["validation"]["valid"]
    premature = client.post(
        "/api/admin/rules/drafts/" + draft["draft_id"] + "/publish",
        json={"revision": draft["revision"], "preview_id": "a" * 32, "change_note": "format"},
    )
    assert premature.status_code in (404, 422)
    draft, report = preview(client, draft)
    assert report["eligible"] and report["entries"][0]["changed"]
    assert (
        report["entries"][0]["before"]["color"] == "green"
        and report["entries"][0]["after"]["color"] == "yellow"
    )
    active = publish(client, draft)
    assert active["version"] == f"LOE2-guide-v{next_number}-admin"
    assert load_rules(project_root).policy_version == active["version"]
    assert client.get("/api/rules").json()["policy_version"] == active["version"]
    assert client.get("/api/health").json()["rules_version"] == active["version"]
    new = finished(client, client.post(f"/api/batches/{old['run_id']}/rescan").json()["run_id"])
    assert new["entries"][0]["result"]["color"] == "yellow"
    assert new["entries"][0]["result"]["rules_version"] == active["version"]
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == before
    restore = client.post("/api/admin/rules/drafts", json={"restore_from": baseline_archive}).json()
    restored = edit_validate(client, restore, restore["yaml_text"])
    restored, report = preview(client, restored)
    assert (
        report["entries"][0]["before"]["color"] == "yellow"
        and report["entries"][0]["after"]["color"] == "green"
    )
    rollback = publish(client, restored)
    assert rollback["version"] == f"LOE2-guide-v{next_number + 1}-admin"
    assert client.get("/api/admin/rules/history").json()["audit"][-1]["operation"] == "rollback"
    newest = finished(client, upload(client, [("heading.docx", word("List 1"))])["run_id"])
    assert newest["entries"][0]["result"]["color"] == "green"
    assert hashlib.sha256(old_path.read_bytes()).hexdigest() == before
    with TestClient(
        create_app(project_root, semantic_provider=client.app.state.semantic_engine.provider),
        base_url="http://127.0.0.1",
    ) as restarted:
        assert restarted.get("/api/health").json()["rules_version"] == rollback["version"]
        assert restarted.get("/api/admin/rules/history").status_code == 403


def test_stale_draft_and_edit_invalidate_preview(client, project_root, orthogonal_semantics):
    login(client, project_root)
    draft = create(client)
    draft = edit_validate(client, draft, changed_yaml(draft))
    draft, report = preview(client, draft)
    old = dict(draft)
    saved = client.put(
        "/api/admin/rules/drafts/" + draft["draft_id"],
        json={"revision": draft["revision"], "yaml_text": draft["yaml_text"] + "\n"},
    ).json()
    assert saved["preview_id"] is None and saved["validation"] is None
    assert (
        client.post(
            "/api/admin/rules/drafts/" + draft["draft_id"] + "/validate",
            json={"revision": old["revision"]},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/admin/rules/drafts/" + draft["draft_id"] + "/publish",
            json={
                "revision": saved["revision"],
                "preview_id": report["preview_id"],
                "change_note": "format",
            },
        ).status_code
        == 422
    )


def test_no_dataset_discovery_and_bad_preview_is_not_publishable(
    client, project_root, orthogonal_semantics, monkeypatch
):
    login(client, project_root)
    draft = create(client)
    draft = edit_validate(client, draft, draft["yaml_text"])
    response = client.post(
        "/api/admin/rules/drafts/" + draft["draft_id"] + f"/preview?revision={draft['revision']}",
        files=[("files", ("format_KEY.docx", b"not read"))],
    )
    assert response.status_code == 422
    draft, report = preview(client, draft, b"corrupt DOCX")
    assert not report["eligible"] and draft["state"] == "validated"
    assert (
        report["source"] == "explicit_upload_only" and report["sponsor_metrics"] == "NOT_MEASURED"
    )
    assert not (project_root / "data").exists()


def test_cross_origin_write_rejected_even_with_admin_cookie(client, project_root):
    login(client, project_root)
    assert (
        client.post(
            "/api/admin/rules/drafts", json={}, headers={"Origin": "https://example.invalid"}
        ).status_code
        == 403
    )


def test_batch_context_pins_queued_work_during_policy_install(
    client, orthogonal_semantics, monkeypatch
):
    from threading import Event

    from backend.core.engines.rules import RulesEngine
    from backend.core.screening_context import ScreeningContext

    service = client.app.state.batch_service
    original = service.rules
    old_context = service.contexts[original.policy_version]
    entered = Event()
    release = Event()
    run = old_context.engine.run

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return run(*args, **kwargs)

    monkeypatch.setattr(old_context.engine, "run", blocked)
    batch = upload(client, [(f"heading-{i}.docx", word("List 1")) for i in range(5)])
    assert entered.wait(10)
    candidate = original.model_copy(update={"policy_version": "context-contract-v4"})
    service.install(ScreeningContext(candidate, RulesEngine(candidate), None, None))
    release.set()
    completed = finished(client, batch["run_id"])
    assert all(
        e["result"]["rules_version"] == original.policy_version for e in completed["entries"]
    )
    rescanned = finished(
        client, client.post(f"/api/batches/{batch['run_id']}/rescan").json()["run_id"]
    )
    assert all(e["result"]["rules_version"] == "context-contract-v4" for e in rescanned["entries"])


def test_restart_invalidates_inflight_preview_and_preserves_saved_draft(client, project_root):
    login(client, project_root)
    draft = create(client)
    manager = client.app.state.policy_manager
    saved = manager.read(draft["draft_id"]).model_copy(
        update={"state": "previewing", "preview_id": "a" * 32}
    )
    manager.save(saved)
    recovered = client.get("/api/admin/rules/drafts/" + draft["draft_id"]).json()
    assert recovered["state"] == "validated" and recovered["preview_id"] is None
    assert recovered["yaml_text"] == draft["yaml_text"]


def test_cli_password_prompt_never_prints_secret(monkeypatch, capsys):
    from backend.admin import __main__ as cli

    values = iter([PASSWORD, PASSWORD])
    seen = []
    monkeypatch.setattr("sys.argv", ["backend.admin", "init"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: next(values))
    monkeypatch.setattr(
        cli, "initialize_admin", lambda root, password, reset: seen.append((password, reset))
    )
    assert cli.main() == 0 and seen == [(PASSWORD, False)]
    assert PASSWORD not in capsys.readouterr().out


def test_rescan_rejects_missing_changed_oversize_sources_and_retains_old_review(
    client, project_root, orthogonal_semantics
):
    import hashlib

    batch = finished(
        client, upload(client, [(f"heading-{i}.docx", word("List 1")) for i in range(3)])["run_id"]
    )
    base = base_for(batch)
    response = client.post(
        base + "/decisions", json={"revision": 0, "action": "inspect", "reviewer": "Format QA"}
    )
    assert response.status_code == 200
    root = project_root / "runs" / batch["run_id"]
    digest = hashlib.sha256((root / "results.json").read_bytes()).hexdigest()
    sources = [root / e["entry_id"] / "source.bin" for e in batch["entries"]]
    sources[0].write_bytes(b"changed")
    sources[1].unlink()
    with sources[2].open("wb") as handle:
        handle.truncate(25 * 1024**2 + 1)
    response = client.post(f"/api/batches/{batch['run_id']}/rescan")
    assert response.status_code == 202
    rescanned = response.json()
    assert all(e["phase"] == "rejected" and e["result"] is None for e in rescanned["entries"])
    assert "hash changed" in rescanned["entries"][0]["message"]
    assert "No retained original" in rescanned["entries"][1]["message"]
    assert "25 MiB" in rescanned["entries"][2]["message"]
    assert hashlib.sha256((root / "results.json").read_bytes()).hexdigest() == digest
    assert client.get(base + "/decisions").json()["inspected"]
    assert not client.get(base_for(rescanned) + "/decisions").json()["inspected"]
