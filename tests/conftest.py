import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.core.engines.local_bge import LocalBGE
from backend.core.runtime import configure_offline_environment

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    for directory in ("config", "policies", "docs", "backend/static"):
        shutil.copytree(ROOT / directory, tmp_path / directory)
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
