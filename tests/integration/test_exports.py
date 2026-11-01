"""Round-trip exported artifacts with official words and atomic format fixtures only."""

import csv
import hashlib
import io
import json
import stat

import pymupdf
import pytest
from docx import Document

from backend.core.export import download_name
from backend.core.export_csv import spreadsheet_safe
from backend.core.export_models import ExportReport
from tests.integration.test_workflow import base_for, finished, upload, word


def test_json_csv_snapshots_include_all_entries_and_reversible_decisions(client, project_root):
    data = word("(CUI). Animal testing.")
    batch = finished(
        client, upload(client, [("official.docx", data), ("unsupported.txt", b"List 1")])["run_id"]
    )
    base = base_for(batch)
    paper = batch["entries"][0]["result"]
    flag = paper["findings"][0]
    immutable = project_root / "runs" / batch["run_id"] / "results.json"
    before = hashlib.sha256(immutable.read_bytes()).hexdigest()
    response = client.post(
        base + "/decisions",
        json={
            "revision": 0,
            "action": "override",
            "reviewer": "Format QA",
            "finding_id": flag["finding_id"],
            "reason": '=SUM(1,2)\n"review, note"',
        },
    )
    assert response.status_code == 200
    report_response = client.get(f"/api/batches/{batch['run_id']}/export/json?layout=audit")
    assert (
        report_response.status_code == 200
        and "attachment" in report_response.headers["content-disposition"]
    )
    report = report_response.json()
    ExportReport.model_validate(report)
    entry = batch["entries"][0]["entry_id"]
    rejected = batch["entries"][1]["entry_id"]
    assert report["batch"]["entries"][0]["result"] == paper
    assert report["reviews"][entry]["decisions"][flag["finding_id"]]["action"] == "override"
    assert report["source_sha256"][entry] == hashlib.sha256(data).hexdigest()
    assert report["source_integrity"][entry] == "verified"
    assert report["source_sha256"][rejected] is None
    csv_response = client.get(f"/api/batches/{batch['run_id']}/export/csv?layout=audit")
    assert csv_response.status_code == 200 and csv_response.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(csv_response.content.decode("utf-8-sig"))))
    overridden = next(r for r in rows if r["finding_id"] == flag["finding_id"])
    assert overridden["flag_color"] == flag["color"] and overridden["review_action"] == "override"
    assert overridden["review_reason"] == '\'=SUM(1,2)\n"review, note"'
    assert json.loads(overridden["review_history_json"])[0]["action"] == "override"
    assert any(r["phase"] == "rejected" and r["row_type"] == "entry" for r in rows)
    assert all(r["release_decision"] == "NOT_MADE_BY_TOOL" for r in rows)
    event = response.json()["events"][-1]
    undone = client.post(
        base + "/decisions",
        json={
            "revision": 1,
            "action": "undo",
            "reviewer": "Format QA",
            "finding_id": flag["finding_id"],
            "target_event": event["event_id"],
        },
    )
    assert undone.status_code == 200
    after = client.get(f"/api/batches/{batch['run_id']}/export/json?layout=audit").json()
    assert after["reviews"][entry]["decisions"] == {}
    assert len(after["reviews"][entry]["events"]) == 2
    assert report["reviews"][entry]["revision"] == 1 and after["reviews"][entry]["revision"] == 2
    assert hashlib.sha256(immutable.read_bytes()).hexdigest() == before
    for name in ("report.json", "report.csv"):
        assert stat.S_IMODE((immutable.parent / name).stat().st_mode) == 0o600


@pytest.mark.parametrize("format", ["docx", "pdf"])
def test_annotated_download_hashes_cache_review_updates_and_unchanged_source(
    format, client, project_root
):
    if format == "docx":
        data = word("(CUI). Animal testing.")
    else:
        with pymupdf.open() as document:
            document.new_page().insert_text((50, 80), "(CUI). Animal testing.")
            data = document.tobytes()
    batch = finished(client, upload(client, [(f"format-contract.{format}", data)])["run_id"])
    base = base_for(batch)
    entry = batch["entries"][0]
    flag = entry["result"]["findings"][0]
    first = client.get(base + "/annotated?notes=true")
    assert first.status_code == 200
    manifest = client.get(base + "/annotation-manifest?notes=true").json()
    assert manifest["source_sha256"] == hashlib.sha256(data).hexdigest()
    assert manifest["annotated_sha256"] == hashlib.sha256(first.content).hexdigest()
    assert first.headers["x-source-sha256"] == manifest["source_sha256"]
    assert first.headers["x-artifact-sha256"] == manifest["annotated_sha256"]
    assert first.content != data and client.get(base + "/original").content == data
    assert client.get(base + "/annotated?notes=true").content == first.content
    decision = client.post(
        base + "/decisions",
        json={
            "revision": 0,
            "action": "override",
            "reviewer": "Format QA",
            "finding_id": flag["finding_id"],
            "reason": "Format contract",
        },
    )
    assert decision.status_code == 200
    second = client.get(base + "/annotated?notes=true")
    details = client.get(base + "/annotation-manifest?notes=true").json()
    assert second.status_code == 200 and second.content != first.content
    assert (
        details["review_revision"] == 1
        and details["annotated_sha256"] == hashlib.sha256(second.content).hexdigest()
    )
    if format == "docx":
        opened = Document(io.BytesIO(second.content))
        assert any("Reviewer decision: override" in c.text for c in opened.comments)
    else:
        with pymupdf.open(stream=second.content, filetype="pdf") as document:
            page = document[0]
            assert any("Reviewer decision: override" in a.info["content"] for a in page.annots())
    directory = project_root / "runs" / batch["run_id"] / "annotated"
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in directory.iterdir())
    assert client.get(base).json()["result"] == entry["result"]
    # A fresh download repairs a corrupt derived copy without trusting its manifest.
    current = next(p for p in directory.glob(f"*.{format}") if p.read_bytes() == second.content)
    current.write_bytes(b"corrupt derived copy")
    repaired = client.get(base + "/annotated?notes=true")
    assert repaired.status_code == 200
    assert (
        hashlib.sha256(repaired.content).hexdigest()
        == client.get(base + "/annotation-manifest?notes=true").json()["annotated_sha256"]
    )


def test_missing_and_changed_sources_leave_report_available_but_refuse_annotation(
    client, project_root
):
    batch = finished(client, upload(client, [("format.docx", word("Animal testing"))])["run_id"])
    base = base_for(batch)
    entry = batch["entries"][0]["entry_id"]
    source = project_root / "runs" / batch["run_id"] / entry / "source.bin"
    source.write_bytes(b"changed")
    assert client.get(base + "/annotated").status_code == 422
    report = client.get(f"/api/batches/{batch['run_id']}/export/json?layout=audit").json()
    assert report["source_integrity"][entry] == "mismatch"
    assert report["source_sha256"][entry] != report["current_source_sha256"][entry]
    source.unlink()
    assert client.get(base + "/annotated").status_code == 422
    report = client.get(f"/api/batches/{batch['run_id']}/export/json?layout=audit").json()
    assert report["source_integrity"][entry] == "unavailable"
    assert report["source_sha256"][entry] and report["current_source_sha256"][entry] is None


def test_flagless_and_incomplete_rows_are_kept(client, orthogonal_semantics):
    batch = finished(
        client,
        upload(client, [("heading.docx", word("List 1")), ("corrupt.pdf", b"not pdf")])["run_id"],
    )
    response = client.get(f"/api/batches/{batch['run_id']}/export/csv?layout=audit")
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert len(rows) == 2 and rows[0]["paper_color"] == "green"
    assert rows[0]["row_type"] == "paper" and rows[0]["flag_total"] == "0"
    assert rows[1]["paper_label"] == "Incomplete" and rows[1]["incomplete_reasons"]
    assert client.get(base_for(batch, 1) + "/annotated").status_code == 422
    annotated = client.get(base_for(batch) + "/annotated")
    assert annotated.status_code == 200
    assert len(Document(io.BytesIO(annotated.content)).comments) == 0


def test_unfinished_snapshot_has_no_fabricated_result_and_annotation_not_ready(client):
    batch = upload(client, [("format.docx", word("List 1"))])
    store = client.app.state.batch_service.store
    # A retained cancelled entry is an honest unfinished state, without racing an active parser.
    client.app.state.batch_service.cancel(batch["run_id"])
    saved = store.entry(batch["run_id"], batch["entries"][0]["entry_id"])
    assert saved.phase == "cancelled"
    base = base_for(batch)
    assert client.get(base + "/annotated").status_code == 409
    report = client.get(f"/api/batches/{batch['run_id']}/export/json?layout=audit").json()
    assert report["batch"]["entries"][0]["result"] is None
    assert report["source_integrity"][saved.entry_id] == "not_screened"


@pytest.mark.parametrize(
    "value", ["=SUM(1,2)", " +SUM(1)", "-1+2", "@function", "\t=1", "\rformula", "\nformula"]
)
def test_csv_formula_cells_are_prefixed_without_losing_content(value):
    assert spreadsheet_safe(value) == "'" + value


@pytest.mark.parametrize("value", ["Animal testing", 'normal, "quoted"\nvalue', None, 3])
def test_ordinary_csv_cells_preserve_value(value):
    assert spreadsheet_safe(value) == ("" if value is None else str(value))


def test_download_names_are_safe():
    assert download_name('../../\r\n"文書.docx', "-annotated.docx") == "document-annotated.docx"
