from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from backend.core.ingest import parse_document
from backend.core.ingest_models import IngestLimits


def save(document):
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def replace_part(data, part, value):
    output = BytesIO()
    with ZipFile(BytesIO(data)) as source, ZipFile(output, "w", ZIP_DEFLATED) as target:
        for name in source.namelist():
            target.writestr(name, value if name == part else source.read(name))
        if part not in source.namelist():
            target.writestr(part, value)
    return output.getvalue()


def test_official_policy_transcription_runs_headings_and_exact_spans(guide_docx, official_rules):
    result = parse_document("policy.docx", guide_docx)
    assert result.status == "complete"
    assert len(result.units) == 41
    assert {u.text for u in result.units} >= {
        r.text for r in (*official_rules.list1, *official_rules.list2)
    }
    assert all(s.location.paragraph and s.location.page is None for s in result.segments)
    assert any(s.location.heading == "List 2" for s in result.segments)
    assert result.units[1].runs[0].bold
    assert result.units[1].runs[1].italic
    assert result.review_color is None and result.screening_state == "NOT_SCREENED"
    for segment in result.segments:
        unit = result.units[segment.unit_id - 1]
        assert unit.text[segment.location.char_start : segment.location.char_end] == segment.text


def test_tables_merged_cells_and_document_order(official_rules):
    document = Document()
    one, two = official_rules.list2[:2]
    document.add_paragraph(one.text)
    table = document.add_table(rows=1, cols=2)
    cell = table.cell(0, 0).merge(table.cell(0, 1))
    cell.text = two.text
    document.add_paragraph(one.text)
    result = parse_document("policy.docx", save(document))
    assert [s.text for s in result.segments] == [one.text, two.text, one.text]
    assert [s.location.paragraph for s in result.segments] == [1, 2, 3]


def test_headers_footers_comments_and_footnotes_are_not_lost(official_rules):
    document = Document()
    body, header, footer, note, comment = [r.text for r in official_rules.list2[:5]]
    document.add_paragraph(body)
    document.sections[0].header.paragraphs[0].text = header
    document.sections[0].footer.paragraphs[0].text = footer
    data = save(document)
    xml = (
        '<w:footnotes xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:footnote w:id="1"><w:p><w:r><w:t>{note}</w:t></w:r></w:p></w:footnote>'
        "</w:footnotes>"
    )
    data = replace_part(data, "word/footnotes.xml", xml.encode())
    xml = (
        '<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f'<w:comment w:id="0"><w:p><w:r><w:t>{comment}</w:t></w:r></w:p></w:comment>'
        "</w:comments>"
    )
    data = replace_part(data, "word/comments.xml", xml.encode())
    result = parse_document("policy.docx", data)
    assert result.status == "complete"
    assert {s.text for s in result.segments} >= {body, header, footer, note, comment}
    assert len({u.paragraph for u in result.units}) == len(result.units)


def test_hyperlink_text_is_retained_without_following_it(official_rules, monkeypatch):
    import socket

    def blocked(*args, **kwargs):
        raise AssertionError("Hyperlink must not be opened")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    document = Document()
    paragraph = document.add_paragraph()
    hyperlink = OxmlElement("w:hyperlink")
    rid = document.part.relate_to(
        "https://example.invalid", RELATIONSHIP_TYPE.HYPERLINK, is_external=True
    )
    hyperlink.set(qn("r:id"), rid)
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = official_rules.list2[0].text
    run.append(text)
    hyperlink.append(run)
    paragraph._p.append(hyperlink)
    result = parse_document("policy.docx", save(document))
    assert result.status == "complete"
    assert result.segments[0].text == text.text
    assert result.units[0].runs[0].hyperlink == rid


def test_tracked_text_is_retained_and_marked_incomplete(official_rules):
    document = Document()
    paragraph = document.add_paragraph(official_rules.list2[0].text)
    inserted = OxmlElement("w:ins")
    run = OxmlElement("w:r")
    text = OxmlElement("w:t")
    text.text = " " + official_rules.list2[1].text
    run.append(text)
    inserted.append(run)
    paragraph._p.append(inserted)
    result = parse_document("policy.docx", save(document))
    assert result.status == "incomplete" and result.review_color == "yellow"
    assert text.text in result.units[0].text
    assert any(i.code == "unsupported_content" for i in result.issues)


def test_textbox_paragraph_is_retained_once(official_rules):
    document = Document()
    paragraph = document.add_paragraph(official_rules.list2[0].text)
    outer = OxmlElement("w:r")
    picture = OxmlElement("w:pict")
    box = OxmlElement("w:txbxContent")
    inner_p = OxmlElement("w:p")
    inner_r = OxmlElement("w:r")
    inner_t = OxmlElement("w:t")
    inner_t.text = official_rules.list2[1].text
    inner_r.append(inner_t)
    inner_p.append(inner_r)
    box.append(inner_p)
    picture.append(box)
    outer.append(picture)
    paragraph._p.append(outer)
    result = parse_document("policy.docx", save(document))
    assert [s.text for s in result.segments] == [official_rules.list2[0].text, inner_t.text]
    assert result.status == "incomplete"  # Visual content is not silently assumed readable.


def test_package_and_text_limits_fail_closed(guide_docx):
    for limits in (
        IngestLimits(max_uncompressed_bytes=1),
        IngestLimits(max_zip_entries=1),
        IngestLimits(max_paragraphs=1),
        IngestLimits(max_characters=1),
    ):
        result = parse_document("policy.docx", guide_docx, limits=limits)
        assert result.status == "incomplete" and result.review_color == "yellow"
        assert any(i.code == "resource_limit" for i in result.issues)


def test_xml_doctype_and_archive_traversal_never_execute(guide_docx, tmp_path):
    evil_xml = b'<!DOCTYPE document [<!ENTITY e SYSTEM "file:///nonexistent/private">]><document>&e;</document>'
    result = parse_document("policy.docx", replace_part(guide_docx, "word/document.xml", evil_xml))
    assert result.status == "incomplete"
    data = replace_part(guide_docx, "../outside.xml", b"<xml/>")
    result = parse_document("policy.docx", data)
    assert result.status == "incomplete"
    assert not (tmp_path.parent / "outside.xml").exists()
