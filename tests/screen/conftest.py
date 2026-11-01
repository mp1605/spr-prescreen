"""Atomic format contracts and official wording; no generated or sponsor paper corpus."""

import hashlib
from pathlib import Path

import pytest

from backend.core.ingest_models import ParseResult, SourceUnit
from backend.core.rules_loader import load_rules
from backend.core.text_segments import excluded_noise, segments_for

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def registry():
    return load_rules(ROOT)


@pytest.fixture
def atom_document():
    def make(*texts, headings=None, part="word/document.xml"):
        units = tuple(
            SourceUnit(
                unit_id=n + 1,
                paragraph=n + 1,
                part=part,
                text=text,
                heading=headings[n] if headings else None,
                excluded=excluded_noise(text),
            )
            for n, text in enumerate(texts)
        )
        segments = tuple(s for unit in units for s in segments_for(unit))
        return ParseResult(
            paper_id="sha256:" + hashlib.sha256("\n".join(texts).encode()).hexdigest(),
            file_name="format-contract.docx",
            file_type="docx",
            byte_count=0,
            status="complete",
            units=units,
            segments=segments,
        )

    return make
