"""Shared offline environment for the local app and explicit-input CLI."""

import os
import sys
from pathlib import Path

from backend.security.airlock import install_airlock


def configure_offline_environment(root: Path) -> None:
    install_airlock()
    if "onnxruntime" in sys.modules and os.environ.get("ORT_DISABLE_TELEMETRY") != "1":
        raise RuntimeError(
            "Restart this process with ORT_DISABLE_TELEMETRY=1 before loading ONNX Runtime"
        )
    os.environ["ORT_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["DO_NOT_TRACK"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["HF_HOME"] = str(root / "models/huggingface")
    os.environ["FASTEMBED_CACHE_PATH"] = str(root / "models/fastembed")
