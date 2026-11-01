import pytest

from backend.cli_io import write_report
from backend.eval.archive import archived_report
from backend.eval.contracts import metric_contract
from backend.eval.dataset import canonical_files
from backend.eval.frozen import verify_frozen_scanner
from backend.eval.score import score_cases
from backend.eval.split import case_ids


def contract_archive(root, registry, split="dev"):
    """Numeric/schema objects with official text; no scanner execution or paper corpus."""
    gold, prediction = metric_contract(registry)
    ids = case_ids(split)
    report = score_cases(
        tuple(gold.model_copy(update={"case_id": ident}) for ident in ids),
        tuple(prediction.model_copy(update={"case_id": ident}) for ident in ids),
        kind="sponsor_evaluation",
    )
    folder = root / "reports/evaluation"
    write_report(
        folder / "authorization.json", {"no_tuning": True, "scanner_fingerprint": "a" * 64}
    )
    write_report(folder / f"{split}.json", report.model_dump(mode="json"))
    return folder, report


def test_empty_archive_does_not_discover_any_dataset(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Empty archive must not read dataset content")

    monkeypatch.setattr(type(tmp_path), "read_text", forbidden)
    assert archived_report(tmp_path, "dev") is None


def test_development_endpoint_keeps_tuned_results_separate_from_frozen_scorecard(
    client, project_root, registry
):
    assert client.get("/api/evaluation/development/latest").status_code == 404
    _, report = contract_archive(project_root, registry)
    write_report(project_root / "reports/m13/final-dev.json", report.model_dump(mode="json"))
    data = client.get("/api/evaluation/development/latest").json()
    assert data["tuned_on_this_split"] and not data["unseen_validation"]
    assert not data["holdout_reused"] and data["report"]["paper_count"] == 60
    bad = report.model_copy(update={"paper_count": 20})
    write_report(project_root / "reports/m13/final-dev.json", bad.model_dump(mode="json"))
    assert client.get("/api/evaluation/development/latest").status_code == 503


def test_complete_contract_archive_round_trips_and_api_exposes_it(client, project_root, registry):
    _, report = contract_archive(project_root, registry)
    assert archived_report(project_root, "dev") == report
    data = client.get("/api/evaluation/scorecard/dev").json()
    assert data["state"] == "complete" and data["sponsor_accuracy_measured"]
    assert data["report"]["paper_count"] == 60


def test_holdout_archive_requires_finished_matching_claim(tmp_path, registry):
    folder, report = contract_archive(tmp_path, registry, "holdout")
    write_report(folder / "holdout-claim.json", {"status": "started", "fingerprint": "a" * 64})
    assert archived_report(tmp_path, "holdout") is None
    write_report(folder / "holdout-claim.json", {"status": "complete", "fingerprint": "b" * 64})
    with pytest.raises(ValueError, match="fingerprints"):
        archived_report(tmp_path, "holdout")
    write_report(folder / "holdout-claim.json", {"status": "complete", "fingerprint": "a" * 64})
    assert archived_report(tmp_path, "holdout") == report


def test_invalid_or_wrong_split_artifact_is_not_published(client, project_root, registry):
    folder, report = contract_archive(project_root, registry)
    write_report(
        folder / "dev.json", report.model_copy(update={"paper_count": 1}).model_dump(mode="json")
    )
    assert client.get("/api/evaluation/scorecard/dev").status_code == 503
    (folder / "dev.json").write_text("{broken")
    assert client.get("/api/evaluation/scorecard/dev").status_code == 503


def test_inventory_requires_exact_case_set_and_ignores_suffixed_duplicates(tmp_path):
    with pytest.raises(ValueError):
        canonical_files(tmp_path, keys=True)
    for ident in (*case_ids("dev"), *case_ids("holdout")):
        (tmp_path / f"{ident}_KEY.docx").touch()
    (tmp_path / "SPR-Test-073_KEY(1).docx").touch()
    assert len(canonical_files(tmp_path, keys=True)) == 80
    (tmp_path / "SPR-Test-073_KEY.pdf").touch()
    with pytest.raises(ValueError, match="Duplicate"):
        canonical_files(tmp_path, keys=True)


def test_freeze_refuses_scanner_change_but_allows_eval_harness_change(tmp_path):
    import hashlib

    records = []
    for n in range(50):
        name = f"backend/core/format{n}.py"
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# mechanical freeze contract\n")
        records.append({"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_report(tmp_path / "reports/M11-build-manifest.json", {"files": records})
    first = verify_frozen_scanner(tmp_path)
    (tmp_path / "evaluation-only.txt").write_text("No detector change")
    assert verify_frozen_scanner(tmp_path) == first
    (tmp_path / records[0]["path"]).write_text("# changed")
    with pytest.raises(ValueError, match="changed"):
        verify_frozen_scanner(tmp_path)
