"""Per-batch AI opt-in pins the configured local model without changing admin defaults."""

import asyncio
from typing import Literal

from backend.core.engines.ai import AIEngine
from backend.core.policy_models import PolicyInputError
from backend.core.settings import AISettings

BatchAIMode = Literal["default", "off", "on", "selective", "full"]


async def batch_ai_settings(engine: AIEngine | None, mode: BatchAIMode) -> AISettings | None:
    if engine is None:
        if mode in {"on", "selective", "full"}:
            raise PolicyInputError("Local AI is unavailable. Choose rules and semantic screening.")
        return None
    current = engine.settings
    if mode == "default":
        return current
    if mode == "off":
        return current.model_copy(update={"enabled": False})
    try:
        async with asyncio.timeout(3):
            models = await engine.provider.models()
            selected = next((m for m in models if m.name == current.model), None)
            if selected is None:
                raise ValueError("Configured model is not available")
            if current.model_digest is not None and selected.digest != current.model_digest:
                raise ValueError("Configured model has changed")
            if await engine.provider.context_limit(selected.name) < current.context_tokens:
                raise ValueError("Configured context exceeds the local model limit")
            return AISettings.model_validate(
                {
                    **current.model_dump(),
                    "enabled": True,
                    "scope": "selective" if mode == "selective" else "full",
                    "model_digest": selected.digest,
                }
            )
    except Exception as exc:
        raise PolicyInputError(
            "This batch was not started. Start local Ollama with the configured cached model "
            "and refresh its status, or choose Python scanner (no Ollama). "
            "If its model or context changed, ask an admin to verify AI settings."
        ) from exc
