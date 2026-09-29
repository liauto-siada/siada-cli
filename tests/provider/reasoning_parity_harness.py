"""Shared harness for reasoning-params parity tests (default / responses paths).

Captures the FINAL arguments each provider path hands to ``litellm.acompletion``
(or, for the Responses path, the request params built by ``ResponsesModel``)
for a matrix of (model, config-variant) combinations, normalized so that
environment-dependent values (auth headers) do not affect comparisons.

The matrix and capture logic live here so that the golden generator
(``_gen_reasoning_parity_golden.py``) and the parity tests
(``test_reasoning_params_parity.py``) exercise byte-identical code paths.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock, patch

import litellm
from litellm.types.utils import Choices, Message, ModelResponse

# ---------------------------------------------------------------------------
# Pin model settings to the built-in MODEL_SETTING list.
#
# get_model_settings() prefers ``_user_model_settings`` over remote-config
# fetches, so setting it here makes the matrix immune to the background
# remote-model-config thread and to whatever models.json a developer machine
# has locally.
# ---------------------------------------------------------------------------
from siada.models import model_base_config as _mbc

_mbc._user_model_settings = [deepcopy(c) for c in _mbc.MODEL_SETTING]

from agents.models.interface import ModelTracing

from siada.models.model_run_config import ModelRunConfig
from siada.models.model_setting_converter import ModelSettingsConverter

# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------

# Every model family / converter branch is covered (one model per branch
# family, all names present in MODEL_SETTING):
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


async def capture_default(model_name: str, settings) -> dict[str, Any]:
    """Run the default provider's LitellmModel._fetch_response and capture acompletion kwargs."""
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
    """Capture the provider path used in production for one (model, variant) pair."""
    settings = build_settings(model, variant)
    result: dict[str, dict[str, Any]] = {}

    if model not in RESPONSES_ONLY_MODELS:
        result["default"] = asyncio.run(capture_default(model, settings))
    else:
        # Responses-only models are routed to ResponsesModel; the
        # chat-completions path is never used in production for them.
        result["responses"] = capture_responses(model, settings)
    return result
