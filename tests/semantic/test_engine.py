import hashlib
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from pydantic import ValidationError

from backend.core.engines.base import Hit
from backend.core.engines.semantic import SemanticEngine
from backend.core.engines.vector_cache import VectorCache, normalized
from backend.core.screen import screen_document
from backend.core.semantic_models import SemanticMatch


def test_one_document_pass_both_lists_and_top_references(host, registry, atom_document):
    document = atom_document(registry.list1[1].text, registry.list2[0].text)
    session = host.session()
    one = session.run(document, "list1", registry.list1)
    two = session.run(document, "list2", registry.list2)
    assert len(host.provider.calls) == 2  # One official bank, one complete paper batch.
    assert one[0].item_id == "L1-3" and two[0].item_id == "L2-01"
    assert all(hit.reference.source == "official_rule" and hit.score == 1 for hit in one + two)
    assert session.info().segments == session.info().chunks == 2
    assert session.info().reference_count == 39 and not session.info().calibrated


@pytest.mark.parametrize(
    "score,expected", [(0.49, None), (0.50, "possible"), (0.74, "possible"), (0.75, "high")]
)
def test_cosine_bands_and_boundaries(score, expected, host, registry, atom_document):
    host.settings = host.settings.model_copy(update={"mid_threshold": 0.5, "high_threshold": 0.75})
    vector = np.zeros((1, 384), dtype=np.float32)
    vector[0, 8] = score
    vector[0, 383] = (1 - score**2) ** 0.5
    host.provider.paper_vectors = vector
    hits = host.session().run(atom_document(registry.list2[0].text), "list2", registry.list2)
    if expected is None:
        assert not hits
    else:
        assert hits[0].reference.band == expected
        assert hits[0].score == pytest.approx(score)


def test_negative_cosine_is_not_rounded_up_to_a_zero_threshold(host, registry, atom_document):
    host.settings = host.settings.model_copy(update={"mid_threshold": 0.0})
    vector = np.zeros((1, 384), dtype=np.float32)
    vector[0, 8], vector[0, 383] = -0.6, 0.8
    host.provider.paper_vectors = vector
    hits = host.session().run(atom_document(registry.list2[0].text), "list2", registry.list2)
    assert "L2-01" not in {hit.item_id for hit in hits}


def test_e1_is_preserved_and_source_is_immutable(host, registry, atom_document):
    document = atom_document("(CUI)", registry.list2[0].text)
    before = document.model_dump_json()
    baseline = screen_document(document, registry)
    result = screen_document(document, registry, semantic=host.session())
    assert result.trace == ("list1:done", "list2:done")
    assert result.color == "red" and result.semantic.state == "complete"
    for raw in baseline.findings:
        matching = next(f for f in result.findings if f.list == raw.list and f.quote == raw.quote)
        assert set(raw.items) <= set(matching.items)
        assert raw.location == matching.location and raw.color == matching.color
    assert result.findings[-1].engines == ("rules", "semantic")
    assert result.findings[-1].nearest_exemplar is None
    assert document.model_dump_json() == before
    assert baseline.screening_stage == "rules_only" and result.screening_stage == "rules_semantic"


def test_failed_semantics_still_runs_rules_on_both_lists_and_is_never_green(
    host, registry, atom_document, capsys
):
    host.provider.failure = True
    result = screen_document(
        atom_document("(CUI)", registry.list2[0].text), registry, semantic=host.session()
    )
    assert result.flag_count.red and result.flag_count.yellow
    assert result.trace == ("list1:error", "list2:error")
    assert result.semantic.state == "error" and result.incomplete_reasons
    result = screen_document(atom_document("List 1"), registry, semantic=host.session())
    assert result.color == "yellow" and result.label == "Incomplete"
    assert "PRIVATE SOURCE" not in capsys.readouterr().out


@pytest.mark.parametrize("kind", ["zero", "nan", "wrong_shape"])
def test_invalid_model_vectors_cannot_become_findings(kind, host, registry, atom_document):
    values = np.zeros((1, 383 if kind == "wrong_shape" else 384), dtype=np.float32)
    if kind == "nan":
        values[0, 0] = np.nan
    host.provider.paper_vectors = values
    result = screen_document(atom_document("List 1"), registry, semantic=host.session())
    assert result.color == "yellow" and result.semantic.state == "error"


def test_session_rejects_a_different_source_even_if_hash_is_reused(host, registry, atom_document):
    document = atom_document(registry.list2[0].text)
    other = atom_document(registry.list2[1].text).model_copy(update={"paper_id": document.paper_id})
    session = host.session()
    session.run(document, "list1", registry.list1)
    with pytest.raises(ValueError, match="reused"):
        session.run(other, "list2", registry.list2)


def test_cache_reuse_and_tamper_recomputation(host, registry, atom_document):
    document = atom_document(registry.list2[0].text)
    first = screen_document(document, registry, semantic=host.session())
    second = screen_document(document, registry, semantic=host.session())
    assert second.semantic.cache_state == "hit"
    assert first.findings == second.findings and len(host.provider.calls) == 2
    for path in host.cache.directory.glob("*.vectors"):
        assert path.stat().st_mode & 0o777 == 0o600
        path.write_bytes(b"invalid cache")
    fresh = SemanticEngine(host.root, registry, host.settings, provider=host.provider)
    third = screen_document(document, registry, semantic=fresh.session())
    assert third.findings == first.findings and third.semantic.cache_state == "miss"
    assert len(host.provider.calls) == 4


def test_cache_key_changes_with_model_and_source(host, registry, atom_document):
    document = atom_document(registry.list2[0].text)
    screen_document(document, registry, semantic=host.session())
    host.provider.identity = "b" * 64
    fresh = SemanticEngine(host.root, registry, host.settings, provider=host.provider)
    result = screen_document(document, registry, semantic=fresh.session())
    assert result.semantic.cache_state == "miss" and len(host.provider.calls) == 4


def test_concurrent_sessions_do_not_mix_papers(host, registry, atom_document):
    documents = [atom_document(item.text) for item in registry.list2[:4]]
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = tuple(
            workers.map(
                lambda doc: screen_document(doc, registry, semantic=host.session()), documents
            )
        )
    for document, result, item in zip(documents, results, registry.list2[:4], strict=True):
        assert result.paper_id == document.paper_id
        assert any(
            item.id in finding.items and finding.quote == item.text for finding in result.findings
        )
    assert len(host.provider.calls) == 5


def test_cache_checks_bounds_hash_and_normalization(tmp_path):
    cache = VectorCache(tmp_path)
    key = hashlib.sha256(b"numerical contract").hexdigest()
    values = normalized(np.ones((2, 384), dtype=np.float32), 2)
    assert cache.write(key, values)
    assert cache.read(key, 3) is None
    path = tmp_path / f"{key}.vectors"
    path.write_bytes(path.read_bytes()[:-1] + b"X")
    assert cache.read(key, 2) is None
    with pytest.raises(ValueError):
        cache.write("../escape", values)


def test_cache_preserves_exact_float32_values(tmp_path):
    cache = VectorCache(tmp_path)
    values = normalized(np.random.default_rng(41).normal(size=(5, 384)).astype(np.float32), 5)
    key = "c" * 64
    assert cache.write(key, values)
    assert np.array_equal(values, cache.read(key, 5))


def test_semantic_hit_cannot_invent_item_or_reference():
    with pytest.raises(ValidationError):
        SemanticMatch(item_id="L1-2", text="List 1", score=1, band="high")
    with pytest.raises(ValidationError):
        Hit(
            segment_id="s1",
            item_id="L2-01",
            list="list2",
            detector="semantic",
            engine="semantic",
            char_start=0,
            char_end=1,
        )


def test_e1_failure_does_not_skip_e2_or_the_next_list(host, registry, atom_document):
    class BrokenRules:
        rules_version = registry.policy_version
        calls = []

        def run(self, document, list_name, items):
            self.calls.append(list_name)
            raise ValueError("Rule engine failure")

    engine = BrokenRules()
    result = screen_document(
        atom_document(registry.list2[0].text), registry, engine=engine, semantic=host.session()
    )
    assert engine.calls == ["list1", "list2"]
    assert result.trace == ("list1:error", "list2:error")
    assert result.semantic.state == "complete" and result.findings[0].engines == ("semantic",)
    assert result.color == "yellow" and result.incomplete_reasons
