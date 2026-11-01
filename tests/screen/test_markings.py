import pytest

from backend.core.engines.rules import RulesEngine
from backend.core.screen import screen_document


@pytest.mark.parametrize(
    "marking",
    [
        "(C)",
        "(S)",
        "(TS)",
        "(CUI)",
        "(S//NF/PROPIN)",
        "(C//FRD)",
        "(//GBR S)",
        "(TS//SI/TK)",
        "(S//RD)",
        "(S//REL)",
        "(TS//REL TO USA, AUS, CAN, GBR)",
        "(S//RD-N)",
    ],
)
def test_official_markings_at_paragraph_start_are_red(marking, registry, atom_document):
    document = atom_document(marking)
    result = screen_document(document, registry)
    assert result.color == "red"
    assert result.findings[0].items == ("L1-1",)
    assert result.findings[0].quote == marking
    assert result.trace == ("list1:done", "list2:done")


@pytest.mark.parametrize(
    "letters", [("(A)", "(B)", "(C)"), ("(R)", "(S)", "(T)"), ("(a)", "(b)", "(c)")]
)
def test_lettered_paragraph_sequences_are_not_classification(letters, registry, atom_document):
    result = screen_document(atom_document(*letters), registry)
    assert result.color == "green" and result.flag_count.total == 0


@pytest.mark.parametrize(
    "text", ["(A), (B), (C)", "(a)(b)(c)", "List 2 (C)", "List 2 (S)", "(c)", "(s)"]
)
def test_nonmarking_letter_formats_do_not_trigger_list1(text, registry, atom_document):
    result = screen_document(atom_document(text), registry)
    assert not any(f.list == "list1" for f in result.findings)


def test_adjacent_markings_remain_indicators_inside_a_paragraph(registry, atom_document):
    result = screen_document(atom_document("List 2 (C) (S) (TS)"), registry)
    assert any(f.items == ("L1-1",) for f in result.findings)


@pytest.mark.parametrize(
    "banner", ["TOP SECRET", "SECRET", "CONFIDENTIAL", "CUI", "FOR OFFICIAL USE ONLY"]
)
def test_uppercase_control_labels_are_indicators(banner, registry, atom_document):
    result = screen_document(atom_document(banner), registry)
    assert result.color == "red" and result.findings[0].items == ("L1-1",)


def test_unicode_normalization_keeps_exact_source_evidence(registry, atom_document):
    source = "(\u200bCUI\u200b) F\u201135A"
    document = atom_document(source)
    engine = RulesEngine(registry)
    hits = engine.run(document, "list1", registry.list1)
    assert source[hits[0].char_start : hits[0].char_end] == "(\u200bCUI\u200b)"
    result = screen_document(document, registry, engine=engine)
    assert result.color == "red" and result.flag_count.total == 2
    assert all(f.quote == source for f in result.findings)
    assert {i for f in result.findings for i in f.items} >= {"L1-1", "L2-06"}
