"""Readable local folder names preserve independent batch identity and stored bytes."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from backend.core.batch_folders import BatchFolders
from backend.core.batch_models import BatchEntry, BatchRecord
from backend.core.run_store import RunStore


def record(store, count=1, created=None):
    batch = BatchRecord(
        run_id="web-" + uuid4().hex,
        created=created or datetime(2026, 11, 1, 12, 15, 30, tzinfo=UTC),
        rules_version="format-contract",
        entries=tuple(
            BatchEntry(entry_id=uuid4().hex, file_name=f"document-{n}.docx", phase="cancelled")
            for n in range(count)
        ),
    )
    store.save(batch)
    return batch


def test_names_use_chicago_creation_time_and_file_count(tmp_path):
    store = RunStore(tmp_path)
    batch = record(store, 12)
    folders = BatchFolders(store)
    folders.prepare(batch.run_id)
    assert folders.path(batch.run_id).name == "2026-11-01_06-15-30-AM_12-files"
    assert folders.path(batch.run_id, "Approved").is_dir()
    assert store.path(batch.run_id).name == batch.run_id


def test_same_second_batches_never_share_a_folder_and_restart_resolves_them(tmp_path):
    store = RunStore(tmp_path)
    first, second = record(store), record(store)
    folders = BatchFolders(store)
    # Both names can be displayed before either folder is created.
    folders.path(first.run_id)
    folders.path(second.run_id)
    folders.prepare(first.run_id)
    folders.prepare(second.run_id)
    one, two = folders.path(first.run_id), folders.path(second.run_id)
    assert one.name == "2026-11-01_06-15-30-AM_1-file"
    assert two.name == one.name + "_Batch-2"
    assert one != two
    restarted = BatchFolders(store)
    assert restarted.path(first.run_id) == one
    assert restarted.path(second.run_id) == two
    assert json.loads((two / "manifest.json").read_bytes())["run_id"] == second.run_id


def test_legacy_rename_preserves_documents_manifest_audit_and_raw_results(tmp_path):
    store = RunStore(tmp_path)
    batch = record(store)
    folders = BatchFolders(store)
    old = folders.root / batch.run_id
    (old / "Approved").mkdir(parents=True)
    (old / "Approved/001_document.docx").write_bytes(b"original byte contract")
    manifest = json.dumps({"run_id": batch.run_id, "documents": {}}).encode()
    (old / "manifest.json").write_bytes(manifest)
    audit = store.path(batch.run_id) / "decisions.jsonl"
    audit.write_bytes(b"audit byte contract")
    raw = (store.path(batch.run_id) / "results.json").read_bytes()
    assert folders.migrate_existing() == 1
    new = folders.path(batch.run_id)
    assert not old.exists()
    assert (new / "Approved/001_document.docx").read_bytes() == b"original byte contract"
    assert (new / "manifest.json").read_bytes() == manifest
    assert audit.read_bytes() == b"audit byte contract"
    assert (store.path(batch.run_id) / "results.json").read_bytes() == raw
    assert folders.migrate_existing() == 0


def test_daylight_saving_repeated_hour_uses_separate_batch_folder(tmp_path):
    store = RunStore(tmp_path)
    first = record(store, created=datetime(2026, 11, 1, 6, 30, tzinfo=UTC))
    second = record(store, created=datetime(2026, 11, 1, 7, 30, tzinfo=UTC))
    folders = BatchFolders(store)
    folders.prepare(first.run_id)
    folders.prepare(second.run_id)
    assert folders.path(first.run_id).name == "2026-11-01_01-30-00-AM_1-file"
    assert folders.path(second.run_id).name.endswith("_Batch-2")


def test_migration_leaves_active_batch_for_app_restart(tmp_path):
    store = RunStore(tmp_path)
    batch = record(store)
    store.update(batch.run_id, batch.entries[0].model_copy(update={"phase": "parsing"}))
    folders = BatchFolders(store)
    old = folders.root / batch.run_id
    old.mkdir(parents=True)
    assert folders.migrate_existing() == 0 and old.is_dir()
