"""Local SPA host. Validate settings and policies before opening a listener."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.api.admin import admin_router
from backend.api.ai import ai_router
from backend.api.batches import batches_router
from backend.api.document_folders import document_folders_router
from backend.api.evaluation import evaluation_router
from backend.api.export import export_router
from backend.api.items import items_router
from backend.api.layout import layout_router
from backend.api.papers import papers_router
from backend.api.system import system_router
from backend.core.ai_config import AIConfig
from backend.core.batch import BatchService
from backend.core.batch_folders import BatchFolders
from backend.core.engines.ai import AIEngine
from backend.core.engines.local_bge import EmbeddingProvider
from backend.core.engines.ollama import AIProvider
from backend.core.engines.rules import RulesEngine
from backend.core.engines.semantic import SemanticEngine
from backend.core.export import ExportService
from backend.core.policy_manager import PolicyManager
from backend.core.policy_models import PolicyConflict, PolicyInputError
from backend.core.review_store import ReviewConflict, ReviewStore
from backend.core.rules_loader import PolicyError, load_rules
from backend.core.runtime import configure_offline_environment
from backend.core.screening_context import ScreeningContext
from backend.core.settings import load_settings
from backend.core.specificity import SpecificityEngine
from backend.core.word_preview import WordPreview
from backend.security.auth import AuthFailure, AuthService


def create_app(
    root: Path | None = None,
    *,
    semantic_provider: EmbeddingProvider | None = None,
    ai_provider: AIProvider | None = None,
) -> FastAPI:
    project_root = root or Path(__file__).resolve().parent.parent
    configure_offline_environment(project_root)
    settings = load_settings(project_root)
    rules = load_rules(project_root)
    engine = RulesEngine(rules)
    configure_offline_environment(project_root)
    static = project_root / "backend/static"
    if not (static / "index.html").is_file():
        raise PolicyError("Frontend build missing — run npm ci && npm run build in frontend/")

    semantic = SemanticEngine(project_root, rules, settings.semantic, provider=semantic_provider)
    specificity = SpecificityEngine(project_root, rules)
    ai = AIEngine(settings.ai, provider=ai_provider)
    service = BatchService(
        project_root, rules, engine, semantic=semantic, specificity=specificity, ai=ai
    )
    folders = BatchFolders(service.store)
    folders.migrate_existing()
    reviews = ReviewStore(service.store, folders)

    def organize(run_id: str, entry_id: str) -> None:
        batch = service.store.read(run_id)
        entry = service.store.entry(run_id, entry_id)
        folders.attempt(batch, entry, reviews.state(run_id, entry_id))

    service.on_entry_changed = organize

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await asyncio.to_thread(manager.previews.close)
        await asyncio.to_thread(service.close)

    app = FastAPI(
        title="SPR Pre-Screen", version="0.0.0", docs_url=None, redoc_url=None, lifespan=lifespan
    )

    def installed(context: ScreeningContext) -> None:
        app.state.rules_engine = context.engine
        app.state.semantic_engine = context.semantic
        app.state.specificity_engine = context.specificity

    auth = AuthService(project_root)
    manager = PolicyManager(project_root, service, installed)
    configuration = AIConfig(project_root, ai, service.store.lock)
    app.state.ai_engine = ai
    app.state.ai_configuration = configuration
    app.state.auth_service = auth
    app.state.policy_manager = manager
    app.state.rules_engine = engine
    app.state.batch_service = service
    app.state.batch_folders = folders
    app.state.semantic_engine = semantic
    app.state.specificity_engine = specificity
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])

    @app.middleware("http")
    async def local_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            if (
                origin is not None and origin != str(request.base_url).rstrip("/")
            ) or request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse(
                    {"detail": "Use the local workspace to make changes"}, status_code=403
                )
        if request.method == "POST" and (
            request.url.path == "/api/batches" or request.url.path.endswith("/preview")
        ):
            try:
                if (
                    int(request.headers.get("content-length", "0"))
                    > 100 * 25 * 1024**2 + 2 * 1024**2
                ):
                    return JSONResponse({"detail": "Batch exceeds upload limits"}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid upload length"}, status_code=400)
        if request.url.path == "/api/admin/login":
            try:
                if int(request.headers.get("content-length", "0")) > 16384:
                    return JSONResponse(
                        {"detail": "Sign-in request exceeds size limit"}, status_code=413
                    )
            except ValueError:
                return JSONResponse({"detail": "Invalid upload length"}, status_code=400)
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'self'"
        )
        return response

    @app.exception_handler(KeyError)
    async def missing(request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse({"detail": "Run or upload not found"}, status_code=404)

    @app.exception_handler(ReviewConflict)
    async def conflict(request: Request, exc: ReviewConflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(PolicyConflict)
    async def policy_conflict(request: Request, exc: PolicyConflict) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(PolicyInputError)
    async def policy_input(request: Request, exc: PolicyInputError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(AuthFailure)
    async def auth_error(request: Request, exc: AuthFailure) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(ValueError)
    async def invalid(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            {"detail": "Invalid operation or damaged stored record"}, status_code=422
        )

    @app.exception_handler(OSError)
    async def storage_error(request: Request, exc: OSError) -> JSONResponse:
        return JSONResponse(
            {"detail": "Local storage unavailable. Check disk space and permissions."},
            status_code=503,
        )

    app.include_router(system_router(project_root, settings, service))
    app.include_router(admin_router(auth, manager))
    app.include_router(ai_router(configuration, auth))
    app.include_router(batches_router(service, reviews))
    app.include_router(document_folders_router(service.store, reviews, folders))
    app.include_router(papers_router(service.store, reviews))
    app.include_router(items_router(service, reviews))
    app.include_router(evaluation_router(project_root))
    app.include_router(layout_router(WordPreview(project_root, service.store)))
    app.include_router(export_router(ExportService(service.store, reviews)))
    app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path not in ("", "rules", "system", "offline", "items", "scorecard") and not (
            path.startswith("review/") and len(path.split("/")) == 3
        ):
            raise HTTPException(status_code=404, detail="Route not found")
        return FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})

    return app
