"""Packaging boundaries and corruption checks use file/metadata atoms only."""

import hashlib
import importlib.util
import json

import pytest

from tests.conftest import ROOT


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_sources_never_visit_private_stores(tmp_path):
    module = script("make_bundle")
    for name in [
        "backend/app.py",
        "backend/._metadata.py",
        "runs/retained/source.bin",
        "data/private.bin",
        "config/admin.json",
        "reports/local.json",
        "policies/drafts/private.json",
        "frontend/node_modules/private.js",
        "vendor/visible.whl",
    ]:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"metadata atom")
    (tmp_path / "vendor/manifest.json").write_text(json.dumps({"files": [{"file": "visible.whl"}]}))
    names = {p.relative_to(tmp_path).as_posix() for p in module.sources(tmp_path)}
    assert names == {"backend/app.py", "vendor/visible.whl", "vendor/manifest.json"}


def test_bundle_rejects_a_symlink_outside_root(tmp_path, monkeypatch):
    module = script("make_bundle")
    root = tmp_path / "source"
    (root / "backend").mkdir(parents=True)
    (root / "backend/link.py").symlink_to(tmp_path / "outside")
    monkeypatch.setattr(module, "sanitized", lambda root: {})
    with pytest.raises(ValueError, match="Nonportable"):
        module.build(root, tmp_path / "bundle.zip")
    assert not (tmp_path / "bundle.zip").exists()


def test_bundle_verifier_detects_modified_file_and_escaping_link(tmp_path, monkeypatch):
    module = script("verify_bundle")
    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(module.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(module.platform, "mac_ver", lambda: ("14.0", (), "arm64"))
    source = tmp_path / "source.py"
    source.write_bytes(b"format atom")
    link = tmp_path / "link"
    link.symlink_to("source.py")
    data = {
        "files": {
            "source.py": {
                "kind": "file",
                "bytes": 11,
                "mode": 0o600,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            },
            "link": {"kind": "symlink", "target": "source.py"},
        }
    }
    (tmp_path / "BUNDLE_MANIFEST.json").write_text(json.dumps(data))
    assert module.verify(tmp_path) == 2
    source.write_bytes(b"changed atom")
    with pytest.raises(ValueError, match="changed"):
        module.verify(tmp_path)
