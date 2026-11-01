"""Render original page orientation; the UI rotates evidence coordinates with the page."""

import hashlib
from pathlib import Path

import pymupdf  # type: ignore[import-untyped]


def verified_pdf(source: Path, expected_sha256: str | None = None) -> bytes:
    data = source.read_bytes()
    if expected_sha256 is not None and hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("Original SHA-256 no longer matches the screening result")
    return data


def render_page(source: Path, number: int, *, expected_sha256: str | None = None) -> bytes:
    with pymupdf.open(stream=verified_pdf(source, expected_sha256), filetype="pdf") as document:
        if not document.is_pdf or document.needs_pass or not 1 <= number <= document.page_count:
            raise ValueError("Page is unavailable")
        page = document[number - 1]
        # Bound memory even for PDFs with unusually large page dimensions.
        scale = min(1.5, 1800 / max(page.rect.width, page.rect.height))
        if scale <= 0:
            raise ValueError("Page geometry is invalid")
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        result: bytes = pixmap.tobytes("png")
        return result
