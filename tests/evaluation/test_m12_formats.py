from io import BytesIO

from docx import Document

from backend.eval.contracts import docx_format_contract
from backend.eval.parse_keys import parse_key_bytes


def test_decoy_annotation_does_not_become_part_of_quoted_reference(registry):
    document = Document(BytesIO(docx_format_contract(registry)))
    text = registry.list2[1].text
    document.paragraphs[
        -1
    ].text = f'Decoy (not a trigger): "{text}". Explanatory text can include "another quote".'
    buffer = BytesIO()
    document.save(buffer)
    result = parse_key_bytes(
        buffer.getvalue(), "docx", case_id="format-contract", registry=registry
    )
    assert result.decoys == (text,)
