import hashlib
import json
from pathlib import Path

import pytest

from backend.core.ingest import DocumentInput, parse_document, parse_many
from backend.core.ingest_models import IngestLimits


def test_hash_identity_is_independent_of_filename(guide_pdf, guide_docx):
    a = parse_document("same.pdf", guide_pdf)
    b = parse_document("same.pdf", guide_docx)
    c = parse_document("renamed.pdf", guide_pdf)
    assert a.paper_id != b.paper_id
    assert a.paper_id == c.paper_id
    assert b.status == "incomplete"  # A DOCX disguised as a PDF cannot be called complete.


def test_cache_hit_preserves_evidence_and_current_filename(guide_pdf, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    first = parse_document("before.pdf", guide_pdf, cache_directory=cache)
    assert first.cache_state == "miss"

    def should_not_parse(*args, **kwargs):
        raise AssertionError("Valid cache hit must not reparse")

    monkeypatch.setattr("backend.core.ingest.parse_pdf", should_not_parse)
    second = parse_document("after.pdf", guide_pdf, cache_directory=cache)
    assert second.cache_state == "hit" and second.file_name == "after.pdf"
    assert second.segments == first.segments and second.units == first.units
    assert next(cache.glob("*.json")).stat().st_mode & 0o777 == 0o600


def test_corrupt_cache_reparsed_and_limits_have_distinct_keys(guide_pdf, tmp_path):
    first = parse_document("guide.pdf", guide_pdf, cache_directory=tmp_path)
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text())
    data["result"]["units"][0]["text"] += " "
    path.write_text(json.dumps(data))
    second = parse_document("guide.pdf", guide_pdf, cache_directory=tmp_path)
    assert second.cache_state == "miss" and second.units == first.units
    third = parse_document(
        "guide.pdf", guide_pdf, cache_directory=tmp_path, limits=IngestLimits(max_pages=1)
    )
    assert third.cache_state == "miss" and third.status == "incomplete"
    assert len(list(tmp_path.glob("*.json"))) == 2
    assert not list(tmp_path.glob("*.tmp"))


def test_unavailable_cache_does_not_discard_fresh_evidence(guide_pdf, tmp_path):
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("")
    result = parse_document("guide.pdf", guide_pdf, cache_directory=blocked)
    assert result.status == "complete" and result.cache_state == "unavailable"


def test_parser_version_change_does_not_reuse_v1_cache(guide_pdf, tmp_path):
    first = parse_document("guide.pdf", guide_pdf, cache_directory=tmp_path)
    path = next(tmp_path.glob("*.json"))
    assert ".v3." in path.name and first.parser_version == "3"
    path.rename(path.with_name(path.name.replace(".v3.", ".v1.")))
    second = parse_document("guide.pdf", guide_pdf, cache_directory=tmp_path)
    assert second.cache_state == "miss"
    assert len(list(tmp_path.glob("*.json"))) == 2


@pytest.mark.parametrize("workers", [1, 2])
def test_batch_continues_after_corrupt_input(guide_pdf, guide_docx, workers, tmp_path):
    inputs = [
        DocumentInput("first.pdf", guide_pdf),
        DocumentInput("corrupt.docx", b""),
        DocumentInput("last.docx", guide_docx),
    ]
    results = parse_many(inputs, cache_directory=tmp_path, workers=workers)
    assert [r.status for r in results] == ["complete", "incomplete", "complete"]
    assert results[1].review_color == "yellow"
    assert [r.file_name for r in results] == [d.file_name for d in inputs]


def test_type_size_and_batch_limits(guide_pdf):
    unsupported = parse_document("guide.txt", guide_pdf)
    oversized = parse_document("guide.pdf", guide_pdf, limits=IngestLimits(max_file_bytes=1))
    assert unsupported.status == oversized.status == "rejected"
    assert oversized.paper_id == "sha256:" + hashlib.sha256(guide_pdf).hexdigest()
    with pytest.raises(ValueError, match="file-count"):
        parse_many(
            [DocumentInput("one.pdf", b""), DocumentInput("two.pdf", b"")],
            limits=IngestLimits(max_batch_files=1),
        )
    with pytest.raises(ValueError, match="workers"):
        parse_many([], workers=0)


def test_ingestion_opens_no_evaluation_paths(guide_pdf, guide_docx, tmp_path, monkeypatch):
    original = Path.open
    forbidden_accesses = []

    def guard(path, *args, **kwargs):
        if "keys" in path.parts or path.name.casefold().endswith("_key.docx"):
            forbidden_accesses.append(path)
            raise AssertionError("Evaluation source access is forbidden")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guard)
    results = parse_many(
        [DocumentInput("guide.pdf", guide_pdf), DocumentInput("guide.docx", guide_docx)],
        cache_directory=tmp_path / "cache",
        workers=1,
    )
    assert all(r.status == "complete" for r in results)
    assert not forbidden_accesses


def test_parse_errors_do_not_log_document_text(capsys):
    result = parse_document("corrupt.pdf", b"%PDF-1.7\nDo not print document content")
    assert result.status == "incomplete"
    capture = capsys.readouterr()
    assert "Do not print document content" not in capture.out + capture.err
