"""Package only declared application assets, excluding user data and credentials."""

import argparse
import hashlib
import json
import os
import stat
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = "spr-prescreen"
sys.path.insert(0, str(ROOT))
from backend.bundle_paths import sources  # noqa: E402


def sanitized(root):
    sys.path.insert(0, str(root))
    from backend.boot import validate_setup
    from backend.core.rules_loader import load_rules
    from backend.local_ai import verify_runtime

    verify_runtime(root)
    settings = validate_setup(root)
    rules = load_rules(root)
    import yaml

    configuration = settings.model_dump()
    configuration["ai"].update(enabled=False, model_digest=None)
    now = datetime.now(UTC).isoformat()
    digest = hashlib.sha256((root / "policies/official_rules.yaml").read_bytes()).hexdigest()
    active = {
        "version": rules.policy_version,
        "sha256": digest,
        "published_by": "Offline bundle baseline",
        "utc": now,
        "change_note": "Current verified rules packaged without user histories or credentials.",
    }
    event = {
        "event_id": "bundle-baseline-" + digest,
        "action": "bundle_baseline",
        "version": rules.policy_version,
        "sha256": digest,
        "admin": "Offline bundle baseline",
        "utc": now,
    }
    return {
        "config/settings.yaml": yaml.safe_dump(configuration, sort_keys=False).encode(),
        "policies/active.json": (json.dumps(active, indent=2) + "\n").encode(),
        "policies/audit.log": (json.dumps(event) + "\n").encode(),
        "policies/versions/rules_v1.yaml": (root / "policies/official_rules.yaml").read_bytes(),
    }


def build(root, destination):
    generated = sanitized(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".partial")
    records = {}
    try:
        with zipfile.ZipFile(
            temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3, allowZip64=True
        ) as archive:
            for path in sorted(set(sources(root))):
                name = path.relative_to(root).as_posix()
                if name in generated:
                    continue
                if path.is_symlink():
                    target = os.readlink(path)
                    if Path(target).is_absolute() or not path.resolve().is_relative_to(root):
                        raise ValueError("Nonportable symbolic link: " + name)
                    info = zipfile.ZipInfo(TOP + "/" + name)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, target)
                    records[name] = {"kind": "symlink", "target": target}
                else:
                    info = path.stat()
                    compression = (
                        zipfile.ZIP_STORED
                        if info.st_size > 32 * 1024**2 or path.suffix in {".whl", ".tgz", ".zip"}
                        else zipfile.ZIP_DEFLATED
                    )
                    archive.write(path, TOP + "/" + name, compress_type=compression)
                    with path.open("rb") as handle:
                        digest = hashlib.file_digest(handle, "sha256").hexdigest()
                    records[name] = {
                        "kind": "file",
                        "bytes": info.st_size,
                        "sha256": digest,
                        "mode": stat.S_IMODE(info.st_mode),
                    }
            for name, data in generated.items():
                info = zipfile.ZipInfo(TOP + "/" + name)
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                archive.writestr(info, data)
                records[name] = {
                    "kind": "file",
                    "bytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "mode": 0o600,
                }
            manifest = {
                "format": "spr-offline-bundle-v1",
                "platform": "macOS arm64",
                "minimum_macos": 14,
                "python": "3.11",
                "ai_enabled": False,
                "excluded": [
                    "runs",
                    "data",
                    "reports",
                    "admin credentials",
                    "review decisions",
                    "drafts",
                    "source policy audit history",
                    ".venv",
                    "node_modules",
                ],
                "files": records,
            }
            archive.writestr(TOP + "/BUNDLE_MANIFEST.json", json.dumps(manifest, indent=2) + "\n")
        temporary.replace(destination)
        with destination.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        destination.with_suffix(destination.suffix + ".sha256").write_text(
            digest + "  " + destination.name + "\n"
        )
        print(
            f"Bundle created: {destination} "
            f"({destination.stat().st_size} bytes, {len(records)} files/links)"
        )
        print("SHA-256: " + digest)
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist/spr-prescreen-M10-macos-arm64.zip"
    )
    arguments = parser.parse_args()
    build(ROOT, arguments.output.resolve())
