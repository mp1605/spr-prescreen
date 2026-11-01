"""Admin AI settings persist atomically and never fetch or start a model."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

import yaml
from pydantic import Field

from backend.core.engines.ai import AIEngine, settings_digest
from backend.core.engines.ollama import LocalModel
from backend.core.export_io import write_binary
from backend.core.policy_models import PolicyConflict, PolicyInputError
from backend.core.rules_loader import StrictModel
from backend.core.settings import AISettings, load_settings


class AIEdit(StrictModel):
    revision: str
    enabled: bool
    model: str = Field(min_length=1, max_length=160)
    timeout_seconds: int = Field(ge=1, le=120)
    context_tokens: int = Field(ge=2048, le=32768)
    max_output_tokens: int = Field(ge=256, le=4096)


class AIStatus(StrictModel):
    settings: AISettings
    revision: str
    available: bool
    models: tuple[LocalModel, ...]
    message: str


class AIConfig:
    def __init__(self, root: Path, engine: AIEngine, lock: RLock) -> None:
        self.root, self.engine, self.lock = root, engine, lock

    async def status(self) -> AIStatus:
        try:
            models = await asyncio.wait_for(self.engine.provider.models(), 2)
            available = True
            message = "Local Ollama inventory received. Only cached local GGUF models are eligible."
        except Exception:
            models = ()
            available = False
            message = (
                "Local Ollama is unavailable at 127.0.0.1:11434. "
                "AI remains optional; no download was attempted."
            )
        with self.lock:
            settings = self.engine.settings
            return AIStatus(
                settings=settings,
                revision=settings_digest(settings),
                available=available,
                models=models,
                message=message,
            )

    async def save(self, command: AIEdit) -> AIStatus:
        with self.lock:
            if command.revision != settings_digest(self.engine.settings):
                raise PolicyConflict(
                    "AI settings changed in another window. Refresh before saving."
                )
        digest = None
        if command.enabled:
            try:
                async with asyncio.timeout(3):
                    models = await self.engine.provider.models()
                    selected = next((m for m in models if m.name == command.model), None)
                    if selected is None:
                        raise ValueError("model_missing")
                    if (
                        await self.engine.provider.context_limit(selected.name)
                        < command.context_tokens
                    ):
                        raise ValueError("context_limit")
                    digest = selected.digest
            except Exception as exc:
                raise PolicyInputError(
                    "AI could not be enabled. Start local-only Ollama with the cached GGUF model "
                    "and a supported context size; refresh model status."
                ) from exc
        try:
            candidate = AISettings(
                **command.model_dump(exclude={"revision"}),
                model_digest=digest,
                endpoint="http://127.0.0.1:11434",
            )
        except ValueError as exc:
            raise PolicyInputError("Invalid local AI settings or context/output budget.") from exc
        with self.lock:
            if command.revision != settings_digest(self.engine.settings):
                raise PolicyConflict(
                    "AI settings changed while the model was being checked. Refresh."
                )
            current = load_settings(self.root)
            if settings_digest(current.ai) != command.revision:
                raise PolicyConflict(
                    "AI settings changed on disk. Restart or refresh the service before editing."
                )
            updated = current.model_copy(update={"ai": candidate})
            write_binary(
                self.root / "config/settings.yaml",
                yaml.safe_dump(updated.model_dump(mode="json"), sort_keys=False).encode(),
            )
            self.engine.settings = candidate
            event = {
                "utc": datetime.now(UTC).isoformat(),
                "actor": "local admin",
                "operation": "configure_optional_ai",
                "previous_digest": command.revision,
                "configuration_digest": settings_digest(candidate),
                "enabled": candidate.enabled,
                "model": candidate.model,
                "model_digest": candidate.model_digest,
            }
            with (self.root / "config/ai-audit.jsonl").open("ab") as handle:
                os.chmod(handle.name, 0o600)
                handle.write((json.dumps(event) + "\n").encode())
                handle.flush()
                os.fsync(handle.fileno())
        return await self.status()
