"""Contract tests for the dynamic model-provider registry."""

from unittest.mock import AsyncMock, MagicMock, sentinel

import pytest

from siada.provider import provider_factory


class _StatelessProvider:
    """Provider that owns no async resources (exposes no ``aclose``)."""


def test_get_provider_returns_named_provider(monkeypatch: pytest.MonkeyPatch):
    providers = {"first": sentinel.first, "second": sentinel.second}
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", providers)

    assert provider_factory.get_provider("second") is sentinel.second


def test_get_provider_defaults_to_first_registered_provider(monkeypatch: pytest.MonkeyPatch):
    """``get_provider()`` without a name returns the first registered provider.

    The 1.7.32 subagent provider-inheritance change restored this fallback
    (model-only overrides inherit the active provider), so the public build
    now matches the source contract documented in the port of 18814a58.
    """
    providers = {"first": sentinel.first, "second": sentinel.second}
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", providers)

    assert provider_factory.get_provider() is sentinel.first


def test_get_provider_reports_empty_provider_registry(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {})

    with pytest.raises(ValueError, match="No model providers found or registered"):
        provider_factory.get_provider()


def test_get_provider_reports_unsupported_provider(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(provider_factory, "_discover_providers", lambda: None)
    monkeypatch.setattr(provider_factory, "provider_map", {"default": sentinel.default})

    with pytest.raises(
        ValueError,
        match="Unsupported model provider 'missing'. Available providers: default.",
    ):
        provider_factory.get_provider("missing")


@pytest.mark.asyncio
async def test_aclose_providers_closes_providers_and_skips_stateless_ones(
    monkeypatch: pytest.MonkeyPatch,
):
    closing = MagicMock()
    closing.aclose = AsyncMock()
    monkeypatch.setattr(provider_factory, "_providers_discovered", True)
    monkeypatch.setattr(
        provider_factory,
        "provider_map",
        {"default": closing, "stateless": _StatelessProvider()},
    )

    await provider_factory.aclose_providers()

    closing.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_aclose_providers_awaits_all_providers_before_reraising_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    awaited: list[str] = []

    class FailingProvider:
        async def aclose(self) -> None:
            awaited.append("failing")
            raise OSError("provider close failed")

    class HealthyProvider:
        async def aclose(self) -> None:
            awaited.append("healthy")

    monkeypatch.setattr(provider_factory, "_providers_discovered", True)
    monkeypatch.setattr(
        provider_factory,
        "provider_map",
        {"failing": FailingProvider(), "healthy": HealthyProvider()},
    )

    with pytest.raises(OSError, match="provider close failed"):
        await provider_factory.aclose_providers()

    assert awaited == ["failing", "healthy"]


@pytest.mark.asyncio
async def test_aclose_providers_aggregates_failures_into_exception_group(
    monkeypatch: pytest.MonkeyPatch,
):
    awaited: list[str] = []

    class FirstFailingProvider:
        async def aclose(self) -> None:
            awaited.append("first")
            raise OSError("first close failed")

    class SecondFailingProvider:
        async def aclose(self) -> None:
            awaited.append("second")
            raise RuntimeError("second close failed")

    class HealthyProvider:
        async def aclose(self) -> None:
            awaited.append("healthy")

    monkeypatch.setattr(provider_factory, "_providers_discovered", True)
    monkeypatch.setattr(
        provider_factory,
        "provider_map",
        {
            "first": FirstFailingProvider(),
            "second": SecondFailingProvider(),
            "healthy": HealthyProvider(),
        },
    )

    with pytest.raises(ExceptionGroup) as excinfo:
        await provider_factory.aclose_providers()

    assert excinfo.value.message == "Failed to close one or more model providers"
    assert {type(error) for error in excinfo.value.exceptions} == {OSError, RuntimeError}
    assert awaited == ["first", "second", "healthy"]


@pytest.mark.asyncio
async def test_aclose_providers_is_noop_before_discovery(
    monkeypatch: pytest.MonkeyPatch,
):
    provider = MagicMock()
    provider.aclose = AsyncMock()
    monkeypatch.setattr(provider_factory, "_providers_discovered", False)
    monkeypatch.setattr(provider_factory, "provider_map", {"default": provider})

    await provider_factory.aclose_providers()

    provider.aclose.assert_not_awaited()