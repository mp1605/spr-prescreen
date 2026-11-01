"""Validate configuration/assets without reading or recovering the run store."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.boot import validate_setup  # noqa: E402

if sys.version_info[:2] != (3, 11):
    raise SystemExit("Python 3.11 is required for this offline dependency bundle.")
validate_setup(ROOT)
print("M10 startup checks passed: official lists, local model hashes and built frontend.")
