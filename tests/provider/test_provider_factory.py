from unittest.mock import sentinel

import pytest

from siada.provider import provider_factory


def test_get_provider_defaults_to_first_registered_provider(monkeypatch: pytest.MonkeyPatch):
    providers = {"first": sentinel.first, "second": sentinel.second}
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", providers)

    assert provider_factory.get_provider() is sentinel.first


def test_get_provider_returns_named_provider(monkeypatch: pytest.MonkeyPatch):
    providers = {"first": sentinel.first, "second": sentinel.second}
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", providers)

    assert provider_factory.get_provider("second") is sentinel.second


def test_get_provider_normalizes_legacy_provider_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"default": sentinel.default})

    assert provider_factory.get_provider("openai_agents") is sentinel.default


def test_get_provider_reports_empty_provider_registry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {})

    with pytest.raises(ValueError, match="No model providers found or registered"):
        provider_factory.get_provider()


def test_get_provider_reports_unsupported_provider(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"li": sentinel.li})

    with pytest.raises(ValueError, match="Unsupported model provider 'missing'.*li"):
        provider_factory.get_provider("missing")
