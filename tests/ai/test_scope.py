"""Review scope is literal source coverage, not a change to baseline policy screening."""

import json

from backend.core.engines.ai import AIEngine
from backend.core.screen import screen_document
from tests.ai.conftest import ContractProvider, proposal


def test_full_and_selective_submit_different_source_but_preserve_baseline(
    registry, assessor, atom_document, ai_settings
):
    document = atom_document("List 1", "Context", "Animal testing", "Details", "Appendix")
    baseline = screen_document(document, registry, specificity=assessor)
    for scope, expected in [("full", 5), ("selective", 3)]:
        provider = ContractProvider([])
        settings = ai_settings.model_copy(update={"scope": scope})
        result = screen_document(
            document, registry, specificity=assessor, ai=AIEngine(settings, provider).session()
        )
        assert result.ai_state == "ran" and result.ai.generation_attempted
        data = json.loads(provider.calls[0]["messages"][1]["content"])
        assert len(data["source_segments"]) == expected
        assert result.ai.source_segments == expected and result.ai.total_source_segments == 5
        assert result.ai.scope == scope and data["review_scope"] == scope
        assert result.findings == baseline.findings and result.trace == baseline.trace
        if scope == "selective":
            assert [s["text"] for s in data["source_segments"]] == [
                "Context",
                "Animal testing",
                "Details",
            ]


def test_selective_does_not_accept_quotes_from_unsent_source(
    registry, assessor, atom_document, ai_settings
):
    document = atom_document("List 1", "Context", "Animal testing", "Details", "Appendix")
    provider = ContractProvider([proposal("Appendix", "L2-02")])
    result = screen_document(
        document,
        registry,
        specificity=assessor,
        ai=AIEngine(ai_settings.model_copy(update={"scope": "selective"}), provider).session(),
    )
    assert result.ai.accepted == 0 and result.ai.rejected == 1
    assert "unbound_or_ambiguous_quote" in result.ai.issue_codes
    assert all("L2-02" not in f.items for f in result.findings)


def test_selective_without_candidates_skips_generation_and_records_coverage(
    registry, assessor, atom_document, ai_settings
):
    provider = ContractProvider(error=True)
    result = screen_document(
        atom_document("List 1"),
        registry,
        specificity=assessor,
        ai=AIEngine(ai_settings.model_copy(update={"scope": "selective"}), provider).session(),
    )
    assert result.ai_state == result.ai.state == "skipped"
    assert result.ai.source_segments == 0 and result.ai.total_source_segments == 1
    assert not result.ai.generation_attempted and not provider.calls
    assert result.color == "green" and not result.incomplete_reasons
    assert result.release_decision == "NOT_MADE_BY_TOOL"


def test_context_does_not_cross_section_boundaries(registry, assessor, atom_document, ai_settings):
    document = atom_document("First", "Animal testing", "Last", headings=["A", "B", "C"])
    provider = ContractProvider()
    result = screen_document(
        document,
        registry,
        specificity=assessor,
        ai=AIEngine(ai_settings.model_copy(update={"scope": "selective"}), provider).session(),
    )
    assert result.ai.source_segments == 1
    assert result.ai.source_segment_ids == (document.segments[1].segment_id,)


def test_full_budget_failure_is_not_relabelled_as_a_selective_review(
    registry, assessor, atom_document, ai_settings
):
    document = atom_document(
        "List 1", "Context", "Animal testing", "Details", "Appendix", "z" * 40000
    )
    provider = ContractProvider()
    full = screen_document(
        document, registry, specificity=assessor, ai=AIEngine(ai_settings, provider).session()
    )
    assert full.ai_state == "error" and "context_budget" in full.ai.issue_codes
    assert full.ai.scope == "full" and not full.ai.generation_attempted and not provider.calls
    selective = screen_document(
        document,
        registry,
        specificity=assessor,
        ai=AIEngine(ai_settings.model_copy(update={"scope": "selective"}), provider).session(),
    )
    assert selective.ai_state == "ran" and selective.ai.source_segments == 3
