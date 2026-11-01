"""All policy writes and private drafts/impact reports require the local admin session."""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.datastructures import UploadFile

from backend.cli_io import source_allowed
from backend.core.export_io import write_binary
from backend.core.ingest import safe_name
from backend.core.policy_manager import PolicyManager
from backend.core.policy_models import (
    Draft,
    DraftEdit,
    PolicyConflict,
    PolicyInputError,
    Preview,
    PreviewEntry,
    PublishCommand,
    RevisionCommand,
)
from backend.core.rules_loader import PolicyError, StrictModel
from backend.security.auth import (
    COOKIE,
    SESSION_SECONDS,
    AuthFailure,
    AuthService,
    AuthStatus,
    RateLimited,
)


class Login(StrictModel):
    password: str


class CreateDraft(StrictModel):
    restore_from: str | None = None


def admin_router(auth: AuthService, manager: PolicyManager) -> APIRouter:
    router = APIRouter(prefix="/api/admin")

    def require_admin(request: Request) -> None:
        if not auth.status(request.cookies.get(COOKIE)).authenticated:
            raise HTTPException(403, "Admin sign-in is required to manage rules.")

    @router.get("/session", response_model=AuthStatus)
    def session(request: Request) -> AuthStatus:
        return auth.status(request.cookies.get(COOKIE))

    @router.post("/login", response_model=AuthStatus)
    def login(command: Login, request: Request, response: Response) -> AuthStatus:
        try:
            token, status = auth.login(command.password)
        except RateLimited as exc:
            raise HTTPException(
                429, str(exc), headers={"Retry-After": str(exc.retry_after)}
            ) from exc
        except AuthFailure as exc:
            raise HTTPException(403, str(exc)) from exc
        auth.logout(request.cookies.get(COOKIE))
        response.set_cookie(
            COOKIE,
            token,
            max_age=SESSION_SECONDS,
            httponly=True,
            samesite="strict",
            path="/api/admin",
        )
        return status

    @router.post("/logout", status_code=204)
    def logout(request: Request, response: Response) -> None:
        auth.logout(request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/api/admin", httponly=True, samesite="strict")

    protected = APIRouter(dependencies=[Depends(require_admin)])

    @protected.get("/rules/history")
    def history() -> dict[str, object]:
        with manager.lock:
            _, active = manager.current()
            events = (
                [
                    json.loads(line)
                    for line in (manager.root / "policies/audit.log").read_bytes().splitlines()
                ]
                if (manager.root / "policies/audit.log").exists()
                else []
            )
            return {
                "active": active.model_dump(mode="json"),
                "versions": manager.history(),
                "audit": events,
            }

    @protected.get("/rules/drafts")
    def drafts() -> list[Draft]:
        with manager.lock:
            return sorted(
                (manager.read(p.stem) for p in (manager.root / "policies/drafts").glob("*.json")),
                key=lambda d: d.created_utc,
                reverse=True,
            )

    @protected.post("/rules/drafts", response_model=Draft, status_code=201)
    def create(command: CreateDraft) -> Draft:
        return manager.create(command.restore_from)

    @protected.get("/rules/drafts/{identifier}", response_model=Draft)
    def draft(identifier: str) -> Draft:
        with manager.lock:
            return manager.read(identifier)

    @protected.put("/rules/drafts/{identifier}", response_model=Draft)
    def edit(identifier: str, command: DraftEdit) -> Draft:
        return manager.edit(identifier, command.revision, command.yaml_text)

    @protected.post("/rules/drafts/{identifier}/validate", response_model=Draft)
    def validate(identifier: str, command: RevisionCommand) -> Draft:
        return manager.validate(identifier, command.revision)

    @protected.post("/rules/drafts/{identifier}/preview", status_code=202)
    async def preview(identifier: str, request: Request, revision: int) -> dict[str, object]:
        with manager.lock:
            current = manager.checked(identifier, revision)
            if not current.validation or not current.validation.valid:
                raise PolicyInputError("Validate the draft before uploading preview files.")
            if manager.previews.active:
                raise PolicyConflict("Another impact preview is running. Wait for it to finish.")
        preview_id = uuid4().hex
        folder = manager.previews.path(preview_id)
        entries = []
        try:
            async with request.form(max_files=100, max_fields=0) as form:
                files = list(form.multi_items())
                if not files or any(not isinstance(value, UploadFile) for _, value in files):
                    raise HTTPException(
                        422, "Select 1–100 permitted PDF/DOCX files for this preview."
                    )
                for index, (_, value) in enumerate(files):
                    if not isinstance(value, UploadFile):
                        continue
                    name = safe_name(value.filename or "unnamed")
                    if not source_allowed(Path(value.filename or name)) or Path(
                        name
                    ).suffix.lower() not in (".pdf", ".docx"):
                        raise HTTPException(
                            422,
                            "Keys, evaluation metadata and unsupported formats "
                            "cannot be preview inputs.",
                        )
                    data = await value.read(25 * 1024**2 + 1)
                    if len(data) > 25 * 1024**2:
                        raise HTTPException(413, "A preview file exceeds 25 MiB.")
                    write_binary(folder / f"{index}.source", data)
                    entries.append(
                        PreviewEntry(file_name=name, sha256=hashlib.sha256(data).hexdigest())
                    )
            report = Preview(
                preview_id=preview_id,
                draft_id=identifier,
                draft_sha256=hashlib.sha256(current.yaml_text.encode()).hexdigest(),
                base_sha256=current.base_sha256,
                entries=tuple(entries),
                created_utc=datetime.now(UTC),
            )
            saved = manager.start_preview(identifier, revision, report)
            return {
                "draft": saved.model_dump(mode="json"),
                "preview": report.model_dump(mode="json"),
            }
        except Exception:
            if manager.previews.active != preview_id:
                shutil.rmtree(folder, ignore_errors=True)
            raise

    @protected.get("/rules/previews/{identifier}", response_model=Preview)
    def impact(identifier: str) -> Preview:
        with manager.lock:
            preview = manager.previews.read(identifier)
            if preview.state in ("queued", "running") and manager.previews.active != identifier:
                preview = preview.model_copy(
                    update={
                        "state": "interrupted",
                        "eligible": False,
                        "message": "Service restarted during preview. Start a fresh impact scan.",
                    }
                )
            return preview

    @protected.post("/rules/drafts/{identifier}/publish")
    def publish(identifier: str, command: PublishCommand) -> object:
        try:
            return manager.publish(
                identifier, command.revision, command.preview_id, command.change_note
            )
        except PolicyError as exc:
            raise HTTPException(
                503,
                "Publication did not finish reliably. Restart the service to recover "
                "the prepared transaction; inspect policy integrity if recovery fails.",
            ) from exc

    router.include_router(protected)
    return router
