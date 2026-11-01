"""Source-local detector guards; no case IDs, key loading, or expected-paper results."""

from backend.core.engines.context import SourceContext
from backend.core.engines.rules import RulesEngine
from scripts.accuracy_patterns import candidate


def items(doc, registry, list_name):
    rules = candidate(registry)
    return {h.item_id for h in RulesEngine(rules).run(doc, list_name, getattr(rules, list_name))}


def test_pfas_response_requires_a_real_document_topic(registry, atom_document):
    response = "The response plan calls for activated carbon filters at eleven homes."
    assert "L2-31" not in items(atom_document(response), registry, "list2")
    doc = atom_document("PFAS sampling.", "Meeting.", "Discussion.", "Next meeting.", response)
    assert "L2-31" in items(doc, registry, "list2")
    noise = atom_document("[1] Fictional source: PFAS sampling.", response)
    assert "L2-31" not in items(noise, registry, "list2")


def test_document_context_does_not_cross_parts(atom_document):
    doc = atom_document("PFAS")
    other = doc.units[0].model_copy(
        update={"unit_id": 2, "part": "word/comments.xml", "text": "response"}
    )
    doc = doc.model_copy(update={"units": (*doc.units, other)})
    assert "PFAS" not in SourceContext(doc).text(2, "document")


def test_rank_name_alone_does_not_establish_operational_personnel_data(registry, atom_document):
    name = "MSgt Jane Q. Example"
    assert "L1-3" not in items(atom_document(name), registry, "list1")
    operational = atom_document("The deployed communications team includes " + name + ".")
    assert "L1-3" in items(operational, registry, "list1")


def test_training_information_gap_is_not_an_operational_vulnerability(registry, atom_document):
    doc = atom_document("Training operations.", "The system lacks this information.")
    assert "L2-13" not in items(doc, registry, "list2")


def test_possible_designated_topic_does_not_invent_confirmed_designation(registry, atom_document):
    from backend.core.screen import screen_document
    from backend.core.specificity import SpecificityEngine
    from tests.conftest import ROOT

    rules = candidate(registry)
    result = screen_document(
        atom_document("Professional military education receives senior-leader attention."),
        rules,
        specificity=SpecificityEngine(ROOT, rules, use_local_entities=False),
    )
    flag = next(f for f in result.findings if "L2-26" in f.items)
    assert flag.color == "yellow" and "designation" in flag.why_unsure
