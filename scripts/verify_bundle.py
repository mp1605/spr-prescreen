"""Verify an extracted bundle using only the bundled Python standard library."""

import hashlib
import json
import os
import platform
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(root):
    manifest = json.loads((root / "BUNDLE_MANIFEST.json").read_bytes())
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise ValueError("This bundle targets macOS arm64, Python 3.11.")
    version = platform.mac_ver()[0].split(".")
    if not version or not version[0].isdigit() or int(version[0]) < 14:
        raise ValueError("This wheel bundle requires macOS 14 or later.")
    for name, record in manifest["files"].items():
        path = root / name
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise ValueError("Invalid bundle path")
        if record["kind"] == "symlink":
            if not path.is_symlink() or os.readlink(path) != record["target"]:
                raise ValueError("Bundle link mismatch: " + name)
            if not path.resolve().is_relative_to(root.resolve()):
                raise ValueError("Bundle link escapes its root")
        else:
            if path.is_symlink() or not path.is_file() or path.stat().st_size != record["bytes"]:
                raise ValueError("Bundle file missing or changed: " + name)
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            if digest != record["sha256"]:
                raise ValueError("Bundle checksum mismatch: " + name)
            if record["mode"] & stat.S_IXUSR and not os.access(path, os.X_OK):
                raise ValueError("Executable permission missing: " + name)
    return len(manifest["files"])


if __name__ == "__main__":
    try:
        count = verify(ROOT)
    except (OSError, KeyError, ValueError) as exc:
        raise SystemExit("Bundle verification failed: " + str(exc)) from exc
    print(f"Verified {count} bundled files/links for macOS arm64. No network used.")
