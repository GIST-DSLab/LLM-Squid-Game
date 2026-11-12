import pytest
from squid_game.models.config import ProviderConfig
from squid_game.providers.factory import build_provider
from squid_game.providers.gemini import GeminiProvider


def test_build_provider_returns_gemini_for_gemini_config(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    cfg = ProviderConfig(provider="gemini", model="gemini-2.5-flash",
                         api_key_env="GEMINI_API_KEY")
    provider = build_provider(cfg)
    assert isinstance(provider, GeminiProvider)
    assert provider.model_name == "gemini-2.5-flash"


def test_build_provider_rejects_unknown_provider():
    cfg = ProviderConfig(provider="does-not-exist", model="x",
                         api_key_env="NONE")
    with pytest.raises(ValueError, match="Unknown provider"):
        build_provider(cfg)
