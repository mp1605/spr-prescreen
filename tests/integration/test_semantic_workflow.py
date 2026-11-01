import hashlib
import json
import subprocess
import sys

from backend.core.ingest import parse_document
from backend.core.screen import screen_document
from tests.conftest import ROOT
from tests.integration.test_workflow import base_for, finished, upload, word


def test_semantic_api_provenance_and_reversible_feedback_never_changes_matching(
    client, project_root
):
    host = client.app.state.semantic_engine
    data = word(host.registry.list2[0].text)
    batch = finished(client, upload(client, [("official-rule.docx", data)])["run_id"])
    base = base_for(batch)
    paper = batch["entries"][0]["result"]
    assert paper["screening_stage"] == "rules_semantic"
    assert paper["semantic"]["state"] == "complete"
    assert paper["semantic"]["reference_source"] == "official_rules_only"
    finding = next(flag for flag in paper["findings"] if "semantic" in flag["engines"])
    assert finding["semantic_matches"][0]["source"] == "official_rule"
    assert finding["score"] > 0.99 and finding["nearest_exemplar"] is None
    snapshot = project_root / "runs" / batch["run_id"] / "results.json"
    before = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    command = {
        "reviewer": "One",
        "revision": 0,
        "action": "accept",
        "finding_id": finding["finding_id"],
    }
    positive = client.post(base + "/decisions", json=command).json()
    assert positive["feedback_examples"][0]["polarity"] == "positive"
    command |= {"revision": 1, "action": "override"}
    negative = client.post(base + "/decisions", json=command).json()
    assert negative["feedback_examples"][0]["polarity"] == "negative"
    assert negative["feedback_examples"][0]["usage"] == "excluded_during_blind_build"
    assert negative["feedback_examples"][0]["quote"] == finding["quote"]
    undone = client.post(
        base + "/decisions",
        json={
            "reviewer": "One",
            "revision": 2,
            "action": "undo",
            "finding_id": finding["finding_id"],
            "target_event": negative["events"][-1]["event_id"],
        },
    ).json()
    assert undone["feedback_examples"][0]["polarity"] == "positive"
    withdrawn = client.post(
        base + "/decisions",
        json={
            "reviewer": "One",
            "revision": 3,
            "action": "undo",
            "finding_id": finding["finding_id"],
            "target_event": positive["events"][0]["event_id"],
        },
    ).json()
    assert withdrawn["feedback_examples"] == []
    assert len(withdrawn["events"]) == 4
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == before
    assert finding["quote"] not in snapshot.with_name("decisions.jsonl").read_text()
    parsed = parse_document("official-rule.docx", data)
    repeated = screen_document(
        parsed,
        host.registry,
        engine=client.app.state.rules_engine,
        semantic=host.session(),
        specificity=client.app.state.specificity_engine,
    )
    assert repeated.model_dump(mode="json")["findings"] == paper["findings"]
    status = client.get("/api/system").json()
    assert status["semantic_enabled"] and status["semantic_state"] == "ready"
    assert status["feedback_usage"] == "excluded_during_blind_build"
    assert client.get(base + "/decisions").json() == withdrawn


def test_default_cli_runs_real_semantics_and_baseline_is_explicit(tmp_path):
    source = tmp_path / "official-wording.docx"
    source.write_bytes(word("Animal testing"))
    output = tmp_path / "semantic.json"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.screen",
            str(source),
            "--workers",
            "1",
            "--no-cache",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    payload = json.loads(output.read_text())
    assert payload["screening_stage"] == "rules_semantic"
    paper = payload["papers"][0]
    assert paper["semantic"]["state"] == "complete" and paper["trace"] == [
        "list1:done",
        "list2:done",
    ]
    assert any("semantic" in flag["engines"] for flag in paper["findings"])
    assert paper["fusion"]["state"] == "complete"
    assert all(flag["assessment"] for flag in paper["findings"])
    assert "Animal testing" not in process.stdout + process.stderr
    assert payload["semantic_configuration"]["calibrated"] is False
