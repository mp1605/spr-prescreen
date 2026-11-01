import time

import pytest

from backend.core.ai_models import AIProposal
from backend.core.ai_quotes import verify_quote
from tests.ai.conftest import proposal


@pytest.mark.parametrize(
    "source,quote,kind",
    [
        ("Animal testing", "Animal testing", "exact"),
        ("Animal\u00a0testing", "Animal testing", "normalized"),
        ("F–22 and F–35", "F-22 and F-35", "normalized"),
        (
            "Animal testing and directed energy and cyber research",
            "Animal testing and directed energy and cyber researsh",
            "fuzzy",
        ),
    ],
)
def test_bound_quotes_keep_exact_original_offsets(source, quote, kind, atom_document):
    document = atom_document(source)
    result = verify_quote(AIProposal(**proposal(quote)), document, time.monotonic() + 2)
    assert result and result.evidence.match == kind
    evidence = result.evidence
    assert source[evidence.char_start : evidence.char_end] == evidence.quote


@pytest.mark.parametrize(
    "texts,quote",
    [
        (("Animal testing", "Animal testing"), "Animal testing"),
        (("Animal testing Animal testing",), "Animal testing"),
        (("Animal testing. Directed energy.",), "Animal testing. Directed energy."),
        (("Animal testing",), "Animal tesing"),
        (
            ("F-22 · 3 aircraft · 7th Wing · readiness information for operations",),
            "F-22 · 8 aircraft · 7th Wing · readiness information for operations",
        ),
        (
            ("AI-GENERATED FAKE CONTENT FOR EDUCATIONAL PURPOSES ONLY\nAnimal testing",),
            "AI-GENERATED FAKE CONTENT FOR EDUCATIONAL PURPOSES ONLY",
        ),
    ],
)
def test_absent_ambiguous_or_unsafe_quotes_are_not_guessed(texts, quote, atom_document):
    assert (
        verify_quote(AIProposal(**proposal(quote)), atom_document(*texts), time.monotonic() + 2)
        is None
    )


def test_long_invented_quote_cannot_bind_just_a_short_contained_phrase(atom_document):
    quote = "Unsupported invented context preceding the words Animal testing"
    assert (
        verify_quote(
            AIProposal(**proposal(quote)), atom_document("Animal testing"), time.monotonic() + 2
        )
        is None
    )
