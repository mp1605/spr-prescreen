from datetime import date

import pytest

from backend.core.engines.context import SourceContext


@pytest.mark.parametrize(
    "text,kind",
    [
        ("3 aircraft", "quantity"),
        ("zero personnel", "quantity"),
        ("1,250 personnel", "quantity"),
        ("3 assigned F-22", "quantity"),
        ("7th Wing", "unit"),
        ("F—22", "system"),
        ("F-\n22", "system"),
        ("Project Alpha", "program"),
        ("2 km", "measurement"),
        ("Washington D.C.", "location"),
        ("January 2040", "future_date"),
        ("May 2040", "future_date"),
        ("2040-01-01", "date"),
        ("will deploy in May", "future_date"),
        ("no coordination documented", "coordination_gap"),
        ("U.S. Army", "actor"),
        ("ordered by the President", "authority_action"),
        ("ITAR", "control"),
    ],
)
def test_literal_features_preserve_exact_source_offsets(text, kind, facts):
    values = facts(text)
    assert any(value.kind == kind for value in values)
    for value in values:
        assert text[value.char_start : value.char_end] == value.text


@pytest.mark.parametrize(
    "text", ["Table 3 aircraft", "2024 aircraft", "https://example.invalid/3 aircraft"]
)
def test_years_labels_and_links_are_not_asset_counts(text, facts):
    assert not any(value.kind == "quantity" for value in facts(text))


def test_explicit_large_count_is_retained_and_readiness_negation_is_not_disclosure_negation(facts):
    assert any(value.kind == "quantity" for value in facts("only 2024 aircraft"))
    assert not any(value.kind == "negation" for value in facts("not mission capable"))
    assert any(value.kind == "negation" for value in facts("does not disclose"))
    assert not any(value.kind == "uncertainty" for value in facts("May 2040"))


def test_future_is_reproducible_and_invalid_dates_do_not_promote(facts):
    text = "January 2040"
    assert any(value.kind == "future_date" for value in facts(text, date(2039, 1, 1)))
    assert not any(value.kind == "future_date" for value in facts(text, date(2041, 1, 1)))
    assert not any(value.kind in {"date", "future_date"} for value in facts("February 31, 2040"))


def test_rank_requires_real_byline_context(facts):
    assert any(value.kind == "rank" for value in facts("By O-7 Author"))
    assert not any(value.kind == "rank" for value in facts("The discussion mentions O-7 roles."))


def test_feature_work_is_bounded(assessor, atom_document):
    text = "F-22 " * 10_001
    document = atom_document(text)
    with pytest.raises(ValueError, match="resource limit"):
        assessor.features(
            document.units[0], 0, len(text), as_of=date(2030, 1, 1), context=SourceContext(document)
        )


def test_article_is_not_a_named_program(facts):
    assert not any(value.kind == "program" for value in facts("Program A review"))


@pytest.mark.parametrize("kind,expected", [("location", 1), ("actor", 0)])
def test_optional_entities_are_source_bound_and_organizations_are_not_dod_evidence(
    kind, expected, registry
):
    from backend.core.named_entities import NamedEntity
    from backend.core.specificity import SpecificityEngine
    from tests.conftest import ROOT

    class Provider:
        identity = "a" * 64

        def entities(self, text):
            return (NamedEntity(0, len(text), kind),)

    model = SpecificityEngine(ROOT, registry, entities=Provider())
    result = model.named("Washington D.C.")
    assert len(result) == expected and model.ner_state == "ready"
    assert all(f.text == "Washington D.C." and f.source == "local_ner" for f in result)


def test_invalid_entity_coordinates_disable_optional_model(registry):
    from backend.core.named_entities import NamedEntity
    from backend.core.specificity import SpecificityEngine
    from tests.conftest import ROOT

    class Provider:
        identity = "a" * 64

        def entities(self, text):
            return (NamedEntity(0, len(text) + 1, "location"),)

    model = SpecificityEngine(ROOT, registry, entities=Provider())
    assert model.named("Washington D.C.") == () and model.ner_state == "unavailable"
