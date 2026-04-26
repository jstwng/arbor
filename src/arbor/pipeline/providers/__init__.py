"""Provider registry."""
from __future__ import annotations

from .base import Plugin
from .gemini import GeminiPlugin

PROVIDERS: dict[str, type] = {
    "gemini": GeminiPlugin,
}


def get_plugin(name: str) -> Plugin:
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider: {name!r}. Available: {sorted(PROVIDERS)}"
        )
    return PROVIDERS[name]()
