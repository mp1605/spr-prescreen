"""Local model availability is readable; configuration requires the existing admin session."""

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.core.ai_config import AIConfig, AIEdit, AIStatus
from backend.security.auth import COOKIE, AuthService


def ai_router(configuration: AIConfig, auth: AuthService) -> APIRouter:
    router = APIRouter()

    def admin(request: Request) -> None:
        if not auth.status(request.cookies.get(COOKIE)).authenticated:
            raise HTTPException(403, "Admin sign-in is required to configure local AI.")

    @router.get("/api/ai", response_model=AIStatus)
    async def status() -> AIStatus:
        return await configuration.status()

    @router.put("/api/admin/ai", response_model=AIStatus, dependencies=[Depends(admin)])
    async def configure(command: AIEdit) -> AIStatus:
        return await configuration.save(command)

    return router
