"""Cached, on-demand Word pages. Rendering never blocks the scan pipeline."""

from __future__ import annotations

import hashlib
import tempfile
import time
from io import BytesIO
from pathlib import Path
from threading import Lock
from zipfile import ZipFile

import pymupdf  # type: ignore[import-untyped]
from lxml import etree  # type: ignore[import-untyped]
from pydantic import Field

from backend.cli_io import write_report
from backend.core.annotate import annotate
from backend.core.batch_models import ReviewState
from backend.core.export_io import write_binary
from backend.core.ingest_models import SourceUnit
from backend.core.page_render import render_page
from backend.core.rules_loader import StrictModel
from backend.core.run_store import RunStore
from backend.core.word_annotations import bookmark_name
from backend.core.word_converter import PreviewError, convert_word


class PageAnchor(StrictModel):
    page: int
    x: float
    y: float


class WordLayout(StrictModel):
    identity: str = Field(pattern=r"^[a-f0-9]{64}$")
    pdf_sha256: str
    units: tuple[SourceUnit, ...]
    anchors: dict[str, PageAnchor]
    unmapped: tuple[str, ...]
    seconds: float
    renderer: str = "Bundled LibreOffice"


def verify_renderable(data: bytes) -> None:
    """Refuse active or externally linked content; never fetch it while making pages."""
    with ZipFile(BytesIO(data)) as archive:
        for name in archive.namelist():
            if "vbaproject" in name.lower():
                raise PreviewError(
                    "Macros require manual inspection. Download the highlighted DOCX."
                )
            if not name.endswith((".xml", ".rels")):
                continue
            tree = etree.fromstring(
                archive.read(name), etree.XMLParser(resolve_entities=False, no_network=True)
            )
            if name.endswith(".rels"):
                for relationship in tree:
                    if relationship.get("TargetMode") == "External" and not relationship.get(
                        "Type", ""
                    ).endswith("/hyperlink"):
                        raise PreviewError(
                            "Externally linked content cannot be rendered offline. "
                            "Download the highlighted DOCX."
                        )
            for node in tree.iter():
                if etree.QName(node).localname in {"instrText", "fldSimple"}:
                    instruction = (node.text or "") + " " + " ".join(node.attrib.values())
                    if any(
                        word in instruction.upper().split()
                        for word in (
                            "DDE",
                            "DDEAUTO",
                            "INCLUDETEXT",
                            "INCLUDEPICTURE",
                            "DATABASE",
                            "LINK",
                        )
                    ):
                        raise PreviewError(
                            "Linked fields require manual inspection. "
                            "Download the highlighted DOCX."
                        )


class WordPreview:
    def __init__(self, root: Path, store: RunStore) -> None:
        self.root, self.store = root, store
        self.gate = Lock()

    def prepare(self, run_id: str, entry_id: str) -> tuple[Path, WordLayout]:
        with self.store.lock:
            entry = self.store.entry(run_id, entry_id)
            if entry.phase != "done" or entry.result is None or entry.result.file_type != "docx":
                raise PreviewError("Word preview is available after screening finishes.")
            paper = entry.result
            parsed = self.store.parsed(run_id, entry_id)
            data = self.store.source(run_id, entry_id).read_bytes()
        if "sha256:" + hashlib.sha256(data).hexdigest() != paper.paper_id:
            raise PreviewError("Original SHA-256 no longer matches the screening result.")
        fingerprint = b"".join(
            (Path(__file__).parent / name).read_bytes()
            for name in (
                "word_preview.py",
                "word_converter.py",
                "annotate.py",
                "annotate_docx.py",
                "word_annotations.py",
            )
        )
        identity = hashlib.sha256(fingerprint + paper.model_dump_json().encode()).hexdigest()
        folder = self.store.path(run_id, entry_id) / "preview" / identity
        pdf, metadata = folder / "pages.pdf", folder / "layout.json"
        if not self.gate.acquire(timeout=70):
            raise PreviewError("Another Word preview is being prepared. Try again shortly.")
        try:
            if pdf.is_file() and metadata.is_file():
                layout = WordLayout.model_validate_json(metadata.read_bytes())
                if (
                    layout.identity == identity
                    and hashlib.sha256(pdf.read_bytes()).hexdigest() == layout.pdf_sha256
                ):
                    return pdf, layout
            started = time.monotonic()
            verify_renderable(data)
            review = ReviewState(revision=0, decisions={}, inspected=False, events=())
            content = annotate(data, parsed, paper, review, bookmarks=True).data
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            with tempfile.TemporaryDirectory(dir=folder) as temporary:
                temporary_path = Path(temporary)
                source = temporary_path / "highlighted.docx"
                write_binary(source, content)
                rendered = convert_word(self.root, source, temporary_path)
                result = rendered.read_bytes()
            units = []
            anchors = {}
            with pymupdf.open(stream=result, filetype="pdf") as document:
                if not 1 <= len(document) <= 1000:
                    raise PreviewError(
                        "Word preview exceeds the page limit. Download the highlighted DOCX."
                    )
                for index, page in enumerate(document):
                    units.append(
                        SourceUnit(
                            unit_id=index + 1,
                            page=index + 1,
                            part="word-preview",
                            text=page.get_text(),
                            width=page.rect.width,
                            height=page.rect.height,
                        )
                    )
                names = document.resolve_names()
                for flag in paper.findings:
                    destination = names.get(bookmark_name(flag.finding_id))
                    if destination is None:
                        continue
                    number = destination.get("page", -1)
                    point = destination.get("to")
                    if (
                        not isinstance(number, int)
                        or not 0 <= number < len(document)
                        or not isinstance(point, tuple)
                    ):
                        continue
                    page = document[number]
                    # PDF named destinations use bottom-left coordinates.
                    location = pymupdf.Point(point) * page.transformation_matrix
                    if page.rect.contains(location):
                        anchors[flag.finding_id] = PageAnchor(
                            page=number + 1, x=location.x, y=location.y
                        )
            layout = WordLayout(
                identity=identity,
                pdf_sha256=hashlib.sha256(result).hexdigest(),
                units=tuple(units),
                anchors=anchors,
                unmapped=tuple(f.finding_id for f in paper.findings if f.finding_id not in anchors),
                seconds=round(time.monotonic() - started, 3),
            )
            write_binary(pdf, result)
            write_report(metadata, layout.model_dump(mode="json"))
            return pdf, layout
        finally:
            self.gate.release()

    def page(self, run_id: str, entry_id: str, identity: str, number: int) -> bytes:
        pdf, layout = self.prepare(run_id, entry_id)
        if identity != layout.identity or not 1 <= number <= len(layout.units):
            raise PreviewError("Word preview page is unavailable. Reopen the document.")
        return render_page(pdf, number)
