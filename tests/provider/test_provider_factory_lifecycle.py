"""Provider ownership contracts for short-lived event-loop consumers."""

from unittest.mock import AsyncMock

import pytest

from siada.provider import provider_factory


@pytest.mark.parametrize("provider_key", ["default"])
def test_create_provider_does_not_reuse_or_replace_shared_instance(
    monkeypatch: pytest.MonkeyPatch, provider_key: str
) -> None:
    class Provider:
        def __init__(self) -> None:
            self.aclose = AsyncMock()

    shared = Provider()
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"default": shared})

    first = provider_factory.create_provider(provider_key)
    second = provider_factory.create_provider(provider_key)

    assert isinstance(first, Provider)
    assert isinstance(second, Provider)
    assert first is not second
    assert first is not shared
    assert second is not shared
    assert provider_factory.get_provider(provider_key) is shared
    shared.aclose.assert_not_called()


def test_create_provider_rejects_unregistered_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {})
    with pytest.raises(ValueError, match="No model providers found or registered"):
        provider_factory.create_provider("missing")
