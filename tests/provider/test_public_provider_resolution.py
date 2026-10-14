"""Public-build provider resolution tests.

The open-source build registers a single provider (``default``, the endpoint and
API key the user configured). Provider names left over from another
distribution — most notably the closed-source ``li`` proxy — must resolve to
that provider instead of making LLM tasks fail with "No LLM clients found",
while the ``fast_llm_config`` override keeps working unchanged.

The user endpoint also decides the model ids: a claude / gemini id litellm does
not know (a gateway alias, a newer release) must still report
``supports_reasoning()`` so the user's thinking / reasoning_effort settings are
not dropped on the way to the wire.
"""

import contextlib
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

import siada.config.conf_store as conf_store
from siada.provider import client_factory, fast_llm


@contextlib.contextmanager
def _forbid_private_imports():
    attempted = []

    class _Finder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname == "siada.internal" or fullname.startswith("siada.internal."):
                attempted.append(fullname)
                raise AssertionError(f"unexpected private import: {fullname}")
            return None

    finder = _Finder()
    sys.meta_path.insert(0, finder)
    try:
        yield attempted
    finally:
        sys.meta_path.remove(finder)


@pytest.fixture(autouse=True)
def temp_user_home(tmp_path, monkeypatch):
    monkeypatch.setattr(conf_store, "SIADA_HOME", Path(tmp_path))
    return Path(tmp_path)


@pytest.fixture(autouse=True)
def public_provider_registry(monkeypatch):
    """Mirror this build's provider registry: only the user endpoint exists."""
    provider = MagicMock(name="default_provider")
    provider.get_model.return_value = "model-instance"

    def _get_provider(name=None):
        if name != "default":
            raise ValueError("No model providers found or registered.")
        return provider

    monkeypatch.setattr(fast_llm, "get_provider", _get_provider)
    return provider


def _write_conf(home: Path, data: dict) -> None:
    (home / "conf.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


# --------------------------------------------------------------------------- #
# fast_llm resolution
# --------------------------------------------------------------------------- #
def test_fast_llm_uses_user_config_for_legacy_provider_key(temp_user_home):
    """A legacy ``li`` in conf.yaml must fall back to the user endpoint."""
    _write_conf(
        temp_user_home,
        {"llm_config": {"provider": "li", "model": "claude-sonnet-5", "api_key": "sk-user"}},
    )

    with _forbid_private_imports() as attempted:
        model, provider, call_kwargs = fast_llm._get_fast_model_and_provider()

    assert (model, provider, call_kwargs) == ("claude-sonnet-5", "default", {})
    assert attempted == []


def test_fast_llm_defaults_to_user_endpoint_without_provider(temp_user_home):
    _write_conf(temp_user_home, {"llm_config": {"model": "kimi-k2.5"}})

    model, provider, call_kwargs = fast_llm._get_fast_model_and_provider()

    assert (model, provider, call_kwargs) == ("kimi-k2.5", "default", {})


def test_fast_llm_falls_back_to_framework_default_without_config(temp_user_home):
    from siada.models.model_run_config import ModelRunConfig

    model, provider, call_kwargs = fast_llm._get_fast_model_and_provider()

    assert model == ModelRunConfig.get_default_config().model_name
    assert provider == "default"
    assert call_kwargs == {}


def test_fast_llm_config_override_is_honoured(temp_user_home):
    _write_conf(
        temp_user_home,
        {
            "llm_config": {"provider": "default", "model": "main-model"},
            "fast_llm_config": {
                "provider": "default",
                "model": "fast-model",
                "base_url": "https://fast.example/v1",
                "api_key": "sk-fast",
                "extra_headers": {"X-Gateway": "fast"},
            },
        },
    )

    model, provider, call_kwargs = fast_llm._get_fast_model_and_provider()

    assert model == "fast-model"
    assert provider == "default"
    assert call_kwargs == {
        "api_base": "https://fast.example/v1",
        "api_key": "sk-fast",
        "extra_headers": {"X-Gateway": "fast"},
    }


def test_fast_llm_config_with_legacy_provider_resolves_to_user_endpoint(
    temp_user_home,
):
    _write_conf(
        temp_user_home,
        {
            "llm_config": {"provider": "default", "model": "main-model"},
            "fast_llm_config": {"provider": "li", "model": "fast-model"},
        },
    )

    with _forbid_private_imports():
        model, provider, _ = fast_llm._get_fast_model_and_provider()

    assert (model, provider) == ("fast-model", "default")


def test_fast_llm_config_override_reaches_the_resolved_provider(temp_user_home, monkeypatch):
    """A legacy provider key must not turn the override into a silent no-op.

    Resolution still lands on ``default``; the difference is that the fast model
    is now built with the override credentials instead of the main environment's.
    """
    _write_conf(
        temp_user_home,
        {
            "llm_config": {"provider": "default", "model": "main-model"},
            "fast_llm_config": {
                "provider": "li",
                "model": "fast-model",
                "base_url": "https://fast.example/v1",
                "api_key": "sk-fast",
            },
        },
    )
    captured: dict = {}

    class _RecordingProvider:
        def get_model(self, model_name):
            captured["env_path"] = model_name
            return "env-model"

        def get_model_with_credentials(self, model_name, *, base_url=None, api_key=None):
            captured.update(model=model_name, base_url=base_url, api_key=api_key)
            return "override-model"

    monkeypatch.setattr(fast_llm, "get_provider", lambda name=None: _RecordingProvider())

    with _forbid_private_imports() as attempted:
        model = fast_llm.get_fast_model()

    assert attempted == []
    assert model == "override-model"
    assert "env_path" not in captured
    assert captured == {
        "model": "fast-model",
        "base_url": "https://fast.example/v1",
        "api_key": "sk-fast",
    }


def test_fast_llm_config_without_model_is_ignored(temp_user_home):
    _write_conf(
        temp_user_home,
        {
            "llm_config": {"provider": "default", "model": "main-model"},
            "fast_llm_config": {"provider": "default", "base_url": "https://fast/v1"},
        },
    )

    model, provider, call_kwargs = fast_llm._get_fast_model_and_provider()

    assert (model, provider, call_kwargs) == ("main-model", "default", {})


@pytest.mark.asyncio
async def test_fast_completion_calls_the_resolved_client(temp_user_home, monkeypatch):
    """fast_completion must use the resolved model/provider — never a live call."""
    _write_conf(
        temp_user_home,
        {"llm_config": {"provider": "default", "model": "main-model"}},
    )
    completion = AsyncMock(return_value="response")
    monkeypatch.setattr("siada.provider.one_shot.one_shot_completion", completion)

    result = await fast_llm.fast_completion("write a slug", temperature=0.2)

    assert result == "response"
    call_args, call_kwargs = completion.call_args
    assert call_kwargs["model"] == "main-model"
    assert call_kwargs["provider"] == "default"
    assert call_args == ("write a slug",)
    assert call_kwargs["stream"] is True
    assert call_kwargs["temperature"] == 0.2


def test_get_fast_model_uses_the_user_endpoint_provider(
    temp_user_home, public_provider_registry
):
    _write_conf(
        temp_user_home,
        {"llm_config": {"provider": "li", "model": "claude-sonnet-5"}},
    )

    assert fast_llm.get_fast_model() == "model-instance"
    public_provider_registry.get_model.assert_called_once_with("claude-sonnet-5")


# --------------------------------------------------------------------------- #
# custom claude / gemini capability registration
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("model_name", "wire_name"),
    [
        ("claude-mygateway-1", "anthropic/claude-mygateway-1"),
        ("gemini-9-ultra", "gemini/gemini-9-ultra"),
    ],
    ids=["claude", "gemini"],
)
def test_unknown_claude_or_gemini_id_keeps_reasoning_params_usable(
    model_name, wire_name, monkeypatch
):
    """Public model ids come from the user's gateway, not litellm's catalog.

    Without the capability registration the SDK's ``supports_reasoning()``
    check drops the user's Claude ``thinking`` / Gemini ``reasoning_effort``
    settings for such a model.
    """
    import litellm

    from siada.provider.default.default_provider import DefaultProvider

    monkeypatch.setenv("BASE_URL", "https://main.example/v1")
    monkeypatch.setenv("API_KEY", "sk-main")
    monkeypatch.delitem(litellm.model_cost, wire_name, raising=False)

    try:
        model = DefaultProvider().get_model(model_name)

        assert model.model == wire_name
        assert wire_name in litellm.model_cost
        assert litellm.supports_reasoning(model=wire_name) is True
    finally:
        litellm.model_cost.pop(wire_name, None)


def test_unknown_non_reasoning_model_is_left_alone(monkeypatch):
    """Capability registration is family specific — no speculative claims."""
    import litellm

    from siada.provider.default.default_provider import DefaultProvider

    monkeypatch.setenv("BASE_URL", "https://main.example/v1")
    monkeypatch.setenv("API_KEY", "sk-main")

    model = DefaultProvider().get_model("gateway-7b-instruct")

    assert model.model == "gateway-7b-instruct"
    assert "gateway-7b-instruct" not in litellm.model_cost
    assert litellm.supports_reasoning(model="gateway-7b-instruct") is False


def test_known_model_keeps_litellm_capability_data():
    """For ids litellm already ships, the registry stays authoritative."""
    import litellm

    from siada.provider.default.default_provider import _register_custom_claude_model

    candidates = [
        name
        for name, info in litellm.model_cost.items()
        if "claude" in name and not info.get("supports_reasoning")
    ]
    if not candidates:
        pytest.skip("litellm no longer ships a claude id without reasoning support")
    known = candidates[0]
    snapshot = dict(litellm.model_cost[known])

    _register_custom_claude_model(known)

    assert litellm.model_cost[known] == snapshot
    assert litellm.supports_reasoning(model=known) is False


# --------------------------------------------------------------------------- #
# client_factory resolution
# --------------------------------------------------------------------------- #
def test_only_the_user_endpoint_provider_is_registered():
    """No closed-source provider client may be registered in this build."""
    assert "default" in client_factory.client_map
    assert "li" not in client_factory.client_map


def test_default_provider_returns_the_registered_client():
    client = client_factory.get_client("default")

    assert client is client_factory.client_map["default"]
    assert isinstance(client, client_factory.LLMClient)


@pytest.mark.parametrize("provider_name", ["li", "openai_agents", "unknown-provider"])
def test_unavailable_provider_falls_back_to_user_endpoint(provider_name, monkeypatch):
    """No provider key may crash the CLI; everything resolves to ``default``."""
    fake_logger = MagicMock()
    monkeypatch.setattr(client_factory, "logger", fake_logger)
    monkeypatch.setattr(client_factory, "_unknown_providers_warned", set())

    with _forbid_private_imports() as attempted:
        client = client_factory.get_client(provider_name)

    assert client is client_factory.client_map["default"]
    assert attempted == []
    assert fake_logger.warning.call_count == 1

    # The warning is emitted once per unknown provider name, not per request.
    client_factory.get_client(provider_name)
    assert fake_logger.warning.call_count == 1


def test_missing_provider_name_returns_the_default_client():
    assert client_factory.get_client(None) is client_factory.client_map["default"]


def test_no_registered_client_still_raises(monkeypatch):
    monkeypatch.setattr(client_factory, "client_map", {})

    with pytest.raises(ValueError):
        client_factory.get_client("default")


def test_get_client_with_kwargs_uses_context_model_and_default_client(monkeypatch):
    llm_config = SimpleNamespace(model_name="kimi-k2.5", provider="li")
    monkeypatch.setattr(client_factory, "get_context_var", lambda key: llm_config)

    with _forbid_private_imports():
        client, complete_kwargs = client_factory.get_client_with_kwargs(
            {"messages": [{"role": "user", "content": "hi"}]}
        )

    assert client is client_factory.client_map["default"]
    assert complete_kwargs["model"] == "kimi-k2.5"