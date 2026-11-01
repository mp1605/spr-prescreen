"""Format fixtures transcribe official policy text; they are not synthetic papers."""

from io import BytesIO
from pathlib import Path

import pytest
from docx import Document

from backend.core.rules_loader import load_rules

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def official_rules():
    return load_rules(ROOT)


@pytest.fixture
def guide_pdf():
    return (ROOT / "docs/official-lists.pdf").read_bytes()


@pytest.fixture
def guide_docx(official_rules):
    document = Document()
    for title, rules in (("List 1", official_rules.list1), ("List 2", official_rules.list2)):
        document.add_heading(title, 1)
        for rule in rules:
            paragraph = document.add_paragraph()
            middle = len(rule.text) // 2
            paragraph.add_run(rule.text[:middle]).bold = True
            paragraph.add_run(rule.text[middle:]).italic = True
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
