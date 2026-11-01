"""Explicit local Ollama launch/verification; no installation, pulls, or config changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def file_digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def verify_runtime(root: Path) -> None:
    inventory = json.loads((root / "vendor/ollama/runtime-files.json").read_text())
    if not isinstance(inventory, dict) or "ollama" not in inventory:
        raise ValueError("Ollama runtime inventory is unavailable")
    for name, digest in inventory.items():
        if Path(name).name != name or file_digest(root / "runtime/ollama" / name) != digest:
            raise ValueError("Ollama runtime checksum mismatch")
    source = root / "vendor/ollama/qwen2.5-3b-manifest.json"
    installed = root / "models/ollama/manifests/registry.ollama.ai/library/qwen2.5/3b"
    if source.read_bytes() != installed.read_bytes():
        raise ValueError("Bundled model manifest mismatch")
    manifest = json.loads(source.read_bytes())
    for layer in [manifest["config"], *manifest["layers"]]:
        digest = layer["digest"]
        if not isinstance(digest, str) or not digest.startswith("sha256:"):
            raise ValueError("Invalid model layer digest")
        expected = digest.removeprefix("sha256:")
        if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
            raise ValueError("Invalid model layer digest")
        path = root / "models/ollama/blobs" / ("sha256-" + expected)
        if path.stat().st_size != layer["size"] or file_digest(path) != expected:
            raise ValueError("Bundled model layer checksum mismatch")


def serve_environment(root: Path, *, cpu: bool) -> dict[str, str]:
    # Preserve the user's home path; official Ollama owns its small identity directory.
    result = {
        name: os.environ[name]
        for name in ("PATH", "HOME", "TMPDIR", "LANG", "USER", "LOGNAME")
        if name in os.environ
    }
    result.update(
        OLLAMA_HOST="127.0.0.1:11434",
        OLLAMA_MODELS=str(root / "models/ollama"),
        OLLAMA_NO_CLOUD="1",
        OLLAMA_NOHISTORY="1",
        OLLAMA_NUM_PARALLEL="1",
        OLLAMA_MAX_LOADED_MODELS="1",
        OLLAMA_CONTEXT_LENGTH="32768",
        OLLAMA_KEEP_ALIVE="5m",
        OLLAMA_DEBUG="false",
        OLLAMA_DEBUG_LOG_REQUESTS="false",
    )
    if cpu:
        result.update(OLLAMA_LLM_LIBRARY="cpu", LLAMA_ARG_DEVICE="none", LLAMA_ARG_KV_OFFLOAD="0")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="Verify cached files and exit")
    parser.add_argument("--cpu", action="store_true", help="Use CPU when Metal is unavailable")
    options = parser.parse_args()
    try:
        verify_runtime(ROOT)
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit("Local AI assets failed verification; no server was started.") from exc
    if options.verify:
        print("Ollama runtime and qwen2.5:3b layers verified. No network request made.")
        return
    executable = ROOT / "runtime/ollama/ollama"
    print("Starting project-local Ollama on 127.0.0.1:11434; cloud disabled.", flush=True)
    os.execve(executable, [str(executable), "serve"], serve_environment(ROOT, cpu=options.cpu))


if __name__ == "__main__":
    main()
