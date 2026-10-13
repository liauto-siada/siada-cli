"""``fast_llm_config`` override coverage for the public default provider.

The audit behind this file found that the ``fast_llm_config`` override was only
half wired: ``get_fast_model`` / ``build_fast_run_config`` resolved the fast
model through the provider's environment-driven ``get_model`` (silently
dropping the override endpoint/key), and ``DefaultClient.completion`` re-applied
the main BASE_URL / API_KEY on top of the explicit per-call kwargs, so even the
``fast_completion`` override lost.

These tests pin the fixed behaviour:

* the override endpoint/key win over the main BASE_URL / API_KEY environment,
  and a partial override keeps the main value for the fields it does not set;
* ``build_fast_run_config`` hands the Runner a Model *instance* carrying those
  credentials (input-processing wrapper intact, unlike a bare model) and puts
  the override ``extra_headers`` on ``ModelSettings`` — the model constructors
  take only model / endpoint / key;
* precedence is explicit per-call kwargs > ``fast_llm_config`` > main env;
* no fast path writes process-global credentials: an override never mutates
  BASE_URL / API_KEY / DEEPSEEK_API_KEY / MOONSHOT_API_KEY, so a main-endpoint
  request issued straight after (or concurrently) still uses the main pair;
* an override that cannot be honoured raises a clear error instead of being
  silently ignored (provider without explicit-credential support;
  ``get_fast_model`` asked to carry ``extra_headers``, which only
  ``ModelSettings`` / per-call kwargs can hold; Responses-API-only models whose
  transport reads the environment);
* without an override nothing changes (string model + ModelProviderWrapper);
* background run configs disable tracing, so session transcripts are never
  shipped to ``traces/ingest`` by the SDK's default trace processor;
* the whole path keeps the open-source boundary (no ``siada.internal`` /
  ``siada.provider.li`` reference or import).

No test performs a real LLM call: the OpenAI SDK Chat Completions entry point
(``chat.completions.create``, whose ``AsyncOpenAI`` client carries the
endpoint/key) and the retained LiteLLM entry point (``litellm.acompletion``)
are mocked, and the Runner-driven tracing test uses a local ``Model`` stub.
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import Any
from unittest import mock as unittest_mock
from unittest.mock import MagicMock

import pytest
import yaml

import siada.config.conf_store as conf_store
from agents import Model
from agents.tracing.processor_interface import TracingProcessor

from siada.provider import client_factory, fast_llm
from siada.provider.default.default_provider import DefaultClient, DefaultProvider
from siada.services.input_processor import process_input
from siada.services.model_wrapper import ModelProviderWrapper, ModelWrapper

REPO_ROOT = Path(__file__).resolve().parents[2]

# Same guard list as tests/entrypoint/test_public_internal_boundary.py.
_FORBIDDEN_PRIVATE_REFERENCES = (
    "siada.internal",
    "siada/internal",
    "siada.provider.li",
    "idaas",
    "IDaaS",
)

# Modules whose public behaviour this file covers.
_SCOPED_SOURCE_FILES = (
    "siada/provider/fast_llm.py",
    "siada/provider/default/default_provider.py",
)

_MAIN_BASE_URL = "https://main.example/v1"
_MAIN_API_KEY = "sk-main"
_FAST_BASE_URL = "https://fast.example/v1"
_FAST_API_KEY = "sk-fast"


# --------------------------------------------------------------------------- #
# fixtures / helpers
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def temp_user_home(tmp_path, monkeypatch):
    """conf.yaml lives under the temp home — never the developer's ~/.siada-cli."""
    monkeypatch.setattr(conf_store, "SIADA_HOME", Path(tmp_path))
    return Path(tmp_path)


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    """No credential leaks from the developer's shell into the tests."""
    for name in ("BASE_URL", "API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _write_conf(home: Path, data: dict) -> None:
    (home / "conf.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


def _write_main_conf(home: Path, fast_llm_config: dict | None = None) -> None:
    data: dict[str, Any] = {
        "llm_config": {"provider": "default", "model": "main-model"},
    }
    if fast_llm_config is not None:
        data["fast_llm_config"] = fast_llm_config
    _write_conf(home, data)


def _full_override(**extra: Any) -> dict:
    section: dict[str, Any] = {
        "provider": "default",
        "model": "fast-model",
        "base_url": _FAST_BASE_URL,
        "api_key": _FAST_API_KEY,
    }
    section.update(extra)
    return section


# The process-global credential variables no fast path may ever touch.
_CREDENTIAL_ENV_KEYS = ("BASE_URL", "API_KEY", "DEEPSEEK_API_KEY", "MOONSHOT_API_KEY")


def _credential_env_snapshot() -> dict[str, str | None]:
    return {name: os.environ.get(name) for name in _CREDENTIAL_ENV_KEYS}


@contextlib.contextmanager
def _forbid_private_imports():
    """Fail if the code under test tries to import the closed-source tree."""
    attempted: list[str] = []

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


@contextlib.asynccontextmanager
async def _captured_litellm_calls():
    """Patch the single LiteLLM network entry point and collect its kwargs."""
    import litellm
    from litellm.types.utils import Choices, Message
    from litellm.types.utils import ModelResponse as LitellmModelResponse

    captured: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs):
        captured.append(kwargs)
        return LitellmModelResponse(
            id="test",
            choices=[
                Choices(
                    message=Message(content="ok", role="assistant"),
                    finish_reason="stop",
                )
            ],
        )

    with unittest_mock.patch.object(litellm, "acompletion", fake_acompletion):
        yield captured


def _chat_completion(model: str) -> Any:
    """A real ``ChatCompletion`` for the mocked SDK entry point to return."""
    from openai.types.chat import ChatCompletion

    return ChatCompletion.model_validate(
        {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 3,
                "completion_tokens": 1,
                "total_tokens": 4,
            },
        }
    )


@contextlib.asynccontextmanager
async def _captured_chat_completion_calls():
    """Patch the OpenAI SDK Chat Completions entry point and collect its calls.

    Yields ``(client, kwargs)`` pairs: the ``AsyncOpenAI`` instance the call was
    dispatched through — the endpoint/key live on that client, not in the
    kwargs — and the kwargs handed to ``chat.completions.create`` (``model``,
    ``extra_headers``, ``extra_body`` …). No network: the SDK method itself is
    replaced, and it answers with a real ``ChatCompletion``.
    """
    from openai.resources.chat.completions.completions import AsyncCompletions

    recorded: list[tuple[Any, dict[str, Any]]] = []

    async def fake_create(resource, **kwargs):
        recorded.append((resource._client, kwargs))
        return _chat_completion(str(kwargs.get("model") or "test-model"))

    with unittest_mock.patch.object(AsyncCompletions, "create", fake_create):
        yield recorded


def _endpoint_of(model_or_client: Any) -> str | None:
    """Configured endpoint of a model / ``AsyncOpenAI`` client.

    ``AsyncOpenAI`` normalizes ``base_url`` to end with a slash; it is stripped
    so the assertions stay about the endpoint the override configured.
    """
    base_url = getattr(model_or_client, "base_url", None)
    return str(base_url).rstrip("/") if base_url is not None else None


async def _wire_kwargs_for(model, model_settings) -> dict[str, Any]:
    """Return the kwargs the model would hand to its network entry point.

    Chat Completions models call the OpenAI SDK (``chat.completions.create``),
    where the credentials live on the ``AsyncOpenAI`` client built for them; the
    retained LiteLLM routes still go through ``litellm.acompletion`` and carry
    ``api_base`` / ``api_key`` in its kwargs.
    """
    from agents.models.interface import ModelTracing
    from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel

    async def fetch_response() -> None:
        await model._fetch_response(
            "You are a test",
            [{"role": "user", "content": "hi"}],
            model_settings,
            [],
            None,
            [],
            MagicMock(),
            ModelTracing.DISABLED,
            stream=False,
        )

    if isinstance(model, OpenAIChatCompletionsModel):
        async with _captured_chat_completion_calls() as recorded:
            await fetch_response()
        assert recorded, "chat.completions.create was not called"
        return recorded[-1][1]

    async with _captured_litellm_calls() as captured:
        await fetch_response()

    assert captured, "litellm.acompletion was not called"
    return captured[-1]


# --------------------------------------------------------------------------- #
# override resolution: endpoint / key
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_override_endpoint_and_key_win_over_main_environment(
    temp_user_home, monkeypatch
):
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    _write_main_conf(temp_user_home, _full_override())

    run_config = fast_llm.build_fast_run_config()

    # Override present → a Model instance (not a string resolved later against
    # the environment), wrapped so the shared input processor still applies.
    assert run_config.tracing_disabled is True
    assert isinstance(run_config.model, Model)
    assert isinstance(run_config.model, ModelWrapper)
    assert run_config.model.input_processor is process_input

    inner = run_config.model.wrapped_model
    assert inner.model == "fast-model"
    assert _endpoint_of(inner) == _FAST_BASE_URL
    assert inner.api_key == _FAST_API_KEY

    # …and the wire call really goes to the override endpoint with its key: the
    # Chat Completions transport posts through the OpenAI client carrying them,
    # so the SDK kwargs hold the wire model (not the credentials).
    kwargs = await _wire_kwargs_for(inner, run_config.model_settings)
    assert kwargs["model"] == "fast-model"
    assert "api_key" not in kwargs
    assert "api_base" not in kwargs


def test_get_fast_model_override_returns_model_instance(temp_user_home, monkeypatch):
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    _write_main_conf(temp_user_home, _full_override())

    model = fast_llm.get_fast_model()

    assert isinstance(model, Model)
    assert model.model == "fast-model"
    assert _endpoint_of(model) == _FAST_BASE_URL
    assert model.api_key == _FAST_API_KEY


def test_without_override_keeps_the_environment_path(temp_user_home, monkeypatch):
    """No override → unchanged: string model resolved by the provider wrapper."""
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    _write_main_conf(temp_user_home)

    run_config = fast_llm.build_fast_run_config()

    assert run_config.tracing_disabled is True
    assert run_config.model == "main-model"
    assert isinstance(run_config.model_provider, ModelProviderWrapper)

    resolved = run_config.model_provider.get_model(run_config.model)
    assert isinstance(resolved, ModelWrapper)
    assert resolved.wrapped_model.model == "main-model"
    assert _endpoint_of(resolved.wrapped_model) == _MAIN_BASE_URL
    assert resolved.wrapped_model.api_key == _MAIN_API_KEY


def test_partial_override_keeps_main_env_for_missing_field(temp_user_home, monkeypatch):
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    _write_main_conf(
        temp_user_home,
        # No base_url — that half must come from the main environment.
        {"provider": "default", "model": "fast-model", "api_key": _FAST_API_KEY},
    )

    inner = fast_llm.build_fast_run_config().model.wrapped_model

    assert _endpoint_of(inner) == _MAIN_BASE_URL
    assert inner.api_key == _FAST_API_KEY


@pytest.mark.asyncio
async def test_override_extra_headers_travel_through_model_settings(
    temp_user_home, monkeypatch
):
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    headers = {"X-Gateway": "fast", "X-Tenant": "acme"}
    _write_main_conf(
        temp_user_home,
        {"provider": "default", "model": "fast-model", "extra_headers": headers},
    )

    run_config = fast_llm.build_fast_run_config()

    # The model constructors take no request headers, so the headers ride
    # ModelSettings (the transport merges them into the outgoing request).
    assert run_config.model_settings.extra_headers == headers
    assert run_config.model_settings.extra_headers is not headers

    inner = run_config.model.wrapped_model
    assert _endpoint_of(inner) == _MAIN_BASE_URL  # headers only → main credentials
    assert inner.api_key == _MAIN_API_KEY

    kwargs = await _wire_kwargs_for(inner, run_config.model_settings)
    assert kwargs["extra_headers"]["X-Gateway"] == "fast"
    assert kwargs["extra_headers"]["X-Tenant"] == "acme"


# --------------------------------------------------------------------------- #
# unsupported providers / models: explicit error, never a silent ignore
# --------------------------------------------------------------------------- #
class _ProviderWithoutExplicitCredentials:
    """A provider implementing only the SDK's ``get_model(name)`` contract."""

    def __init__(self):
        self.requested: list[str | None] = []
        self.model = _ScriptedModel()

    def get_model(self, model_name):
        self.requested.append(model_name)
        return self.model


def test_provider_without_explicit_credentials_raises_when_creds_are_set(
    temp_user_home, monkeypatch
):
    _write_main_conf(temp_user_home, _full_override())
    provider = _ProviderWithoutExplicitCredentials()
    monkeypatch.setattr(fast_llm, "get_provider", lambda name=None: provider)

    with pytest.raises(ValueError, match="fast_llm_config credentials"):
        fast_llm.build_fast_run_config()
    with pytest.raises(ValueError, match="fast_llm_config credentials"):
        fast_llm.get_fast_model()

    # Nothing was resolved through the environment path behind the user's back.
    assert provider.requested == []


def test_headers_only_override_works_on_a_minimal_provider(temp_user_home, monkeypatch):
    headers = {"X-Gateway": "fast"}
    _write_main_conf(
        temp_user_home,
        {"provider": "default", "model": "fast-model", "extra_headers": headers},
    )
    provider = _ProviderWithoutExplicitCredentials()
    monkeypatch.setattr(fast_llm, "get_provider", lambda name=None: provider)

    run_config = fast_llm.build_fast_run_config()

    assert run_config.model_settings.extra_headers == headers
    assert provider.requested == ["fast-model"]
    assert run_config.model.wrapped_model is provider.model


@pytest.mark.parametrize(
    "override",
    [
        # Headers-only override (main credentials) and full override: neither
        # can be delivered by get_fast_model's bare Model.
        {"provider": "default", "model": "fast-model", "extra_headers": {"X-Gateway": "fast"}},
        _full_override(extra_headers={"X-Gateway": "fast"}),
    ],
    ids=["headers-only", "credentials-and-headers"],
)
def test_get_fast_model_rejects_headers_it_cannot_carry(
    temp_user_home, monkeypatch, override
):
    """Fail loudly instead of silently sending the request header-less."""
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    _write_main_conf(temp_user_home, override)

    with pytest.raises(ValueError, match="extra_headers"):
        fast_llm.get_fast_model()

    # The header-carrying paths still work for the same override: ModelSettings
    # here, per-call kwargs in fast_completion (pinned by the tests above).
    run_config = fast_llm.build_fast_run_config()
    assert run_config.model_settings.extra_headers == override["extra_headers"]


def test_responses_only_model_with_different_override_credentials_raises(
    temp_user_home, monkeypatch
):
    """The env-only Responses transport cannot honour a *different* endpoint."""
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    _write_main_conf(
        temp_user_home,
        {
            "provider": "default",
            "model": "gpt-5.4",
            "base_url": _FAST_BASE_URL,
            "api_key": _FAST_API_KEY,
        },
    )

    with pytest.raises(ValueError, match="Responses-API-only"):
        fast_llm.build_fast_run_config()


def test_responses_only_model_with_matching_credentials_is_allowed(
    temp_user_home, monkeypatch
):
    """Identical values lose no override — the env-driven transport is enough."""
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    _write_main_conf(
        temp_user_home,
        {
            "provider": "default",
            "model": "gpt-5.4",
            "base_url": _MAIN_BASE_URL,
            "api_key": _MAIN_API_KEY,
        },
    )

    from siada.provider.responses import ResponsesModel

    inner = fast_llm.build_fast_run_config().model.wrapped_model

    assert isinstance(inner, ResponsesModel)
    assert inner.model == "gpt-5.4"


# --------------------------------------------------------------------------- #
# DefaultClient / fast_completion precedence
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_default_client_env_fills_only_missing_per_call_kwargs(monkeypatch):
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    client = DefaultClient()

    async with _captured_litellm_calls() as captured:
        await client.completion(
            model="main-model", messages=[{"role": "user", "content": "hi"}]
        )
        await client.completion(
            model="main-model",
            messages=[{"role": "user", "content": "hi"}],
            api_base="https://other.example/v1",
            api_key="sk-other",
        )

    # Env fills the gaps…
    assert captured[0]["api_base"] == _MAIN_BASE_URL
    assert captured[0]["api_key"] == _MAIN_API_KEY
    # …but never overwrites explicit per-call kwargs.
    assert captured[1]["api_base"] == "https://other.example/v1"
    assert captured[1]["api_key"] == "sk-other"


@pytest.mark.asyncio
async def test_fast_completion_precedence_explicit_over_override_over_env(
    temp_user_home, monkeypatch
):
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    _write_main_conf(temp_user_home, _full_override())
    client = DefaultClient()
    monkeypatch.setattr(client_factory, "get_client", lambda name=None: client)

    async with _captured_litellm_calls() as captured:
        await fast_llm.fast_completion("write a slug")
        await fast_llm.fast_completion("write a slug", api_key="sk-call")
        await fast_llm.fast_completion(
            "write a slug", api_base="https://call.example/v1", api_key="sk-call"
        )

    # override only
    assert captured[0]["model"] == "fast-model"
    assert captured[0]["api_base"] == _FAST_BASE_URL
    assert captured[0]["api_key"] == _FAST_API_KEY
    # explicit per-call key beats the override; the override still supplies the
    # endpoint the call did not set
    assert captured[1]["api_base"] == _FAST_BASE_URL
    assert captured[1]["api_key"] == "sk-call"
    # explicit per-call values beat both the override and the main environment
    assert captured[2]["api_base"] == "https://call.example/v1"
    assert captured[2]["api_key"] == "sk-call"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fast_model", "vendor_env"),
    [
        ("deepseek-chat", "DEEPSEEK_API_KEY"),
        ("kimi-k2.5", "MOONSHOT_API_KEY"),
    ],
    ids=["deepseek", "kimi"],
)
async def test_fast_completion_override_never_mutates_process_credentials(
    temp_user_home, monkeypatch, fast_model, vendor_env
):
    """An override request must not change what a main request sees.

    DeepSeek / Moonshot are the two LiteLLM backends behind a vendor-specific
    env var. Writing it (with either key) is process-global state: a concurrent
    main-endpoint request could then authenticate with the override key, or the
    override request could be rerouted to the main endpoint. The credentials
    therefore travel as per-call ``api_base`` / ``api_key`` kwargs only.
    """
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    monkeypatch.delenv(vendor_env, raising=False)
    _write_main_conf(
        temp_user_home,
        {
            "provider": "default",
            "model": fast_model,
            "base_url": _FAST_BASE_URL,
            "api_key": _FAST_API_KEY,
        },
    )
    before = _credential_env_snapshot()

    async with _captured_litellm_calls() as captured:
        await fast_llm.fast_completion("write a slug")
        # A main-endpoint request issued straight after the override call: it
        # must still resolve the environment pair, not the fast one.
        await DefaultClient().completion(
            model=fast_model, messages=[{"role": "user", "content": "hi"}]
        )

    expected_model = {
        "deepseek-chat": "deepseek/deepseek-chat",
        "kimi-k2.5": "moonshot/kimi-k2.5",
    }[fast_model]
    assert captured[0]["model"] == expected_model
    assert captured[0]["api_base"] == _FAST_BASE_URL
    assert captured[0]["api_key"] == _FAST_API_KEY
    assert captured[1]["api_base"] == _MAIN_BASE_URL
    assert captured[1]["api_key"] == _MAIN_API_KEY
    # No credential env var was created, changed or removed…
    assert _credential_env_snapshot() == before
    # …in particular neither vendor var (both used to be set to the main key
    # by DefaultClient.completion / the provider's env helper).
    assert os.environ.get("DEEPSEEK_API_KEY") is None
    assert os.environ.get("MOONSHOT_API_KEY") is None


def test_model_build_never_writes_vendor_env_vars(temp_user_home, monkeypatch):
    """Building a model (main or override) is not a credential side effect."""
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    provider = DefaultProvider()

    main_model = provider.get_model("deepseek-chat")
    assert main_model.api_key == _MAIN_API_KEY
    assert _endpoint_of(main_model) == _MAIN_BASE_URL

    fast_model = provider.get_model_with_credentials(
        "kimi-k2.5", base_url=_FAST_BASE_URL, api_key=_FAST_API_KEY
    )
    assert fast_model.api_key == _FAST_API_KEY
    assert _endpoint_of(fast_model) == _FAST_BASE_URL

    # Both models passed their credentials on the instance; the vendor env vars
    # stayed absent (the main key used to be copied into them here).
    assert os.environ.get("DEEPSEEK_API_KEY") is None
    assert os.environ.get("MOONSHOT_API_KEY") is None


# --------------------------------------------------------------------------- #
# background tracing + open-source boundary
# --------------------------------------------------------------------------- #
class _TranscriptRecorder(TracingProcessor):
    """Minimal TracingProcessor recording what a trace export would ship."""

    def __init__(self):
        self.trace_starts: list[Any] = []
        self.trace_ends: list[Any] = []
        self.spans: list[Any] = []

    def on_trace_start(self, trace):
        self.trace_starts.append(trace)

    def on_trace_end(self, trace):
        self.trace_ends.append(trace)

    def on_span_start(self, span):
        self.spans.append(span)

    def on_span_end(self, span):
        pass

    def shutdown(self):
        pass

    def force_flush(self):
        pass


@contextlib.contextmanager
def _recording_trace_provider():
    """Install a fresh trace provider with one local recorder; restore after."""
    from agents.tracing import get_trace_provider, set_trace_provider
    from agents.tracing.provider import DefaultTraceProvider

    recorder = _TranscriptRecorder()
    original = get_trace_provider()
    provider = DefaultTraceProvider()
    provider.register_processor(recorder)
    # The test harness exports OPENAI_AGENTS_DISABLE_TRACING; the manual flag
    # always wins over the env value, so the control run below can prove the
    # recorder would see a trace that the fast config keeps from it.
    provider.set_disabled(False)
    set_trace_provider(provider)
    try:
        yield recorder
    finally:
        set_trace_provider(original)


class _ScriptedModel(Model):
    """Local Model stub: one assistant message, no network."""

    def __init__(self):
        self.model = "stub-model"
        self.calls: list[Any] = []

    async def get_response(
        self, system_instructions, input, *args, **kwargs
    ):  # noqa: A002 - SDK signature
        from agents.items import ModelResponse
        from agents.usage import Usage
        from openai.types.responses import ResponseOutputMessage, ResponseOutputText

        self.calls.append(input)
        return ModelResponse(
            output=[
                ResponseOutputMessage(
                    id="msg_1",
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[
                        ResponseOutputText(
                            type="output_text", text="ok", annotations=[]
                        )
                    ],
                )
            ],
            usage=Usage(),
            response_id=None,
        )

    def stream_response(self, *args, **kwargs):  # pragma: no cover - unused
        raise NotImplementedError("streaming not needed in these tests")


class _ProviderReturningModel:
    def __init__(self, model):
        self._model = model

    def get_model(self, model_name):
        return self._model


@pytest.mark.asyncio
async def test_background_run_config_never_reaches_trace_processors(
    temp_user_home, monkeypatch
):
    """MemoryAgent-style runs must not export the transcript anywhere."""
    from agents import Agent, Runner, RunConfig

    _write_main_conf(temp_user_home)
    stub = _ScriptedModel()
    monkeypatch.setattr(
        fast_llm, "get_provider", lambda name=None: _ProviderReturningModel(stub)
    )

    with _recording_trace_provider() as recorder:
        run_config = fast_llm.build_fast_run_config()
        assert run_config.tracing_disabled is True

        # Control: the same harness DOES record a trace when tracing is on —
        # this proves the empty result below is the config's doing.
        control = RunConfig(tracing_disabled=False, model=stub)
        await Runner.run(
            Agent(name="control", instructions="control"),
            input="SECRET TRANSCRIPT",
            run_config=control,
        )
        assert len(recorder.trace_starts) == 1
        assert recorder.spans, "control run should have produced spans"

        del recorder.trace_starts[:]
        del recorder.spans[:]

        await Runner.run(
            Agent(name="MemoryAgent", instructions="summarize"),
            input="SECRET TRANSCRIPT",
            run_config=run_config,
        )

    assert recorder.trace_starts == []
    assert recorder.spans == []
    assert stub.calls, "the fast model was actually invoked"


@pytest.mark.asyncio
async def test_override_run_config_drives_the_runner_with_the_override_model(
    temp_user_home, monkeypatch
):
    """End-to-end (local): Runner → wrapper → real Chat Completions model.

    The OpenAI SDK entry point is mocked, so what the Runner dispatches proves
    the Model *instance* carried the override endpoint/key/headers all the way
    (the provider wrapper's environment path would have sent the main ones):
    the kwargs hold the override wire model/headers, and the ``AsyncOpenAI``
    client they are dispatched through holds the override endpoint/key.
    """
    from agents import Agent, Runner

    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    _write_main_conf(
        temp_user_home, _full_override(extra_headers={"X-Gateway": "fast"})
    )

    run_config = fast_llm.build_fast_run_config()

    async with _captured_chat_completion_calls() as recorded:
        result = await Runner.run(
            Agent(name="MemoryAgent", instructions="summarize"),
            input="SECRET TRANSCRIPT",
            run_config=run_config,
        )

    assert result.final_output == "ok"
    assert recorded, "chat.completions.create was not called"
    serving_client, kwargs = recorded[-1]
    assert kwargs["model"] == "fast-model"
    assert kwargs["extra_headers"]["X-Gateway"] == "fast"
    # The override pair, not the main environment pair, authenticated the call.
    assert _endpoint_of(serving_client) == _FAST_BASE_URL
    assert serving_client.api_key == _FAST_API_KEY


@pytest.mark.parametrize("relative_path", _SCOPED_SOURCE_FILES)
def test_scoped_source_has_no_private_references(relative_path):
    source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")

    found = [needle for needle in _FORBIDDEN_PRIVATE_REFERENCES if needle in source]
    assert found == [], f"{relative_path} still references {found}"


def test_override_paths_stay_inside_the_public_boundary(temp_user_home, monkeypatch):
    monkeypatch.setenv("BASE_URL", _MAIN_BASE_URL)
    monkeypatch.setenv("API_KEY", _MAIN_API_KEY)
    _write_main_conf(temp_user_home, _full_override())

    with _forbid_private_imports() as attempted:
        run_config = fast_llm.build_fast_run_config()
        fast_llm.get_fast_model()
        client = DefaultClient()

    assert attempted == []
    assert _endpoint_of(run_config.model.wrapped_model) == _FAST_BASE_URL
    assert isinstance(client, DefaultClient)
