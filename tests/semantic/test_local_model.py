import io
import os
import socket
import subprocess
import sys

import pytest
from docx import Document

from backend.core.engines.local_bge import LocalBGE
from backend.core.engines.semantic import SemanticEngine
from backend.core.ingest import parse_document
from backend.core.runtime import configure_offline_environment
from backend.core.screen import screen_document
from backend.core.settings import load_settings
from tests.conftest import ROOT


@pytest.mark.models
def test_real_pipeline_offline_source_bound_and_no_dataset_discovery(
    registry, tmp_path, monkeypatch
):
    configure_offline_environment(ROOT)

    def blocked(*args, **kwargs):
        pytest.fail("Semantic inference attempted network or corpus discovery")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(type(tmp_path), "glob", blocked)
    document = Document()
    for item in (*registry.list1, *registry.list2):
        document.add_paragraph(item.text)
    output = io.BytesIO()
    document.save(output)
    parsed = parse_document("official-wording.docx", output.getvalue())
    host = SemanticEngine(tmp_path, registry, load_settings(ROOT).semantic, provider=LocalBGE(ROOT))
    result = screen_document(parsed, registry, semantic=host.session())
    assert result.semantic.state == "complete" and result.semantic.chunks == 39
    assert {ref.item_id for finding in result.findings for ref in finding.semantic_matches} == {
        item.id for item in host.items
    }
    for finding in result.findings:
        unit = next(unit for unit in parsed.units if unit.paragraph == finding.location.paragraph)
        assert unit.text[finding.location.char_start : finding.location.char_end] == finding.quote
        assert finding.nearest_exemplar is None
    assert all(f.color == "yellow" for f in result.findings if f.list == "list2")


def test_long_text_windows_cover_tail_without_truncation(semantic_provider):
    text = "Animal testing " * 700 + "Deployment schedules or locations"
    pieces = semantic_provider.chunks(text)
    assert len(pieces) > 1 and pieces[-1].endswith("Deployment schedules or locations")
    assert all(
        len(semantic_provider.tokenizer.encode(piece, add_special_tokens=False).ids) <= 510
        for piece in pieces
    )


def test_missing_assets_fail_locally_before_loading_fastembed(tmp_path):
    with pytest.raises(ValueError, match="unavailable"):
        LocalBGE(tmp_path)


def test_fresh_process_disables_native_telemetry_before_onnx_import():
    environment = dict(os.environ)
    environment.pop("ORT_DISABLE_TELEMETRY", None)
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import os, sys
from pathlib import Path
from backend.core.engines.local_bge import LocalBGE
assert 'onnxruntime' not in sys.modules
model = LocalBGE(Path.cwd())
assert os.environ['ORT_DISABLE_TELEMETRY'] == '1'
assert model.embed(['Animal testing']).shape == (1, 384)
print('native telemetry disabled before import')
""",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert process.returncode == 0, process.stderr
    assert "native telemetry disabled before import" in process.stdout
    assert "telemetry_1ds" not in process.stderr and "NetworkStorageDB" not in process.stderr


def test_late_telemetry_configuration_requires_restart(monkeypatch):
    monkeypatch.setitem(sys.modules, "onnxruntime", object())
    monkeypatch.delenv("ORT_DISABLE_TELEMETRY", raising=False)
    with pytest.raises(RuntimeError, match="Restart"):
        configure_offline_environment(ROOT)
