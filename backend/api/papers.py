"""Evidence and decisions are separate resources; no endpoint modifies scanner findings."""

import pymupdf  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import Field

from backend.core.batch_models import BatchEntry, ReviewCommand, ReviewState
from backend.core.ingest_models import ParseResult
from backend.core.page_render import render_page, verified_pdf
from backend.core.review_store import ReviewStore
from backend.core.run_store import RunStore


class DocumentView(ParseResult):
    page_rotations: dict[int, int] = Field(default_factory=dict)


def papers_router(store: RunStore, reviews: ReviewStore) -> APIRouter:
    router = APIRouter(prefix="/api/batches/{run_id}/papers/{entry_id}")

    @router.get("", response_model=BatchEntry)
    def paper(run_id: str, entry_id: str) -> BatchEntry:
        return store.entry(run_id, entry_id)

    @router.get("/original")
    def original(run_id: str, entry_id: str) -> FileResponse:
        entry = store.entry(run_id, entry_id)
        source = store.source(run_id, entry_id)
        if not source.is_file():
            raise HTTPException(404, "Original file unavailable")
        return FileResponse(source, media_type="application/octet-stream", filename=entry.file_name)

    @router.get("/document", response_model=DocumentView)
    def document(run_id: str, entry_id: str) -> DocumentView:
        entry = store.entry(run_id, entry_id)
        if entry.phase != "done":
            raise HTTPException(409, "Wait for screening to finish")
        parsed = store.parsed(run_id, entry_id)
        rotations = {}
        if parsed.file_type == "pdf":
            try:
                data = verified_pdf(
                    store.source(run_id, entry_id), parsed.paper_id.removeprefix("sha256:")
                )
                with pymupdf.open(stream=data, filetype="pdf") as original:
                    rotations = {
                        u.page: original[u.page - 1].rotation for u in parsed.units if u.page
                    }
            except Exception as exc:
                raise HTTPException(422, "Original PDF could not be verified for display.") from exc
        return DocumentView(
            **parsed.model_dump(exclude={"review_color", "incomplete_pages"}),
            page_rotations=rotations,
        )

    @router.get("/pages/{number}.png")
    def page(run_id: str, entry_id: str, number: int) -> Response:
        entry = store.entry(run_id, entry_id)
        if entry.phase != "done" or entry.result is None or entry.result.file_type != "pdf":
            raise HTTPException(404, "PDF page unavailable")
        try:
            image = render_page(
                store.source(run_id, entry_id),
                number,
                expected_sha256=entry.result.paper_id.removeprefix("sha256:"),
            )
        except Exception as exc:
            raise HTTPException(
                422, "Page could not be rendered. Inspect the original file."
            ) from exc
        return Response(
            image, media_type="image/png", headers={"Cache-Control": "private, no-store"}
        )

    @router.get("/decisions", response_model=ReviewState)
    def decisions(run_id: str, entry_id: str) -> ReviewState:
        return reviews.state(run_id, entry_id)

    @router.post("/decisions", response_model=ReviewState)
    def decide(run_id: str, entry_id: str, command: ReviewCommand) -> ReviewState:
        return reviews.apply(run_id, entry_id, command)

    return router
