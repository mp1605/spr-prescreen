"""Ollama protocol contracts using a labelled fake HTTP transport, not real model inference."""

import asyncio

import httpx
import pytest

from backend.core.engines.ollama import AIUnavailable, Ollama
from tests.ai.conftest import DIGEST, MODEL


def catalog(**extra):
    return {
        "models": [
            {"name": MODEL, "digest": DIGEST, "size": 1024, "details": {"format": "gguf"}, **extra}
        ]
    }


def test_http_adapter_uses_fixed_loopback_and_validates_local_metadata():
    calls = []

    async def handler(request):
        calls.append(request)
        assert request.url.host == "127.0.0.1" and request.url.port == 11434
        if request.url.path == "/api/tags":
            return httpx.Response(200, json=catalog())
        if request.url.path == "/api/show":
            return httpx.Response(
                200,
                json={
                    "details": {"format": "gguf"},
                    "capabilities": ["completion"],
                    "model_info": {"qwen2.context_length": 32768},
                },
            )
        return httpx.Response(
            200,
            json={
                "model": MODEL,
                "done": True,
                "done_reason": "stop",
                "message": {"content": "[]"},
            },
        )

    async def run():
        provider = Ollama(httpx.MockTransport(handler))
        models = await provider.models()
        assert models[0].digest == DIGEST
        assert await provider.context_limit(MODEL) == 32768
        assert (await provider.complete({"model": MODEL, "stream": False}))["done"]

    asyncio.run(run())
    assert [r.url.path for r in calls] == ["/api/tags", "/api/show", "/api/chat"]
    assert all(r.url.path != "/api/pull" for r in calls)


@pytest.mark.parametrize(
    "extra",
    [
        {"remote_host": "https://example.invalid"},
        {"remote_model": "remote"},
        {"name": "contract:cloud"},
        {"digest": "not-sha256"},
        {"size": 0},
        {"details": {"format": "remote"}},
    ],
)
def test_cloud_or_invalid_models_are_never_eligible(extra):
    provider = Ollama(
        httpx.MockTransport(lambda request: httpx.Response(200, json=catalog(**extra)))
    )
    assert asyncio.run(provider.models()) == ()


def test_redirects_and_cloud_responses_are_refused():
    calls = []

    def redirect(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://example.invalid"})

    with pytest.raises(AIUnavailable):
        asyncio.run(Ollama(httpx.MockTransport(redirect)).models())
    assert len(calls) == 1
    provider = Ollama(
        httpx.MockTransport(
            lambda request: httpx.Response(200, json={"remote_host": "https://example.invalid"})
        )
    )
    with pytest.raises(AIUnavailable):
        asyncio.run(provider.complete({}))


def test_oversized_responses_are_refused():
    provider = Ollama(
        httpx.MockTransport(lambda request: httpx.Response(200, content=b"x" * 262145))
    )
    with pytest.raises(AIUnavailable, match="resource limit"):
        asyncio.run(provider.models())
