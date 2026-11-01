import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.core.ingest import DocumentInput, parse_many
from backend.core.ingest_models import IngestLimits, ParseResult
from backend.ingest.io import read_input

ROOT = Path(__file__).resolve().parents[2]


def test_cli_processes_mixed_inputs_and_records_unreadable_files(guide_pdf, guide_docx, tmp_path):
    pdf, word, bad, missing = [
        tmp_path / name for name in ("guide.pdf", "guide.docx", "bad.pdf", "missing.pdf")
    ]
    pdf.write_bytes(guide_pdf)
    word.write_bytes(guide_docx)
    bad.write_bytes(b"")
    output = tmp_path / "result.json"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.ingest",
            str(pdf),
            str(word),
            str(bad),
            str(missing),
            "--workers",
            "2",
            "--no-cache",
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
    assert payload["summary"] == {"complete": 2, "incomplete": 1, "rejected": 0}
    assert payload["input_errors"][0]["paper_id"] is None
    assert payload["input_errors"][0]["review_color"] == "yellow"
    assert payload["screening_state"] == "NOT_SCREENED"
    assert "Anything classified" not in process.stdout + process.stderr
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "name", ["policy_KEY.docx", "INDEX.csv", "expected_results.pdf", "keys/policy.pdf"]
)
def test_cli_blocks_evaluation_sources_before_file_reads(name, tmp_path):
    output = tmp_path / "result.json"
    process = subprocess.run(
        [sys.executable, "-m", "backend.ingest", str(tmp_path / name), "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert process.returncode == 2
    assert "blocked" in process.stderr
    assert not output.exists()


def test_oversize_file_read_hashes_the_entire_source(guide_pdf, tmp_path):
    path = tmp_path / "guide.pdf"
    path.write_bytes(guide_pdf)
    result = read_input(path, IngestLimits(max_file_bytes=10))
    assert isinstance(result, ParseResult)
    assert result.paper_id == "sha256:" + hashlib.sha256(guide_pdf).hexdigest()
    assert result.byte_count == len(guide_pdf)
    assert result.status == "rejected" and result.review_color == "yellow"


def test_format_parsing_requires_no_network(guide_pdf, guide_docx, monkeypatch):
    import socket

    attempts = []

    def blocked(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("Document parsing must not access the network")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    results = parse_many(
        [DocumentInput("guide.pdf", guide_pdf), DocumentInput("guide.docx", guide_docx)], workers=1
    )
    assert all(r.status == "complete" for r in results)
    assert not attempts
