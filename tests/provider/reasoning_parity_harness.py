"""Shared harness for reasoning-params parity tests (default / responses paths).

Captures the FINAL arguments each provider path hands to its network entry
point, normalized so that environment-dependent values (auth headers) do not
affect comparisons:

* ``capture_default`` -- the retained LiteLLM route (claude / anthropic /
  gemini in production) and the frozen pre-refactor snapshots: the kwargs
  handed to ``litellm.acompletion``.
* ``capture_default_wire_body`` -- the Chat Completions families, which the
  public default provider serves through the official SDK: the JSON request
  body an OpenAI-compatible endpoint receives.
* ``capture_responses`` -- the Responses path: the request params built by
  ``ResponsesModel``.

The matrix and capture logic live here so that the golden generator
(``_gen_reasoning_parity_golden.py``) and the parity tests
(``test_reasoning_params_parity.py``) exercise byte-identical code paths.
"""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import litellm
from litellm.types.utils import Choices, Message, ModelResponse

# ---------------------------------------------------------------------------
# Pin model settings while constructing each test config, without changing
# other tests' active catalog. The historical Gemini entry is an offline
# request-format fixture; it is not part of the public supported-model list.
# ---------------------------------------------------------------------------
from siada.models import model_base_config as _mbc

_PINNED_MODEL_SETTINGS = [deepcopy(c) for c in _mbc.MODEL_SETTING]
_PINNED_MODEL_SETTINGS.append(
    _mbc.ModelBaseConfig(
        model_name="gemini-3.5-flash",
        max_tokens=65535,
        context_window=600_000,
        parallel_tool_calls=True,
        supports_extra_params=["reasoning_effort"],
        default_reasoning_effort="low",
    )
)

from agents.models.interface import ModelTracing

from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter

# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------

# Every model family / converter branch is covered (one model per branch
# family, using the built-in catalog and the historical fixture above):
#   claude (adaptive default DT=-1), gemini, glm-5.2 (DT=1024), glm-5.3,
#   deepseek, qwen (effort+enable_thinking), kimi (effort only, DRE=max),
#   gpt-6 (responses-only).
MODELS: list[str] = [
    "claude-sonnet-5",
    "claude-sonnet-4-6",
    "gemini-3.5-flash",
    "deepseek-v4-flash",
    "kimi-k3",
    "glm-5.2",
    "glm-5.3",
    "qwen3.7-plus",
    "qwen3.8-max",
    "gpt-6-luna",
]

RESPONSES_ONLY_MODELS = {"gpt-6-luna"}

VARIANTS: list[str] = [
    "default",             # keep model-config defaults (DT / DRE applied)
    "no_reasoning",        # clear thinking_tokens + reasoning_effort
    "effort_low",          # reasoning_effort = "low"
    "effort_max",          # reasoning_effort = "max"
    "tokens_2048",         # thinking_tokens = 2048
    "tokens_neg1",         # thinking_tokens = -1 (explicit adaptive)
    "effort_low_tokens",   # reasoning_effort = "low" + thinking_tokens = 2048
    "thinking_off",        # enable_thinking = False, no effort/tokens
    "thinking_off_tokens", # enable_thinking = False + thinking_tokens = 2048
]


def make_config(model: str, variant: str) -> ModelRunConfig:
    """Build a ModelRunConfig for (model, variant)."""
    with patch.object(_mbc, "_user_model_settings", _PINNED_MODEL_SETTINGS):
        cfg = ModelRunConfig(model)
    if variant == "default":
        return cfg
    cfg.thinking_tokens = None
    cfg.reasoning_effort = None
    if variant == "no_reasoning":
        pass
    elif variant == "effort_low":
        # set_reasoning_effort (not a plain field write) mirrors the real user
        # entry points (CLI --effort / conf.yaml / /effort command) and marks
        # the effort as user-EXPLICIT for the converter's effort-first policy.
        cfg.set_reasoning_effort("low")
    elif variant == "effort_max":
        cfg.set_reasoning_effort("max")
    elif variant == "tokens_2048":
        cfg.thinking_tokens = 2048
    elif variant == "tokens_neg1":
        cfg.thinking_tokens = -1
    elif variant == "effort_low_tokens":
        cfg.set_reasoning_effort("low")
        cfg.thinking_tokens = 2048
    elif variant == "thinking_off":
        cfg.enable_thinking = False
    elif variant == "thinking_off_tokens":
        cfg.enable_thinking = False
        cfg.thinking_tokens = 2048
    else:
        raise ValueError(f"unknown variant {variant!r}")
    return cfg


def build_settings(model: str, variant: str):
    return ModelSettingsConverter.convert_model_settings(make_config(model, variant))


def is_unreachable(model: str, variant: str) -> bool:
    """Combinations that cannot occur in production (and would crash the
    pre-refactor converter), so they are excluded from the matrix.

    - gemini + effort="max": the /effort validation rejects "max" for Gemini
      (valid: low/medium/high), and constructing ``Reasoning(effort="max")``
      raises a pydantic validation error anyway.
    """
    if "gemini" in model.lower() and variant == "effort_max":
        return True
    return False



# ---------------------------------------------------------------------------
# Capture harnesses
# ---------------------------------------------------------------------------

def _fake_model_response() -> ModelResponse:
    return ModelResponse(
        id="test-response",
        choices=[Choices(message=Message(content="hi", role="assistant"), finish_reason="stop")],
    )


def _normalize_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    """Strip environment-dependent values so snapshots are reproducible."""
    normalized = {}
    for key, value in kwargs.items():
        if key == "extra_headers":
            # Contains per-request uuid, session fingerprint and locally
            # stored auth token — replace with a stable marker.
            normalized[key] = "<normalized>"
        else:
            normalized[key] = value
    return normalized


_INPUT = [{"role": "user", "content": "hi"}]

# Endpoint/credentials for the in-process transport capture: synthetic, and
# never dialed (the client's transport is replaced by a MockTransport).
_STUB_BASE_URL = "http://provider-harness.test/v1"
_STUB_API_KEY = "sk-harness-test"

# Model-family keywords served by the retained LiteLLM route; mirrors
# ``DefaultProvider._build_model``. Everything else is Chat Completions.
_LITELLM_ROUTE_KEYWORDS: tuple[str, ...] = ("claude", "anthropic", "gemini")


def uses_litellm_route(model_name: str) -> bool:
    """Whether the public default provider keeps ``model_name`` on LiteLLM."""
    lower = (model_name or "").lower()
    return any(keyword in lower for keyword in _LITELLM_ROUTE_KEYWORDS)


async def capture_default(model_name: str, settings) -> dict[str, Any]:
    """Capture the retained LiteLLM route's ``litellm.acompletion`` kwargs.

    This is the production transport for claude / anthropic / gemini (and the
    frozen pre-refactor snapshot comparison for those families). The
    Chat Completions families no longer take this route -- they are captured by
    ``capture_default_wire_body`` instead.
    """
    from siada.provider.default.kimi_tool_ordering import (
        get_kimi_tool_ordering_litellm_model_cls,
    )

    captured: list[dict] = []

    async def fake_acompletion(**kwargs):
        captured.append(kwargs)
        return _fake_model_response()

    model = get_kimi_tool_ordering_litellm_model_cls()(
        model=model_name, base_url="http://test.local", api_key="test-key"
    )
    with patch.object(litellm, "acompletion", fake_acompletion):
        await model._fetch_response(
            "You are a test",
            deepcopy(_INPUT),
            settings,
            [],
            None,
            [],
            MagicMock(),
            ModelTracing.DISABLED,
            stream=False,
        )
    return _normalize_kwargs(captured[0])


def _chat_completion_payload(model_name: str) -> dict[str, Any]:
    return {
        "id": "chatcmpl-harness",
        "object": "chat.completion",
        "created": 1,
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "hi"},
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


async def capture_default_wire_body(model_name: str, settings) -> dict[str, Any]:
    """Capture the final HTTP request body the default provider sends.

    Chat Completions families are served by ``DefaultOpenAIChatCompletionsModel``
    (the official SDK), so this runs the real
    provider -> model -> SDK serialization chain and replaces only the client's
    transport with an in-process ``MockTransport``: the returned dict is the
    JSON body an OpenAI-compatible endpoint receives. Nothing leaves the
    process, and the ambient ``HTTP(S)_PROXY`` settings cannot reroute it.
    """
    if uses_litellm_route(model_name):
        raise ValueError(
            f"{model_name!r} keeps the retained LiteLLM route; capture it with "
            "capture_default() instead"
        )

    from siada.provider.default import chat_completions as chat_module
    from siada.provider.default.chat_completions import (
        DefaultOpenAIChatCompletionsModel,
    )
    from siada.provider.default.default_provider import DefaultProvider

    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(
            200, json=_chat_completion_payload(model_name), request=request
        )

    real_async_openai = chat_module.AsyncOpenAI

    def create_client(**kwargs: Any) -> Any:
        return real_async_openai(
            **kwargs,
            http_client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler), trust_env=False
            ),
        )

    provider = DefaultProvider()
    try:
        with patch.object(chat_module, "AsyncOpenAI", create_client):
            model = provider.get_model_with_credentials(
                model_name, base_url=_STUB_BASE_URL, api_key=_STUB_API_KEY
            )
            assert isinstance(model, DefaultOpenAIChatCompletionsModel), (
                f"the default provider no longer serves {model_name!r} through "
                f"the Chat Completions transport ({type(model).__name__})"
            )
            await model.get_response(
                system_instructions="You are a test",
                input=deepcopy(_INPUT),
                model_settings=settings,
                tools=[],
                output_schema=None,
                handoffs=[],
                tracing=ModelTracing.DISABLED,
            )
    finally:
        await provider.aclose()

    assert bodies, "the Chat Completions transport sent no request"
    return bodies[0]


def capture_responses(model_name: str, settings) -> dict[str, Any]:
    """Run ResponsesModel._build_request_params (used for responses-only models)."""
    from siada.provider.responses.responses_model import ResponsesModel
    from siada.provider.responses.transport import ResponsesTransport

    model = ResponsesModel(model=model_name, transport=MagicMock(spec=ResponsesTransport))
    params = model._build_request_params(
        system_instructions="You are a test",
        input=deepcopy(_INPUT),
        model_settings=settings,
        tools=[],
        output_schema=None,
        handoffs=[],
        previous_response_id=None,
        conversation_id=None,
        prompt=None,
    )
    return params


def capture_all(model: str, variant: str) -> dict[str, dict[str, Any]]:
    """Capture the provider path used in production for one (model, variant) pair.

    The ``"default"`` entry is the retained LiteLLM route's kwargs (the frozen
    pre-refactor comparison, and the reference snapshots the generator writes);
    the Chat Completions families' production body is captured by
    ``capture_default_wire_body``.
    """
    settings = build_settings(model, variant)
    result: dict[str, dict[str, Any]] = {}

    if model not in RESPONSES_ONLY_MODELS:
        result["default"] = asyncio.run(capture_default(model, settings))
    else:
        # Responses-only models are routed to ResponsesModel; the
        # chat-completions path is never used in production for them.
        result["responses"] = capture_responses(model, settings)
    return result
