"""Word page previews are created only when a reviewer opens the document."""

from fastapi import APIRouter, HTTPException, Response

from backend.core.annotation_notes import AnnotationError
from backend.core.word_converter import PreviewError
from backend.core.word_preview import WordLayout, WordPreview


def layout_router(previews: WordPreview) -> APIRouter:
    router = APIRouter(prefix="/api/batches/{run_id}/papers/{entry_id}/layout")

    @router.get("", response_model=WordLayout)
    def layout(run_id: str, entry_id: str) -> WordLayout:
        try:
            return previews.prepare(run_id, entry_id)[1]
        except (PreviewError, AnnotationError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/{identity}/pages/{number}.png")
    def page(run_id: str, entry_id: str, identity: str, number: int) -> Response:
        try:
            data = previews.page(run_id, entry_id, identity, number)
        except (PreviewError, AnnotationError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return Response(data, media_type="image/png")

    return router
