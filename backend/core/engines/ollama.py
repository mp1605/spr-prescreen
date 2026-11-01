"""Loopback-only Ollama HTTP adapter; no pulls, redirects, tools, or cloud models."""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

import httpx
from pydantic import Field

from backend.core.rules_loader import StrictModel

ENDPOINT = "http://127.0.0.1:11434"


class AIUnavailable(ValueError):
    pass


class LocalModel(StrictModel):
    name: str
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(gt=0)


class AIProvider(Protocol):
    async def models(self) -> tuple[LocalModel, ...]: ...
    async def context_limit(self, model: str) -> int: ...
    async def complete(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class Ollama:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        # trust_env=False also excludes proxy settings and ambient credentials.
        async with httpx.AsyncClient(
            transport=self.transport,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(120, connect=2),
            limits=httpx.Limits(max_connections=1),
        ) as client:
            async with client.stream(method, ENDPOINT + path, json=payload) as response:
                if response.status_code != 200:
                    raise AIUnavailable("Local Ollama request failed")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 262144:
                        raise AIUnavailable("Local AI response exceeds resource limit")
            value = json.loads(data)
        if not isinstance(value, dict) or value.get("remote_host") or value.get("remote_model"):
            raise AIUnavailable("A local-only Ollama response is required")
        return value

    async def models(self) -> tuple[LocalModel, ...]:
        response = await self.request("GET", "/api/tags")
        values = response.get("models")
        if not isinstance(values, list) or len(values) > 128:
            raise AIUnavailable("Invalid local model inventory")
        models = []
        for value in values:
            if not isinstance(value, dict):
                continue
            name = value.get("name", "")
            details = value.get("details", {})
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,160}", name):
                continue
            if "cloud" in name.casefold() or value.get("remote_host") or value.get("remote_model"):
                continue
            if not isinstance(details, dict) or details.get("format") != "gguf":
                continue
            try:
                models.append(
                    LocalModel.model_validate(
                        {"name": name, "digest": value.get("digest"), "bytes": value.get("size")},
                        strict=True,
                    )
                )
            except ValueError:
                continue
        if len({m.name for m in models}) != len(models):
            raise AIUnavailable("Ambiguous local model names")
        return tuple(models)

    async def context_limit(self, model: str) -> int:
        response = await self.request("POST", "/api/show", {"model": model})
        if response.get("details", {}).get("format") != "gguf" or "completion" not in response.get(
            "capabilities", []
        ):
            raise AIUnavailable("A local GGUF completion model is required")
        info = response.get("model_info", {})
        values = [
            v
            for k, v in info.items()
            if k.endswith(".context_length") and isinstance(v, int) and not isinstance(v, bool)
        ]
        if not values or min(values) < 2048:
            raise AIUnavailable("Model context metadata is unavailable")
        return min(values)

    async def complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", "/api/chat", payload)
