"""Official words and mechanical formatting/coordinate contracts only."""

import io

import pytest
from docx import Document

from backend.core.batch_models import ReviewState
from backend.core.ingest import parse_document
from backend.core.rules_loader import load_rules
from backend.core.screen import screen_document
from tests.conftest import ROOT


@pytest.fixture
def empty_review():
    return ReviewState(revision=0, decisions={}, inspected=False, events=())


def word_bytes(document):
    stream = io.BytesIO()
    document.save(stream)
    return stream.getvalue()


@pytest.fixture
def prepared():
    def make(data, format="docx"):
        parsed = parse_document("format-contract." + format, data)
        paper = screen_document(parsed, load_rules(ROOT))
        return parsed, paper

    return make


@pytest.fixture
def official_word():
    document = Document()
    document.add_paragraph("(CUI)")
    document.add_paragraph("Animal testing")
    return word_bytes(document)
