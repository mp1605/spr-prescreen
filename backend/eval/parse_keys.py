"""Strict key-format interpretation. This module never opens a key file itself."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from backend.core.rules_loader import RuleRegistry
from backend.eval.key_format import KeyBlock, KeyFormatError, KeyParagraph, KeyTable
from backend.eval.models import GoldCase
from backend.eval.read_docx import read_docx
from backend.eval.read_pdf import read_pdf
from backend.eval.rule_refs import resolve_items


def _passages(paragraph: KeyParagraph) -> dict[str, str]:
    output: dict[str, str] = {}
    if re.search(r"\[T0+\]", paragraph.text):
        raise KeyFormatError("Trigger tags must be positive integers")
    previous = 0
    for tag in re.finditer(r"\[(T[1-9]\d*)\]", paragraph.text):
        tag_runs = [r for r in paragraph.runs if r.start < tag.end() and tag.start() < r.end]
        if paragraph.superscript_required and (
            not tag_runs or not all(r.superscript for r in tag_runs)
        ):
            raise KeyFormatError("Word trigger tag is not superscript")
        selected = []
        cursor = tag.start()
        for run in reversed(paragraph.runs):
            lo, hi = max(run.start, previous), min(run.end, tag.start())
            if lo >= hi:
                continue
            if paragraph.text[hi:cursor].strip():
                break
            text = paragraph.text[lo:hi]
            if not run.bold and text.strip():
                break
            if run.bold:
                selected.append((lo, hi))
            cursor = lo
        if not selected:
            raise KeyFormatError("Trigger tag has no adjacent bold passage")
        quote = paragraph.text[min(s[0] for s in selected) : max(s[1] for s in selected)].strip()
        if tag[1] in output:
            raise KeyFormatError("Duplicate trigger tag in key body")
        output[tag[1]] = quote
        previous = tag.end()
    return output


def _answer_rows(
    table: KeyTable, registry: RuleRegistry
) -> dict[str, tuple[tuple[str, ...], str, str]]:
    output: dict[str, tuple[tuple[str, ...], str, str]] = {}
    for row in table.rows:
        if not row or not re.fullmatch(r"\s*\[?T[1-9]\d*\]?\s*", row[0]):
            continue
        if len(row) != 4:
            raise KeyFormatError(
                "Answer table requires tag, official item, color, and reason columns"
            )
        tag = row[0].strip().strip("[]")
        colors = re.findall(r"\b(red|yellow)\b", row[2], re.IGNORECASE)
        if len(colors) != 1 or not row[3].strip():
            raise KeyFormatError("Answer row has an ambiguous color or missing reason")
        if tag in output:
            raise KeyFormatError("Duplicate trigger row in answer table")
        output[tag] = (resolve_items(row[1], registry), colors[0].lower(), row[3].strip())
    return output


def parse_blocks(
    blocks: tuple[KeyBlock, ...],
    *,
    case_id: str,
    registry: RuleRegistry,
    source_sha256: str | None = None,
) -> GoldCase:
    passages: dict[str, str] = {}
    rows: dict[str, tuple[tuple[str, ...], str, str]] = {}
    answer_text: list[str] = []
    in_answers = False
    for block in blocks:
        if isinstance(block, KeyTable):
            if in_answers:
                additions = _answer_rows(block, registry)
                if rows.keys() & additions.keys():
                    raise KeyFormatError("Duplicate trigger row across answer tables")
                rows.update(additions)
            else:
                for paragraph in block.paragraphs:
                    body_passages = _passages(paragraph)
                    if passages.keys() & body_passages.keys():
                        raise KeyFormatError("Duplicate body trigger tag")
                    passages.update(body_passages)
            continue
        marker = re.search(r"\bANSWER\s+KEY\b", block.text, re.IGNORECASE)
        body_end = marker.start() if marker and not in_answers else len(block.text)
        if not in_answers:
            body = KeyParagraph(
                block.text[:body_end],
                tuple(r for r in block.runs if r.start < body_end),
                block.superscript_required,
            )
            body_passages = _passages(body)
            if passages.keys() & body_passages.keys():
                raise KeyFormatError("Duplicate body trigger tag")
            passages.update(body_passages)
        if marker:
            in_answers = True
            answer_text.append(block.text[marker.end() :])
        elif in_answers:
            answer_text.append(block.text)
    text = "\n".join(answer_text)
    expected = re.findall(
        r"Expected\s+tool\s+result\s*:\s*(RED|YELLOW|GREEN)\b", text, re.IGNORECASE
    )
    if not in_answers or len(expected) != 1:
        raise KeyFormatError("Key must have one answer section and one expected tool result")
    if passages.keys() != rows.keys():
        raise KeyFormatError("Body trigger tags and answer-table tags disagree")
    decoys = tuple(
        m[1].strip()
        for m in re.finditer(
            r'Decoy\s*\(not\s+a\s+trigger\)\s*:\s*["“](.*?)["”]',
            text,
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
    )
    if len(decoys) != len(re.findall(r"Decoy\s*\(not\s+a\s+trigger\)\s*:", text, re.IGNORECASE)):
        raise KeyFormatError("A decoy line could not be parsed unambiguously")
    try:
        return GoldCase.model_validate(
            dict(
                case_id=case_id,
                expected_color=expected[0].lower(),
                source_key_sha256=source_sha256,
                triggers=[
                    dict(tag=tag, quote=passages[tag], items=row[0], color=row[1], reason=row[2])
                    for tag, row in sorted(rows.items(), key=lambda row: int(row[0][1:]))
                ],
                decoys=decoys,
            )
        )
    except ValueError:
        raise KeyFormatError(
            "Parsed key contradicts official IDs or color/count invariants"
        ) from None


def parse_key_bytes(
    data: bytes, file_type: Literal["docx", "pdf"], *, case_id: str, registry: RuleRegistry
) -> GoldCase:
    if file_type not in ("docx", "pdf"):
        raise KeyFormatError("Key format must be DOCX or PDF")
    blocks = read_docx(data) if file_type == "docx" else read_pdf(data)
    return parse_blocks(
        blocks, case_id=case_id, registry=registry, source_sha256=hashlib.sha256(data).hexdigest()
    )
