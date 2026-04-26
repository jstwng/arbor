"""GeminiPlugin shape test (no live call)."""
from arbor.pipeline.providers import PROVIDERS, get_plugin
from arbor.pipeline.providers.gemini import GeminiPlugin


def test_gemini_registered():
    assert "gemini" in PROVIDERS
    assert PROVIDERS["gemini"] is GeminiPlugin


def test_get_plugin_returns_instance():
    plugin = get_plugin("gemini")
    assert plugin.name == "gemini"
    assert callable(plugin.extract)
    assert callable(plugin.extract_stream)


def test_get_plugin_unknown_raises():
    import pytest
    with pytest.raises(ValueError, match="Unknown provider"):
        get_plugin("does-not-exist")
