"""Bundle only application code and declared assets; never walk data/run/private stores."""

import json
import os
from collections.abc import Iterator
from pathlib import Path

EXCLUDE = {
    "__pycache__",
    "node_modules",
    ".cache",
    ".git",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".DS_Store",
}
DIRECTORIES = (
    "backend",
    "frontend/src",
    "runtime/python3.11",
    "runtime/LibreOfficeDev.app",
    "runtime/ollama",
    "scripts",
    "tests",
)
FILES = (
    "README.md",
    ".gitignore",
    "MASTER_PROMPT.md",
    "requirements.txt",
    "requirements.in",
    "pyproject.toml",
    "run.sh",
    "install.sh",
    "docs/AUTHORITY.md",
    "docs/OFFLINE_VERIFICATION.md",
    "docs/official-lists.pdf",
    "docs/policy-baseline.json",
    "policies/official_rules.yaml",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/index.html",
    "frontend/vite.config.ts",
    "frontend/tailwind.config.js",
    "frontend/postcss.config.cjs",
    "frontend/tsconfig.json",
    "frontend/eslint.config.js",
)


def declared(root: Path) -> Iterator[Path]:
    model_manifest = root / "models/manifest.json"
    if model_manifest.is_file():
        yield model_manifest
        for item in json.loads(model_manifest.read_bytes())["assets"]:
            name = item["path"]
            if (
                not isinstance(name, str)
                or not name.startswith("models/")
                or ".." in Path(name).parts
            ):
                raise ValueError("Invalid declared model path")
            yield root / name
    wheel_manifest = root / "vendor/manifest.json"
    if wheel_manifest.is_file():
        yield wheel_manifest
        for item in json.loads(wheel_manifest.read_bytes())["files"]:
            name = item["file"]
            if not isinstance(name, str) or Path(name).name != name or not name.endswith(".whl"):
                raise ValueError("Invalid declared wheel path")
            yield root / "vendor" / name
    model = root / "models/ollama/manifests/registry.ollama.ai/library/qwen2.5/3b"
    if model.is_file():
        yield model
        record = json.loads(model.read_bytes())
        for layer in [record["config"], *record["layers"]]:
            digest = layer["digest"]
            value = digest.removeprefix("sha256:")
            if (
                not digest.startswith("sha256:")
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise ValueError("Invalid declared model layer")
            yield root / "models/ollama/blobs" / digest.replace(":", "-")
    for name in (
        "release.json",
        "runtime-files.json",
        "qwen2.5-3b-manifest.json",
        "QWEN2.5-3B-LICENSE.txt",
        "OLLAMA-LICENSE.txt",
        "ollama-darwin-v0.40.13.tgz",
    ):
        path = root / "vendor/ollama" / name
        if path.is_file():
            yield path


def sources(root: Path) -> Iterator[Path]:
    for directory in DIRECTORIES:
        for parent, dirs, files in os.walk(root / directory, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE and not d.startswith("._"))
            for name in list(dirs):
                path = Path(parent) / name
                if path.is_symlink():
                    dirs.remove(name)
                    yield path
            for name in sorted(files):
                path = Path(parent) / name
                relative = path.relative_to(root).as_posix()
                if (
                    name.startswith("._")
                    or name in EXCLUDE
                    or name.endswith((".pyc", ".log", ".partial", ".lock"))
                ):
                    continue
                if directory in {"tests", "scripts"} and path.suffix not in {".py", ".sh", ".mjs"}:
                    continue
                if (
                    directory == "backend"
                    and not relative.startswith("backend/static/")
                    and path.suffix not in {".py", ".pyi"}
                ):
                    continue
                yield path
    for name in FILES:
        path = root / name
        if path.is_file():
            yield path
    yield from declared(root)
