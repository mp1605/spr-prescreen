"""Evaluation math contracts are independent of scanner outputs and sponsor datasets."""

import hashlib
from pathlib import Path

import pytest

from backend.core.models import Finding, FlagCount, Location, PaperResult
from backend.core.rules_loader import load_rules
from backend.eval.models import PredictionCase

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def registry():
    return load_rules(ROOT)


@pytest.fixture
def prediction():
    def make(case_id, specs=(), *, incomplete=False, seconds=1.0, ai_state="off"):
        paper_id = "sha256:" + hashlib.sha256(case_id.encode()).hexdigest()
        findings = []
        for index, spec in enumerate(specs):
            quote, items, color, *where = spec
            paragraph = where[0] if where else index + 1
            findings.append(
                Finding(
                    finding_id=f"contract-{index}",
                    paper_id=paper_id,
                    list="list1" if items[0].startswith("L1-") else "list2",
                    items=items,
                    color=color,
                    quote=quote,
                    location=Location(paragraph=paragraph, char_start=0, char_end=len(quote)),
                    reason="Math contract",
                    why_unsure="Math contract" if color == "yellow" else None,
                    engines=("rules",),
                )
            )
        red = sum(f.color == "red" for f in findings)
        yellow = len(findings) - red
        unsure = incomplete or ai_state in ("timeout", "error")
        color = "red" if red else "yellow" if yellow or unsure else "green"
        label = (
            "Flag identified"
            if red
            else "Incomplete"
            if incomplete
            else "Potential flag"
            if color == "yellow"
            else "No flags found"
        )
        return PredictionCase(
            case_id=case_id,
            result=PaperResult(
                paper_id=paper_id,
                file_name="math-contract.docx",
                file_type="docx",
                color=color,
                label=label,
                flag_count=FlagCount(total=len(findings), red=red, yellow=yellow),
                lists_checked=("list1", "list2"),
                trace=("list1:done", "list2:done"),
                incomplete_reasons=("Format contract incomplete",) if incomplete else (),
                ai_state=ai_state,
                rules_version="contract-version",
                seconds=seconds,
                findings=findings,
            ),
        )

    return make
