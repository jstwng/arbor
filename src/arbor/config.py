"""User-editable configuration: providers, models, themes, defaults.

Stored at ``~/.config/arbor/config.json``. Auto-created on first run
with sensible defaults. ``GEMINI_API_KEY`` from a project-local ``.env`` is
auto-migrated into the config on first run so existing setups keep working.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path.home() / ".config" / "arbor"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Legacy path -- earlier releases stored config under a different name.
# Kept for one-shot migration on first arbor run.
LEGACY_CONFIG_DIR = Path.home() / ".config" / "mindbranches"
LEGACY_CONFIG_PATH = LEGACY_CONFIG_DIR / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "providers": {
        "gemini": {"api_key": ""},
    },
    "models": [
        {
            "id": "gemini-2.5-flash",
            "label": "Gemini 2.5 Flash",
            "provider": "gemini",
            "default": True,
        },
        {
            "id": "gemini-2.5-flash-lite",
            "label": "Gemini 2.5 Flash-Lite",
            "provider": "gemini",
        },
        {
            "id": "gemini-2.5-pro",
            "label": "Gemini 2.5 Pro",
            "provider": "gemini",
        },
        {
            "id": "gemini-2.0-flash",
            "label": "Gemini 2.0 Flash",
            "provider": "gemini",
        },
    ],
    "themes": [
        {"id": "cream", "label": "Cream", "default": True},
        {"id": "dark", "label": "Dark"},
        {"id": "mono", "label": "Mono"},
    ],
    "defaults": {
        "width": 1600,
    },
}


def _migrate_from_env(config: dict[str, Any]) -> bool:
    """If config has no Gemini key but the environment / .env has one, copy it.

    Returns True if the config was mutated.
    """
    gemini = config.setdefault("providers", {}).setdefault("gemini", {})
    if gemini.get("api_key"):
        return False

    # 1. Already exported in the shell environment
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        gemini["api_key"] = env_key
        return True

    # 2. .env in the current working directory or anywhere up the tree
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        env_path = parent / ".env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("GEMINI_API_KEY="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        gemini["api_key"] = value
                        return True
            break

    return False


def load_config() -> dict[str, Any]:
    """Load config from disk, creating defaults + migrating env on first run."""
    if not CONFIG_PATH.exists():
        # First run -- carry over a legacy config if one exists.
        if LEGACY_CONFIG_PATH.exists():
            try:
                config = json.loads(LEGACY_CONFIG_PATH.read_text())
                _migrate_from_env(config)
                save_config(config)
                return config
            except Exception:
                pass
        config = copy.deepcopy(DEFAULT_CONFIG)
        _migrate_from_env(config)
        save_config(config)
        return config

    config = json.loads(CONFIG_PATH.read_text())

    # Heal: ensure every default top-level section is present.
    mutated = False
    for key, default_value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = copy.deepcopy(default_value)
            mutated = True

    if _migrate_from_env(config):
        mutated = True

    if mutated:
        save_config(config)
    return config


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


def public_config(config: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with secrets stripped and provider key-presence flags added.

    Suitable for sending to the browser frontend.
    """
    out = copy.deepcopy(config)
    providers = out.get("providers", {})
    for name, provider in providers.items():
        provider["has_key"] = bool(provider.get("api_key"))
        provider.pop("api_key", None)
    return out


def get_model(config: dict[str, Any], model_id: str) -> dict[str, Any]:
    for m in config.get("models", []):
        if m["id"] == model_id:
            return m
    raise ValueError(
        f"Unknown model id: {model_id!r}. Available: "
        f"{[m['id'] for m in config.get('models', [])]}"
    )


def default_model_id(config: dict[str, Any]) -> str:
    for m in config.get("models", []):
        if m.get("default"):
            return m["id"]
    models = config.get("models", [])
    if not models:
        raise RuntimeError("Config has no models defined.")
    return models[0]["id"]


def default_theme_id(config: dict[str, Any]) -> str:
    for t in config.get("themes", []):
        if t.get("default"):
            return t["id"]
    themes = config.get("themes", [])
    if not themes:
        return "cream"
    return themes[0]["id"]


def provider_api_key(config: dict[str, Any], provider: str) -> str:
    return config.get("providers", {}).get(provider, {}).get("api_key", "")
