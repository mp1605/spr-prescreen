from io import BytesIO

import pytest
from docx import Document

from backend.eval.contracts import docx_format_contract, pdf_format_contract
from backend.eval.io import gold_jsonl, parse_gold_jsonl, write_gold_jsonl
from backend.eval.key_format import KeyFormatError
from backend.eval.parse_keys import parse_key_bytes
from backend.eval.rule_refs import resolve_items


def save(document):
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.mark.parametrize("kind", ["docx", "pdf"])
def test_format_contracts_parse_bold_passages_rows_and_decoys(kind, registry):
    data = docx_format_contract(registry) if kind == "docx" else pdf_format_contract(registry)
    result = parse_key_bytes(data, kind, case_id="format-contract", registry=registry)
    assert result.expected_color == "yellow" and len(result.triggers) == 1
    assert result.triggers[0].quote == registry.list2[0].text
    assert result.triggers[0].items == ("L2-01",) and result.triggers[0].tag == "T1"
    assert result.decoys == (registry.list2[1].text,)
    assert result.source_key_sha256 and len(result.source_key_sha256) == 64


def test_multiple_and_split_run_tags_preserve_distinct_passages(registry):
    document = Document(BytesIO(docx_format_contract(registry)))
    paragraph = document.paragraphs[0]
    paragraph.runs[-1].text = "["
    for value in ("T1", "]"):
        paragraph.add_run(value).font.superscript = True
    paragraph.add_run(" ")
    paragraph.add_run(registry.list2[1].text).bold = True
    paragraph.add_run("[T2]").font.superscript = True
    row = document.tables[0].add_row()
    for cell, text in zip(
        row.cells, ("T2", "List 2 item 2", "Yellow", "Format contract"), strict=True
    ):
        cell.text = text
    result = parse_key_bytes(save(document), "docx", case_id="format-contract", registry=registry)
    assert [t.quote for t in result.triggers] == [i.text for i in registry.list2[:2]]
    assert [t.tag for t in result.triggers] == ["T1", "T2"]


def test_green_key_contract_has_no_invented_triggers(registry):
    document = Document()
    document.add_heading("ANSWER KEY", 1)
    document.add_paragraph("Expected tool result: GREEN")
    result = parse_key_bytes(
        save(document), "docx", case_id="empty-format-contract", registry=registry
    )
    assert result.expected_color == "green" and not result.triggers


@pytest.mark.parametrize(
    "problem",
    [
        "bold",
        "superscript",
        "missing_row",
        "extra_row",
        "duplicate_row",
        "unknown_id",
        "ambiguous_color",
        "wrong_expected",
        "bad_decoy",
        "bad_tag",
    ],
)
def test_ambiguous_or_inconsistent_key_formats_fail_closed(problem, registry):
    document = Document(BytesIO(docx_format_contract(registry)))
    if problem == "bold":
        document.paragraphs[0].runs[0].bold = False
    elif problem == "superscript":
        document.paragraphs[0].runs[-1].font.superscript = False
    elif problem == "missing_row":
        document.tables[0]._tbl.remove(document.tables[0].rows[1]._tr)
    elif problem in ("extra_row", "duplicate_row"):
        row = document.tables[0].add_row()
        for cell, text in zip(
            row.cells,
            ("T2" if problem == "extra_row" else "T1", "L2-01", "Yellow", "Format contract"),
            strict=True,
        ):
            cell.text = text
    elif problem == "unknown_id":
        document.tables[0].rows[1].cells[1].text = "L1-2"
    elif problem == "ambiguous_color":
        document.tables[0].rows[1].cells[2].text = "Red / Yellow"
    elif problem == "wrong_expected":
        document.paragraphs[2].text = "Expected tool result: GREEN"
    elif problem == "bad_decoy":
        document.paragraphs[-1].text = 'Decoy (not a trigger): "unclosed'
    else:
        document.paragraphs[0].runs[-1].text = "[T0]"
    with pytest.raises(KeyFormatError):
        parse_key_bytes(save(document), "docx", case_id="bad-format-contract", registry=registry)


@pytest.mark.parametrize("kind", ["docx", "pdf"])
def test_corrupt_format_does_not_log_source_text(kind, registry, capsys):
    with pytest.raises(KeyFormatError):
        parse_key_bytes(
            b"Do not log contract content", kind, case_id="bad-format", registry=registry
        )
    output = capsys.readouterr()
    assert "Do not log contract content" not in output.out + output.err


def test_docx_renamed_as_pdf_is_not_interpreted_as_a_pdf_key(registry):
    with pytest.raises(KeyFormatError):
        parse_key_bytes(
            docx_format_contract(registry), "pdf", case_id="format-contract", registry=registry
        )


@pytest.mark.parametrize(
    "reference,expected",
    [
        ("L1-1", ("L1-1",)),
        ("L2-6; L2-29", ("L2-06", "L2-29")),
        ("List 1 item 6 and List 2 item 29", ("L1-6", "L2-29")),
        ("List 2 items 6, 29", ("L2-06", "L2-29")),
        ("Animal testing", ("L2-01",)),
        ("Animal testign", ("L2-01",)),
    ],
)
def test_reference_mapping_uses_only_official_ids(reference, expected, registry):
    assert resolve_items(reference, registry) == expected


@pytest.mark.parametrize(
    "reference", ["L1-2", "L2-99", "List 2 item 99", "readiness", "unrelated", "dwells"]
)
def test_unknown_or_ambiguous_references_are_not_guessed(reference, registry):
    with pytest.raises(KeyFormatError):
        resolve_items(reference, registry)


def test_gold_jsonl_round_trip_and_private_write(registry, tmp_path):
    case = parse_key_bytes(
        docx_format_contract(registry), "docx", case_id="format-contract", registry=registry
    )
    text = gold_jsonl((case,))
    assert parse_gold_jsonl(text) == (case,)
    output = tmp_path / "contract-gold.jsonl"
    write_gold_jsonl(output, (case,))
    assert output.read_text() == text and output.stat().st_mode & 0o777 == 0o600
    with pytest.raises(ValueError):
        parse_gold_jsonl(text + text)
    with pytest.raises(ValueError):
        parse_gold_jsonl("")


def test_jsonl_preserves_unicode_line_separators_inside_a_quote(registry):
    case = parse_key_bytes(
        docx_format_contract(registry), "docx", case_id="format-contract", registry=registry
    )
    trigger = case.triggers[0].model_copy(update={"quote": case.triggers[0].quote + "\u2028"})
    case = case.model_copy(update={"triggers": (trigger,)})
    assert parse_gold_jsonl(gold_jsonl((case,))) == (case,)
