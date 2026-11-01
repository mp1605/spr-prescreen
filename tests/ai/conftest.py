"""Official policy phrases and coordinate/format contracts, never a narrative paper corpus."""

import asyncio
import json

import pytest

from backend.core.engines.ollama import LocalModel
from backend.core.settings import AISettings
from backend.core.specificity import SpecificityEngine
from tests.conftest import ROOT
from tests.screen import conftest as source_fixtures

registry = source_fixtures.registry
atom_document = source_fixtures.atom_document
MODEL = "contract-only:local"
DIGEST = "a" * 64


class ContractProvider:
    def __init__(self, values=None, *, raw=None, delay=0, error=False):
        self.values = values or []
        self.raw = raw
        self.delay = delay
        self.error = error
        self.calls = []
        self.active = 0
        self.maximum = 0
        self.digest = DIGEST
        self.limit = 32768

    async def models(self):
        if self.error:
            raise OSError("Loopback service unavailable")
        return (LocalModel(name=MODEL, digest=self.digest, bytes=1024),)

    async def context_limit(self, model):
        return self.limit

    async def complete(self, payload):
        self.calls.append(payload)
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return {
                "model": MODEL,
                "done": True,
                "done_reason": "stop",
                "prompt_eval_count": 100,
                "message": {
                    "content": self.raw if self.raw is not None else json.dumps(self.values)
                },
            }
        finally:
            self.active -= 1


@pytest.fixture
def ai_settings():
    return AISettings(
        enabled=True,
        model=MODEL,
        model_digest=DIGEST,
        endpoint="http://127.0.0.1:11434",
        timeout_seconds=5,
    )


@pytest.fixture
def assessor(registry):
    return SpecificityEngine(ROOT, registry, use_local_entities=False)


def proposal(quote="Animal testing", item="L2-01", kind="possible"):
    return {
        "quote": quote,
        "item_id": item,
        "clear_or_possible": kind,
        "reason": "Official-wording source-binding contract; applicability not measured.",
    }
