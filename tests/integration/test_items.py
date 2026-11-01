"""Item-navigation contracts use official phrases, not sponsor papers or expected results."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from backend.core.batch_models import BatchEntry, BatchRecord
from backend.core.ingest import parse_document
from backend.core.screen import screen_document
from tests.integration.test_workflow import base_for, finished, upload, word


@pytest.fixture
def item_batches(client):
    service = client.app.state.batch_service
    parsed = parse_document("official.docx", word("Animal testing"))
    result = screen_document(parsed, service.rules)
    assert any("L2-01" in f.items for f in result.findings)
    batches = []
    for number in range(2):
        batch = BatchRecord(
            run_id="web-" + uuid4().hex,
            created=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=number),
            rules_version=result.rules_version,
            entries=tuple(
                BatchEntry(
                    entry_id=uuid4().hex,
                    file_name=name,
                    phase="done",
                    result=result,
                )
                for name in ("Zulu.docx", "Alpha.docx")
            ),
        )
        service.store.save(batch)
        batches.append(batch)
    return batches


def test_index_has_official_order_counts_and_independent_duplicate_uploads(client, item_batches):
    response = client.get("/api/review/items")
    assert response.status_code == 200, response.text
    index = response.json()
    assert len(index["items"]) == 39
    assert [i["item_id"] for i in index["items"][:3]] == ["L1-1", "L1-3", "L1-4"]
    item = next(i for i in index["items"] if i["item_id"] == "L2-01")
    assert item["findings"] == item["papers"] == item["pending"] == 4
    assert item["yellow"] == 4 and item["red"] == 0
    assert item["accepted"] == item["overridden"] == 0
    assert index["scope"]["completed_papers"] == 4
    assert index["scope"]["run_ids"][0] == item_batches[1].run_id
    assert response.headers["cache-control"] == "no-store"


def test_scoped_pagination_and_filtering_keep_original_finding(client, item_batches):
    path = "/api/review/items/L2-01"
    first = client.get(path, params={"limit": 1}).json()
    assert first["total"] == 4 and first["has_more"]
    assert first["entries"][0]["file_name"] == "Alpha.docx"
    assert first["entries"][0]["run_id"] == item_batches[1].run_id
    second = client.get(
        path, params={"offset": 1, "limit": 1, "if_snapshot": first["scope"]["snapshot"]}
    ).json()
    assert second["entries"][0]["file_name"] == "Zulu.docx"
    row = first["entries"][0]
    original = client.get(row["decisions_url"].removesuffix("/decisions")).json()
    assert row["finding"] in original["result"]["findings"]
    assert row["review_url"] == f"/review/{row['run_id']}/{row['entry_id']}"
    scoped = client.get(path, params={"run_id": item_batches[0].run_id}).json()
    assert scoped["total"] == 2
    repeated = client.get(path, params=[("run_id", item_batches[0].run_id)] * 2).json()
    assert repeated["total"] == 2
    assert client.get(path, params={"search": "ALPHA"}).json()["total"] == 2
    assert client.get(path, params={"color": "red"}).json()["total"] == 0
    assert client.get(path, params={"offset": 200}).json()["entries"] == []
    assert client.get(path, params={"review_status": "reviewed"}).json()["total"] == 0


def test_existing_decisions_change_item_progress_and_stale_pages_fail(
    client, item_batches, project_root
):
    path = "/api/review/items/L2-01"
    before = client.get(path).json()
    row = before["entries"][0]
    raw = project_root / "runs" / row["run_id"] / "results.json"
    original = raw.read_bytes()
    command = {
        "action": "accept",
        "reviewer": "Item reviewer",
        "revision": row["review_revision"],
        "finding_id": row["finding"]["finding_id"],
    }
    response = client.post(row["decisions_url"], json=command)
    assert response.status_code == 200
    assert client.get(path, params={"if_snapshot": before["scope"]["snapshot"]}).status_code == 409
    page = client.get(path, params={"review_status": "reviewed"}).json()
    assert page["total"] == page["item"]["accepted"] == 1
    assert page["item"]["pending"] == 3
    assert page["entries"][0]["decision"]["reviewer"] == "Item reviewer"
    assert client.post(row["decisions_url"], json=command).status_code == 409
    state = response.json()
    override = client.post(
        row["decisions_url"],
        json=command | {"action": "override", "revision": state["revision"], "reason": "Contract"},
    ).json()
    assert client.get(path).json()["item"]["overridden"] == 1
    undo = command | {
        "action": "undo",
        "revision": override["revision"],
        "target_event": override["decisions"][command["finding_id"]]["event_id"],
    }
    assert client.post(row["decisions_url"], json=undo).status_code == 200
    assert client.get(path).json()["item"]["accepted"] == 1
    assert raw.read_bytes() == original


def test_empty_index_is_zero_review_activity_not_scanner_accuracy(client):
    index = client.get("/api/review/items").json()
    assert index["scope"]["run_ids"] == [] and len(index["items"]) == 39
    assert all(item["findings"] == 0 for item in index["items"])
    page = client.get("/api/review/items/L1-1").json()
    assert page["entries"] == [] and not page["has_more"]
    assert page["release_decision"] == "NOT_MADE_BY_TOOL"


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
        "color=green",
        "review_status=accepted",
        "run_id=bad",
        "if_snapshot=bad",
    ],
)
def test_bad_item_query_is_rejected(client, query):
    assert client.get("/api/review/items/L2-01?" + query).status_code == 422


def test_unknown_item_and_run_do_not_fall_back_to_other_data(client, item_batches):
    assert client.get("/api/review/items/L1-2").status_code == 404
    assert client.get("/api/review/items", params={"run_id": "web-" + "0" * 32}).status_code == 404


def test_navigation_reads_no_originals_and_audits_once_per_run(client, item_batches, monkeypatch):
    from backend.core.review_store import ReviewStore

    calls = []
    previous = ReviewStore._events
    old_read = Path.read_bytes

    def counted(self, run):
        calls.append(run)
        return previous(self, run)

    def guarded(path):
        assert path.name not in {"source.bin", "parsed.json"}
        assert "data" not in path.parts and "keys" not in path.parts
        return old_read(path)

    monkeypatch.setattr(ReviewStore, "_events", counted)
    monkeypatch.setattr(Path, "read_bytes", guarded)
    assert client.get("/api/review/items/L2-01").status_code == 200
    assert sorted(calls) == sorted(b.run_id for b in item_batches)


def test_actual_upload_scanning_then_item_accept_uses_existing_audit(client):
    batch = finished(client, upload(client, [("official.docx", word("(CUI)"))])["run_id"])
    page = client.get("/api/review/items/L1-1", params={"run_id": batch["run_id"]}).json()
    assert page["total"] >= 1
    row = page["entries"][0]
    assert row["finding"]["quote"] == "(CUI)" and row["finding"]["color"] == "red"
    state = client.post(
        row["decisions_url"],
        json={
            "action": "accept",
            "reviewer": "Format check",
            "revision": 0,
            "finding_id": row["finding"]["finding_id"],
        },
    ).json()
    assert state == client.get(base_for(batch) + "/decisions").json()
    assert client.get("/api/review/items/L1-1").json()["item"]["accepted"] == 1


def test_batch_states_equal_individual_replay_with_one_audit_read(client, item_batches):
    from backend.core.review_store import ReviewStore

    store = client.app.state.batch_service.store
    reviews = ReviewStore(store)
    batch = item_batches[0]
    grouped = reviews.states(batch.run_id)
    assert grouped == {e.entry_id: reviews.state(batch.run_id, e.entry_id) for e in batch.entries}


def test_multi_item_math_contract_counts_overlap_without_splitting_evidence(client, item_batches):
    """A stored count contract, not a claim of policy applicability or scanner recall."""
    store = client.app.state.batch_service.store
    batch = item_batches[0]
    entry = batch.entries[0]
    paper = entry.result
    flag = paper.findings[0].model_copy(update={"items": ("L2-01", "L2-02")})
    store.update(
        batch.run_id,
        entry.model_copy(update={"result": paper.model_copy(update={"findings": (flag,)})}),
    )
    index = client.get("/api/review/items").json()
    counts = {item["item_id"]: item["findings"] for item in index["items"]}
    assert counts["L2-01"] == 4 and counts["L2-02"] == 1
    assert index["scope"]["unique_findings"] == 4
    row = client.get("/api/review/items/L2-02").json()["entries"][0]
    assert row["finding"]["items"] == ["L2-01", "L2-02"]
    assert row["finding"]["quote"] == flag.quote
    assert (
        client.post(
            row["decisions_url"],
            json={
                "action": "accept",
                "revision": row["review_revision"],
                "reviewer": "Count contract",
                "finding_id": flag.finding_id,
            },
        ).status_code
        == 200
    )
    assert client.get("/api/review/items/L2-01").json()["item"]["accepted"] == 1
    assert client.get("/api/review/items/L2-02").json()["item"]["accepted"] == 1


def test_partial_runs_are_disclosed_and_retained_results_do_not_leak(client, item_batches):
    store = client.app.state.batch_service.store
    batch = item_batches[0]
    store.update(batch.run_id, batch.entries[0].model_copy(update={"phase": "parsing"}))
    store.update(batch.run_id, batch.entries[1].model_copy(update={"phase": "failed"}))
    index = client.get("/api/review/items").json()
    assert index["scope"]["completed_papers"] == 2
    assert index["scope"]["unfinished_entries"] == 1
    assert index["scope"]["unavailable_entries"] == 1
    assert client.get("/api/review/items/L2-01").json()["total"] == 2


def test_run_scope_limit_and_mismatched_snapshot_are_enforced(client, item_batches):
    run = item_batches[0].run_id
    assert client.get("/api/review/items", params=[("run_id", run)] * 101).status_code == 422
    all_runs = client.get("/api/review/items").json()
    assert (
        client.get(
            "/api/review/items/L2-01",
            params={"run_id": run, "if_snapshot": all_runs["scope"]["snapshot"]},
        ).status_code
        == 409
    )


def test_queue_uses_one_audit_read_per_batch(client, item_batches, monkeypatch):
    from backend.core.review_store import ReviewStore

    calls = []
    original = ReviewStore._events

    def counted(self, run):
        calls.append(run)
        return original(self, run)

    monkeypatch.setattr(ReviewStore, "_events", counted)
    assert client.get("/api/batches").status_code == 200
    assert len(calls) == len(item_batches)


def test_item_rows_preserve_recorded_version_and_incomplete_source(client, item_batches):
    store = client.app.state.batch_service.store
    batch = item_batches[0]
    entry = batch.entries[0]
    result = entry.result.model_copy(
        update={
            "rules_version": "historical-contract-version",
            "incomplete_pages": (1,),
            "incomplete_reasons": ("Format contract incomplete",),
            "label": "Incomplete",
        }
    )
    store.update(batch.run_id, entry.model_copy(update={"result": result}))
    page = client.get("/api/review/items/L2-01", params={"run_id": batch.run_id}).json()
    row = next(r for r in page["entries"] if r["entry_id"] == entry.entry_id)
    assert row["rules_version"] == "historical-contract-version"
    assert row["incomplete_reasons"] == ["Format contract incomplete"]
    assert row["incomplete_pages"] == [1]
    assert page["scope"]["incomplete_papers"] == 1


def test_damaged_result_fails_visibly_instead_of_an_empty_green_queue(client, item_batches):
    store = client.app.state.batch_service.store
    path = store.path(item_batches[0].run_id) / "results.json"
    original = path.read_bytes()
    try:
        path.write_bytes(b"invalid contract JSON")
        response = client.get("/api/review/items")
        assert response.status_code == 422
        assert "damaged stored record" in response.json()["detail"]
    finally:
        # Leave the isolated fixture valid for the existing service shutdown scan.
        path.write_bytes(original)
