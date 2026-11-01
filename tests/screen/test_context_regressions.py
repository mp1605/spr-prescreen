"""Acronym and byline boundary contracts; not additional research-paper examples."""

import pytest

from backend.core.screen import screen_document


@pytest.mark.parametrize("text", ["(TS)", "(TS//NF)", "Top Secret (TS)"])
def test_real_markings_survive_acronym_guard(text, registry, atom_document):
    result = screen_document(atom_document(text), registry)
    assert any("L1-1" in finding.items for finding in result.findings)


def test_explicit_ordinary_acronym_does_not_become_a_classification(registry, atom_document):
    result = screen_document(atom_document("Training Simulator (TS)"), registry)
    assert not any("L1-1" in finding.items for finding in result.findings)


def test_author_affiliation_is_not_rejected_as_a_long_personal_name(registry, atom_document):
    result = screen_document(
        atom_document(
            "Brig Gen Example A. Name, Commander, Example Training Wing (fictional author)"
        ),
        registry,
    )
    assert any("L2-24" in finding.items for finding in result.findings)


def test_comma_in_prose_does_not_convert_a_rank_mention_into_an_author(registry, atom_document):
    result = screen_document(
        atom_document("The briefing mentioned Brig Gen Example Name, who attended."), registry
    )
    assert not any("L2-24" in finding.items for finding in result.findings)
