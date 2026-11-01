import json
import subprocess
import sys
from io import BytesIO
from pathlib import Path

import pytest
from docx import Document

from backend.core.engines.rules import RulesEngine
from backend.core.ingest import parse_document
from backend.core.screen import screen_document

ROOT = Path(__file__).resolve().parents[2]


def word_bytes(*texts):
    document = Document()
    for text in texts:
        document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_real_cli_batch_preserves_findings_errors_order_and_rules_version(registry, tmp_path):
    pdf, word, corrupt, green, unsupported, missing = [
        tmp_path / name
        for name in (
            "policy.pdf",
            "policy.docx",
            "corrupt.pdf",
            "heading.docx",
            "unsupported.txt",
            "missing.docx",
        )
    ]
    pdf.write_bytes((ROOT / "docs/official-lists.pdf").read_bytes())
    word.write_bytes(word_bytes(registry.list1[0].examples, registry.list2[0].text))
    corrupt.write_bytes(b"")
    green.write_bytes(word_bytes("List 2"))
    unsupported.write_bytes(b"")
    output = tmp_path / "screen.json"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.screen",
            str(pdf),
            str(word),
            str(corrupt),
            str(green),
            str(unsupported),
            str(missing),
            "--workers",
            "2",
            "--no-cache",
            "--rules-only",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 2
    payload = json.loads(output.read_text())
    assert payload["summary"] == dict(
        green=1, yellow=1, red=2, incomplete=1, rejected=1, unreadable_inputs=1
    )
    assert [paper["file_name"] for paper in payload["papers"]] == [
        p.name for p in (pdf, word, corrupt, green)
    ]
    assert all(p["trace"] == ["list1:done", "list2:done"] for p in payload["papers"])
    assert all(p["rules_version"] == registry.policy_version for p in payload["papers"])
    assert all(p["release_decision"] == "NOT_MADE_BY_TOOL" for p in payload["papers"])
    assert payload["screening_stage"] == "rules_only" and payload["limitations"]
    assert payload["input_errors"][0]["paper_id"] is None
    assert payload["rejected_inputs"][0]["status"] == "rejected"
    assert payload["papers"][2]["label"] == "Incomplete"
    assert payload["timing"]["paper_seconds_scope"] == "rules stage only"
    assert "Anything classified" not in process.stdout + process.stderr
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("name", ["policy_KEY.docx", "keys/policy.pdf", "expected_results.pdf"])
def test_screen_cli_does_not_open_evaluation_paths(name, tmp_path):
    output = tmp_path / "never-created.json"
    process = subprocess.run(
        [sys.executable, "-m", "backend.screen", str(tmp_path / name), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert process.returncode == 2 and "blocked" in process.stderr
    assert not output.exists()


def test_successful_yellow_pre_screen_is_not_a_command_error(registry, tmp_path):
    path = tmp_path / "official-wording.docx"
    path.write_bytes(word_bytes(registry.list2[0].text))
    output = tmp_path / "screen.json"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.screen",
            str(path),
            "--workers",
            "1",
            "--no-cache",
            "--rules-only",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert process.returncode == 0
    result = json.loads(output.read_text())["papers"][0]
    assert result["color"] == "yellow" and result["release_decision"] == "NOT_MADE_BY_TOOL"


def test_rule_screening_uses_no_network_or_evaluation_files(registry, monkeypatch):
    import socket

    attempts = []
    old_open = Path.open

    def blocked(*args, **kwargs):
        attempts.append("network")
        raise AssertionError("No network access")

    def guard(path, *args, **kwargs):
        if "keys" in path.parts or path.stem.casefold().endswith("_key"):
            attempts.append("evaluation")
            raise AssertionError("No evaluation access")
        return old_open(path, *args, **kwargs)

    data = word_bytes(registry.list1[0].examples, registry.list2[0].text)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(Path, "open", guard)
    result = screen_document(
        parse_document("official-wording.docx", data), registry, engine=RulesEngine(registry)
    )
    assert result.color == "red" and result.flag_count.yellow > 0
    assert not attempts
