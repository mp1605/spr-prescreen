import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

from backend.eval.__main__ import main
from backend.eval.ledger import claim_holdout, finish_holdout
from backend.eval.report import deferred_report
from backend.eval.self_check import run_self_check
from backend.eval.split import case_ids, case_number, split_for

ROOT = Path(__file__).resolve().parents[2]


def test_frozen_split_is_exact_complete_and_disjoint():
    expected = {6, 11, 14, 15, 16, 26, 35, 37, 44, 49, 56, 60, 61, 62, 65, 71, 73, 74, 79, 80}
    dev, holdout = set(case_ids("dev")), set(case_ids("holdout"))
    assert {case_number(i) for i in holdout} == expected
    assert len(dev) == 60 and len(holdout) == 20 and not dev & holdout
    assert len(dev | holdout) == 80
    assert all(split_for(case) == "holdout" for case in holdout)


@pytest.mark.parametrize(
    "case", ["SPR-Test-000", "SPR-Test-081", "SPR-Test-6", "contract", "SPR-Test-006_KEY"]
)
def test_noncanonical_split_ids_are_rejected(case):
    with pytest.raises(ValueError):
        split_for(case)


@pytest.mark.parametrize("succeeded", [True, False])
def test_holdout_claim_is_once_even_after_failure_or_changed_fingerprint(succeeded, tmp_path):
    directory = tmp_path / "contract-ledger"
    path = claim_holdout(directory, "a" * 64)
    assert path.stat().st_mode & 0o777 == 0o600
    finish_holdout(directory, "a" * 64, succeeded=succeeded)
    assert json.loads(path.read_text())["status"] == ("complete" if succeeded else "failed")
    for digest in ("a" * 64, "b" * 64):
        with pytest.raises(ValueError, match="already"):
            claim_holdout(directory, digest)


def test_holdout_claim_requires_a_matching_frozen_identity(tmp_path):
    with pytest.raises(ValueError):
        claim_holdout(tmp_path, "not-a-hash")
    claim_holdout(tmp_path, "a" * 64)
    with pytest.raises(ValueError):
        finish_holdout(tmp_path, "b" * 64, succeeded=True)
    assert json.loads((tmp_path / "holdout-claim.json").read_text())["status"] == "started"


@pytest.mark.parametrize("split", ["dev", "holdout"])
def test_run_is_locked_before_any_dataset_discovery_or_ledger_claim(split, monkeypatch, capsys):
    old_open = Path.open
    attempts = []

    def guard(path, *args, **kwargs):
        if "data" in path.parts or "keys" in path.parts or "holdout-claim" in path.name:
            attempts.append(str(path))
            raise AssertionError("Forbidden dataset or holdout-claim access")
        return old_open(path, *args, **kwargs)

    def no_discovery(*args, **kwargs):
        attempts.append("discovery")
        raise AssertionError("Dataset discovery must not run while locked")

    monkeypatch.setattr(Path, "open", guard)
    monkeypatch.setattr(Path, "glob", no_discovery)
    monkeypatch.setattr(Path, "rglob", no_discovery)
    monkeypatch.setattr(sys, "argv", ["backend.eval", "run", "--split", split])
    assert main() == 2 and not attempts
    assert "DEFERRED" in capsys.readouterr().out


def test_self_check_uses_no_network_or_dataset_files(registry, monkeypatch):
    import socket

    old_open = Path.open
    attempts = []

    def blocked(*args, **kwargs):
        attempts.append("network")
        raise AssertionError("No network in harness self-check")

    def guard(path, *args, **kwargs):
        if "keys" in path.parts or "data" in path.parts:
            attempts.append("dataset")
            raise AssertionError("No dataset files in self-check")
        return old_open(path, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(Path, "open", guard)
    result = run_self_check(registry)
    assert result["checks_passed"] == 6 and not result["scanner_accuracy_measured"]
    assert not attempts


def test_scanner_import_graph_has_no_evaluation_dependency():
    forbidden = []
    for directory in ("core", "screen", "ingest"):
        for source in (ROOT / "backend" / directory).rglob("*.py"):
            tree = ast.parse(source.read_text())
            for node in ast.walk(tree):
                names = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                    if isinstance(node, ast.ImportFrom)
                    else []
                )
                forbidden.extend(name for name in names if name.startswith("backend.eval"))
    assert not forbidden


def test_cli_self_check_and_deferred_status_are_real_outputs(tmp_path):
    output, markdown = tmp_path / "checks.json", tmp_path / "status.md"
    check = subprocess.run(
        [sys.executable, "-m", "backend.eval", "self-check", "--output", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert check.returncode == 0
    payload = json.loads(output.read_text())
    assert payload["kind"] == "harness_self_check" and not payload["sponsor_files_accessed"]
    assert output.stat().st_mode & 0o777 == 0o600
    status = subprocess.run(
        [
            sys.executable,
            "-m",
            "backend.eval",
            "status",
            "--report",
            str(markdown),
            "--archive-root",
            str(tmp_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert status.returncode == 0
    assert json.loads(status.stdout)["state"] == "deferred"
    assert markdown.read_text() == deferred_report() and "NOT PERFORMED" in markdown.read_text()
