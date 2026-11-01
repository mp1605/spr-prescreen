import shutil
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.engines.local_bge import LocalBGE
from backend.core.runtime import configure_offline_environment

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    for directory in ("config", "policies", "docs", "backend/static"):
        shutil.copytree(
            ROOT / directory,
            tmp_path / directory,
            ignore=shutil.ignore_patterns("admin.json"),
        )
    # User-saved AI defaults must not make contract tests call a real local LLM.
    settings_path = tmp_path / "config/settings.yaml"
    settings = yaml.safe_load(settings_path.read_text())
    settings["ai"]["enabled"] = False
    settings["ai"]["model_digest"] = None
    settings_path.write_text(yaml.safe_dump(settings, sort_keys=False))
    return tmp_path


@pytest.fixture(scope="session")
def semantic_provider():
    configure_offline_environment(ROOT)
    return LocalBGE(ROOT)


@pytest.fixture
def client(project_root: Path, semantic_provider):
    with TestClient(
        create_app(project_root, semantic_provider=semantic_provider), base_url="http://127.0.0.1"
    ) as test_client:
        yield test_client
