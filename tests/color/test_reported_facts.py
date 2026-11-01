"""Distinguish measured capability from hypothetical conditions without weakening either."""


def test_measured_capability_is_not_hypothetical_due_to_could(facts):
    measured = facts("The exercise measured that operations could resume in 8 hours.")
    assert any(f.kind == "measurement" for f in measured)
    assert not any(f.kind == "uncertainty" for f in measured)
    hypothetical = facts("In a hypothetical exercise operations could resume in 8 hours.")
    assert any(f.kind == "uncertainty" for f in hypothetical)


def test_named_unit_and_plural_designator_retain_literal_evidence(facts):
    features = facts("Example Fighter Squadron has 21 assigned F-22s.")
    assert any(f.kind == "unit" and f.text == "Example Fighter Squadron" for f in features)
    assert any(f.kind == "system" and f.text == "F-22s" for f in features)


def test_numbered_fictional_source_is_excluded_without_changing_real_references(atom_document):
    from backend.core.text_segments import excluded_noise

    source = "[12] Fictional source: readiness index."
    spans = excluded_noise(source)
    assert len(spans) == 1 and source[spans[0].char_start : spans[0].char_end] == source
    assert not excluded_noise("[12] Real published source: readiness index.")
