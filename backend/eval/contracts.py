"""In-memory format/math contracts made from official wording, never a paper corpus."""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import cast

import pymupdf  # type: ignore[import-untyped]
from docx import Document

from backend.core.models import Finding, FlagCount, Location, PaperResult
from backend.core.rules_loader import RuleRegistry
from backend.eval.models import GoldCase, GoldTrigger, PredictionCase


def docx_format_contract(registry: RuleRegistry) -> bytes:
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run(registry.list2[0].text).bold = True
    paragraph.add_run(" ")
    paragraph.add_run("[T1]").font.superscript = True
    document.add_heading("ANSWER KEY", 1)
    document.add_paragraph("Expected tool result: YELLOW")
    table = document.add_table(rows=2, cols=4)
    for cell, text in zip(
        table.rows[0].cells, ("Tag", "Rule violated", "Flag", "Why it triggers"), strict=True
    ):
        cell.text = text
    for cell, text in zip(
        table.rows[1].cells, ("T1", "L2-01", "Yellow", "Format contract"), strict=True
    ):
        cell.text = text
    document.add_paragraph(f'Decoy (not a trigger): "{registry.list2[1].text}"')
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def pdf_format_contract(registry: RuleRegistry) -> bytes:
    # This single-page artifact tests formatting only. It is never screened, saved as a
    # development paper, or used as an exemplar.
    document = pymupdf.open()
    try:
        page = document.new_page()
        text = registry.list2[0].text
        page.insert_text((50, 60), text, fontname="hebo", fontsize=11)
        width = pymupdf.get_text_length(text, fontname="hebo", fontsize=11)
        page.insert_text((56 + width, 56), "[T1]", fontsize=7)
        page.insert_text((50, 120), "ANSWER KEY", fontname="hebo", fontsize=14)
        page.insert_text((50, 145), "Expected tool result: YELLOW", fontsize=10)
        page.insert_text(
            (50, 165), f'Decoy (not a trigger): "{registry.list2[1].text}"', fontsize=10
        )
        columns = (50, 100, 250, 315, 545)
        for x in columns:
            page.draw_line((x, 190), (x, 260))
        for y in (190, 220, 260):
            page.draw_line((50, y), (545, y))
        for row, values in enumerate(
            (
                ("Tag", "Rule violated", "Flag", "Why it triggers"),
                ("T1", "L2-01", "Yellow", "Format contract"),
            )
        ):
            for x, value in zip(columns, values, strict=False):
                page.insert_text((x + 5, 208 + row * 30), value, fontsize=9)
        return cast(bytes, document.tobytes())
    finally:
        document.close()


def metric_contract(registry: RuleRegistry) -> tuple[GoldCase, PredictionCase]:
    quote = registry.list2[0].text
    paper_id = "sha256:" + hashlib.sha256(quote.encode()).hexdigest()
    finding = Finding(
        finding_id="format-contract-finding",
        paper_id=paper_id,
        list="list2",
        items=("L2-01",),
        color="yellow",
        quote=quote,
        location=Location(paragraph=1, char_start=0, char_end=len(quote)),
        reason="Format contract",
        why_unsure="Contract object; not a scanner prediction",
        engines=("rules",),
    )
    result = PaperResult(
        paper_id=paper_id,
        file_name="format-contract.docx",
        file_type="docx",
        color="yellow",
        label="Potential flag",
        flag_count=FlagCount(total=1, red=0, yellow=1),
        lists_checked=("list1", "list2"),
        trace=("list1:done", "list2:done"),
        ai_state="off",
        rules_version=registry.policy_version,
        seconds=0,
        findings=(finding,),
    )
    gold = GoldCase(
        case_id="format-contract",
        expected_color="yellow",
        paper_id=paper_id,
        triggers=(
            GoldTrigger(
                tag="T1", quote=quote, items=("L2-01",), color="yellow", reason="Format contract"
            ),
        ),
    )
    return gold, PredictionCase(case_id=gold.case_id, result=result)
