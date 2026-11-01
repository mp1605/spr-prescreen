"""Startup checks read declared configuration/assets, never recover or discover paper runs."""

from pathlib import Path

from backend.core.assets import model_status
from backend.core.rules_loader import PolicyError, load_rules
from backend.core.runtime import configure_offline_environment
from backend.core.settings import Settings, load_settings


def validate_setup(root: Path) -> Settings:
    configure_offline_environment(root)
    settings = load_settings(root)
    load_rules(root)
    if not (root / "backend/static/index.html").is_file():
        raise PolicyError("Frontend build missing; restore the prepared offline bundle.")
    assets = model_status(root, verify_hashes=True)
    if not assets.ready:
        raise PolicyError(assets.message)
    return settings
