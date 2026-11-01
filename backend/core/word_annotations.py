"""Split Word runs at exact source boundaries while retaining run properties and objects."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.run import Run

from backend.core.annotation_notes import AnnotationError
from backend.core.models import Finding

# python-docx's registered lxml elements have no complete static type surface.
Xml = Any
TEXT_TAGS = {qn("w:t"), qn("w:delText")}
SCALAR_TAGS = {qn("w:br"), qn("w:cr"), qn("w:tab"), qn("w:ptab"), qn("w:noBreakHyphen")}


@dataclass
class RunPiece:
    node: Xml
    start: int
    end: int


def source_runs(paragraph: Xml) -> list[Xml]:
    return [r for r in paragraph.xpath(".//w:r") if r.xpath("ancestor::w:p[1]")[0] is paragraph]


def run_text(run: Xml) -> str:
    text: str = Run(run, run).text
    return text + "".join(e.text or "" for e in run.xpath(".//w:delText"))


def child_text(child: Xml) -> str:
    if child.tag in TEXT_TAGS:
        return str(child.text or "")
    if child.tag in SCALAR_TAGS:
        return str(child)
    return ""


def highlighted_run(run: Xml, text_start: int, flags: list[Finding]) -> list[RunPiece]:
    text = run_text(run)
    end = text_start + len(text)
    relevant = [
        f for f in flags if text_start < f.location.char_end and f.location.char_start < end
    ]
    if not relevant:
        return [RunPiece(run, text_start, end)]
    cuts = sorted(
        {
            0,
            len(text),
            *[
                min(len(text), max(0, point - text_start))
                for f in relevant
                for point in (f.location.char_start, f.location.char_end)
            ],
        }
    )
    children = [c for c in run if c.tag != qn("w:rPr")]
    if "".join(child_text(c) for c in children) != text:
        raise AnnotationError("A complex Word run cannot be mapped exactly. Export JSON instead.")
    # Create fragments, then distribute each original XML child once in source order.
    pieces = []
    for left, right in zip(cuts, cuts[1:], strict=False):
        clone = OxmlElement("w:r")
        clone.attrib.update(run.attrib)
        properties = run.find(qn("w:rPr"))
        if properties is not None:
            clone.append(deepcopy(properties))
        active = [
            f
            for f in relevant
            if left + text_start < f.location.char_end
            and f.location.char_start < right + text_start
        ]
        if active:
            props = clone.get_or_add_rPr()
            for old in list(props.findall(qn("w:highlight"))):
                props.remove(old)
            props.get_or_add_highlight().set(
                qn("w:val"), "red" if any(f.color == "red" for f in active) else "yellow"
            )
        pieces.append(RunPiece(clone, text_start + left, text_start + right))
    cursor = 0
    for child in children:
        content = child_text(child)
        if not content:
            target = next((p for p in pieces if p.start <= text_start + cursor < p.end), pieces[-1])
            target.node.append(deepcopy(child))
        else:
            for piece in pieces:
                left = max(cursor, piece.start - text_start)
                right = min(cursor + len(content), piece.end - text_start)
                if left >= right:
                    continue
                copy = deepcopy(child)
                if child.tag in TEXT_TAGS:
                    copy.text = content[left - cursor : right - cursor]
                    copy.set(qn("xml:space"), "preserve")
                piece.node.append(copy)
        cursor += len(content)
    parent = run.getparent()
    index = parent.index(run)
    tail = run.tail
    parent.remove(run)
    for offset, piece in enumerate(pieces):
        piece.node.tail = tail if offset == len(pieces) - 1 else None
        parent.insert(index + offset, piece.node)
    return pieces


def annotate_paragraph(paragraph: Xml, text: str, flags: list[Finding]) -> list[RunPiece]:
    runs = source_runs(paragraph)
    if "".join(run_text(r) for r in runs) != text:
        raise AnnotationError("Word paragraph no longer matches its source evidence.")
    offset = 0
    pieces = []
    for run in runs:
        length = len(run_text(run))
        if length:
            pieces.extend(highlighted_run(run, offset, flags))
        offset += length
    return pieces


def anchor_comment(first: Xml, last: Xml, identifier: int) -> None:
    start = OxmlElement("w:commentRangeStart")
    start.set(qn("w:id"), str(identifier))
    end = OxmlElement("w:commentRangeEnd")
    end.set(qn("w:id"), str(identifier))
    reference = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    style = OxmlElement("w:rStyle")
    style.set(qn("w:val"), "CommentReference")
    props.append(style)
    reference.append(props)
    marker = OxmlElement("w:commentReference")
    marker.set(qn("w:id"), str(identifier))
    reference.append(marker)
    first.addprevious(start)
    last.addnext(end)
    end.addnext(reference)


def bookmark_name(finding_id: str) -> str:
    import hashlib

    # Alphanumeric names survive LibreOffice PDF destination encoding unchanged.
    return "SPRF" + hashlib.sha256(finding_id.encode()).hexdigest()[:28]


def anchor_bookmark(first: Xml, last: Xml, identifier: int, name: str) -> None:
    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), str(identifier))
    start.set(qn("w:name"), name)
    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), str(identifier))
    first.addprevious(start)
    last.addnext(end)
