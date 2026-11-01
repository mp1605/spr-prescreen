"""Official-text and numerical fixtures; no sponsor or generated-paper corpus."""

import numpy as np
import pytest

from backend.core.engines.semantic import SemanticEngine
from backend.core.settings import load_settings
from tests.conftest import ROOT
from tests.screen import conftest as screen_fixtures

atom_document = screen_fixtures.atom_document
registry = screen_fixtures.registry


class NumericProvider:
    identity = "a" * 64

    def __init__(self, registry):
        self.texts = tuple(item.text for item in (*registry.list1, *registry.list2))
        self.references = np.eye(384, dtype=np.float32)[:39]
        self.calls = []
        self.paper_vectors = None
        self.failure = False

    def chunks(self, text):
        return (text,)

    def embed(self, texts):
        self.calls.append(tuple(texts))
        if self.failure:
            raise RuntimeError("PRIVATE SOURCE MUST NOT BE LOGGED")
        if tuple(texts) == self.texts:
            return self.references.copy()
        if self.paper_vectors is not None:
            return self.paper_vectors.copy()
        return np.stack(
            [
                self.references[self.texts.index(text)]
                if text in self.texts
                else np.eye(384, dtype=np.float32)[383]
                for text in texts
            ]
        )


@pytest.fixture
def host(registry, tmp_path):
    provider = NumericProvider(registry)
    return SemanticEngine(tmp_path, registry, load_settings(ROOT).semantic, provider=provider)
