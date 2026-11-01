import pytest

from backend.core.engines.rules import RulesEngine
from backend.core.screen import screen_document


@pytest.mark.parametrize("index", range(31))
def test_each_list2_item_recognizes_its_official_wording(index, registry, atom_document):
    item = registry.list2[index]
    hits = RulesEngine(registry).run(atom_document(item.text), "list2", registry.list2)
    assert item.id in {hit.item_id for hit in hits}


@pytest.mark.parametrize("index", range(8))
def test_list1_official_examples_have_implemented_indicators(index, registry, atom_document):
    item = registry.list1[index]
    hits = RulesEngine(registry).run(atom_document(item.examples), "list1", registry.list1)
    assert item.id in {hit.item_id for hit in hits}


@pytest.mark.parametrize(
    "token",
    [
        "name@example.invalid",
        "123-45-6789",
        "(555) 010-0000",
        "+44 0000 000000",
        "123 Example Street",
        "my wife Example",
    ],
)
def test_pii_format_contracts_have_source_quotes(token, registry, atom_document):
    result = screen_document(atom_document(token), registry)
    assert any("L1-6" in finding.items and finding.color == "red" for finding in result.findings)
    assert all(f.quote == token for f in result.findings)


def test_multiple_pii_formats_in_one_passage_count_once(registry, atom_document):
    token = "name@example.invalid (555) 010-0000 123 Example Street"
    result = screen_document(atom_document(token), registry)
    assert result.flag_count.red == result.flag_count.total == 1
    assert result.findings[0].items == ("L1-6",)


def test_medical_terms_need_acknowledgment_context(registry, atom_document):
    generic = screen_document(atom_document("treatment"), registry)
    personal = screen_document(atom_document("treatment", headings=["Acknowledgments"]), registry)
    next_section = screen_document(
        atom_document("Acknowledgments", "treatment", headings=["Acknowledgments", "References"]),
        registry,
    )
    assert not any("L1-6" in f.items for f in generic.findings)
    assert any("L1-6" in f.items for f in personal.findings)
    assert not any("L1-6" in f.items for f in next_section.findings)


@pytest.mark.parametrize(
    "rank",
    [
        "Brigadier General",
        "Major General",
        "Lieutenant General",
        "General",
        "Rear Admiral",
        "Vice Admiral",
        "Admiral",
        "O-7",
        "O-10",
    ],
)
def test_senior_rank_in_byline_is_a_list2_candidate(rank, registry, atom_document):
    result = screen_document(atom_document(f"By {rank} Example"), registry)
    assert any("L2-24" in f.items and f.color == "yellow" for f in result.findings)


@pytest.mark.parametrize(
    "text",
    [
        "General discussion",
        "General Example discusses policy",
        "By comparison with General Example",
        "Colonel Example",
        "O-6 Example",
    ],
)
def test_prose_rank_mentions_and_lower_ranks_do_not_become_bylines(text, registry, atom_document):
    result = screen_document(atom_document(text), registry)
    assert not any("L2-24" in f.items for f in result.findings)


def test_reference_story_rank_is_not_author_metadata(registry, atom_document):
    result = screen_document(
        atom_document("By General Example", part="word/footnotes.xml"), registry
    )
    assert not any("L2-24" in f.items for f in result.findings)


def test_keyword_boundaries_and_negative_social_security_groups(registry, atom_document):
    result = screen_document(atom_document("UASuffix F-350 000-00-0000"), registry)
    assert not {"L2-04", "L2-06", "L1-6"} & {i for f in result.findings for i in f.items}


def test_coordination_candidates_require_a_service_context(registry, atom_document):
    candidate = screen_document(atom_document(registry.list2[26].text), registry)
    generic = screen_document(atom_document("no coordination documented"), registry)
    assert any("L2-27" in f.items for f in candidate.findings)
    assert not any({"L2-27", "L2-28"} & set(f.items) for f in generic.findings)
