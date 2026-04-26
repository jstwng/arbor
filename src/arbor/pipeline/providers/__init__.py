"""Provider registry."""
from __future__ import annotations

from .anthropic import AnthropicPlugin
from .base import Plugin
from .gemini import GeminiPlugin
from .openai import OpenAIPlugin
from .openai_compat import OpenAICompatPlugin


PROVIDERS: dict[str, type[Plugin]] = {
    "gemini": GeminiPlugin,
    "anthropic": AnthropicPlugin,
    "openai": OpenAIPlugin,
    "openai_compat": OpenAICompatPlugin,
}


def get_plugin(name: str, config: dict | None = None) -> Plugin:
    if name not in PROVIDERS:
        raise ValueError(
            f"Unknown provider: {name!r}. Available: {sorted(PROVIDERS)}"
        )
    cls = PROVIDERS[name]
    if name == "openai_compat" and config is not None:
        base_url = (
            config.get("providers", {}).get("openai_compat", {}).get("base_url")
        )
        return cls(base_url=base_url)
    return cls()
