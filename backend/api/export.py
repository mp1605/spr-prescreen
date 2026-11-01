"""Download private, source-bound review artifacts and batch reports."""

import json
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from backend.core.annotation_notes import AnnotationError
from backend.core.batch_index import index_csv, index_rows
from backend.core.export import ExportNotReady, ExportService
from backend.core.export_models import AnnotationManifest


def export_router(exports: ExportService) -> APIRouter:
    router = APIRouter(prefix="/api/batches/{run_id}")

    @router.get("/export/{format}")
    def report(
        run_id: str, format: Literal["csv", "json"], layout: Literal["index", "audit"] = "index"
    ) -> Response:
        try:
            if layout == "audit":
                data, media, name = exports.report(run_id, format)
            else:
                rows = index_rows(exports.store, run_id)
                data = (
                    (json.dumps(rows, ensure_ascii=False, indent=2) + "\n").encode()
                    if format == "json"
                    else index_csv(rows).encode("utf-8-sig")
                )
                media = "application/json" if format == "json" else "text/csv; charset=utf-8"
                name = f"{run_id}-index.{format}"
        except AnnotationError as exc:
            raise HTTPException(409, str(exc)) from exc
        return Response(
            data,
            media_type=media,
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
            },
        )

    def artifact(run_id: str, entry_id: str, notes: bool) -> tuple[Path, AnnotationManifest]:
        try:
            return exports.annotated(run_id, entry_id, notes=notes)
        except ExportNotReady as exc:
            raise HTTPException(409, str(exc)) from exc
        except AnnotationError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/papers/{entry_id}/annotated")
    def annotated(run_id: str, entry_id: str, notes: bool = False) -> FileResponse:
        path, manifest = artifact(run_id, entry_id, notes)
        media = (
            "application/pdf"
            if path.suffix == ".pdf"
            else ("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        )
        return FileResponse(
            path,
            media_type=media,
            filename=manifest.download_file_name,
            headers={
                "X-Source-SHA256": manifest.source_sha256,
                "X-Artifact-SHA256": manifest.annotated_sha256,
                "X-Review-Revision": str(manifest.review_revision),
                "X-Annotation-Warnings": str(len(manifest.warnings)),
            },
        )

    @router.get("/papers/{entry_id}/annotation-manifest", response_model=AnnotationManifest)
    def manifest(run_id: str, entry_id: str, notes: bool = False) -> AnnotationManifest:
        _, metadata = artifact(run_id, entry_id, notes)
        return metadata

    return router
