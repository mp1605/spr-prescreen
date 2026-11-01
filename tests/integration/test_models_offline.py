import socket
from pathlib import Path

import pytest

from backend.core.assets import model_status

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.models
def test_models_run_from_disk_without_python_network_access(monkeypatch):
    # Inference checks use only official rule text. This is not an accuracy test.
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("ORT_DISABLE_TELEMETRY", "1")
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "1")
    monkeypatch.setenv("HF_HOME", str(ROOT / "models/huggingface"))

    def blocked(*args, **kwargs):
        raise AssertionError("Offline model inference attempted network access")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    import onnxruntime

    onnxruntime.disable_telemetry_events()
    import spacy
    from fastembed import TextEmbedding

    assert model_status(ROOT, verify_hashes=True).ready
    model = TextEmbedding(
        model_name="BAAI/bge-small-en-v1.5",
        cache_dir=str(ROOT / "models/fastembed"),
        local_files_only=True,
        threads=2,
    )
    assert next(model.embed(["Animal testing"])).shape == (384,)
    nlp = spacy.load(ROOT / "models/spacy/en_core_web_sm")
    assert len(nlp("Deployment schedules or locations")) == 4


@pytest.mark.models
def test_specificity_optional_ner_uses_cached_model_without_python_network(monkeypatch):
    from backend.core.named_entities import LocalEntities
    from backend.core.runtime import configure_offline_environment

    configure_offline_environment(ROOT)

    def blocked(*args, **kwargs):
        raise AssertionError("Entity model attempted network access")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    provider = LocalEntities(ROOT)
    text = "DoD information from Washington D.C."
    entities = provider.entities(text)
    assert len(provider.identity) == 64
    assert all(0 <= entity.start < entity.end <= len(text) for entity in entities)
    assert any(entity.kind == "location" for entity in entities)
