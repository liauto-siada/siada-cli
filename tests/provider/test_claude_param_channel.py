"""Why Claude's thinking/output_config MUST stay in extra_args (top-level).

litellm 1.91.0 channel behavior for claude models, verified by intercepting
the final HTTP request body (httpx transport mock):

- anthropic provider — the provider the default path routes Claude traffic to
  (``covert_to_litellm_model_name`` maps ``claude-*`` to
  ``anthropic/claude-*``): a literal ``extra_body`` key is forwarded VERBATIM
  into the request body, which the Anthropic/Bedrock endpoint rejects with
  "extra_body: Extra inputs are not permitted". Top-level ``thinking`` /
  ``output_config`` kwargs are natively mapped by litellm's Anthropic
  transformation.
- openai-compatible endpoints: ``extra_body`` is merged into the request
  body (this is why GLM's thinking dict / openai-protocol reasoning_effort
  travel via extra_body).
- bedrock: ``extra_body`` is merged into the request body.

Therefore ModelSettingsConverter emits Claude thinking/output_config via
``extra_args`` (top-level kwargs) and CANNOT unify them into extra_body
without breaking users on the anthropic provider. The default provider runs
the SDK's LitellmModel (site-packages), which does not unwrap extra_body
either — so no project-side adapter can fix that path.

If litellm ever starts unwrapping extra_body for the anthropic provider,
these tests fail: that is the signal the two channels can be unified.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

import httpx
import litellm

THINKING = {"type": "enabled", "budget_tokens": 2048}
OUTPUT_CONFIG = {"effort": "high"}


def _capture_request_bodies():
    """Context manager capturing the final HTTP request body litellm sends."""
    captured: list[dict | None] = []

    async def fake_send(self, request, **kwargs):
        try:
            body = json.loads(request.content) if request.content else None
        except Exception:
            body = None
        captured.append(body)
        # Anthropic Messages-API response shape so litellm parses it.
        return httpx.Response(200, json={
            "id": "msg_test", "object": "message", "created_at": 1,
            "model": "test", "role": "assistant", "type": "message",
            "content": [{"type": "text", "text": "hi"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }, request=request)

    return patch.object(httpx.AsyncClient, "send", fake_send), captured


def _acompletion(**kwargs):
    async def run():
        with patch.object(litellm, "drop_params", True):
            try:
                await litellm.acompletion(
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=100, **kwargs
                )
            except Exception:
                # Response parsing may fail on some providers; the request
                # body has already been captured, which is all we assert on.
                pass
    asyncio.run(run())


class TestAnthropicProviderChannels:
    def test_extra_body_is_forwarded_verbatim(self):
        # The incompatibility that forbids unifying Claude params into
        # extra_body: a literal "extra_body" key lands in the request body
        # and the Anthropic/Bedrock gateway rejects it.
        patcher, captured = _capture_request_bodies()
        with patcher:
            _acompletion(
                model="anthropic/claude-sonnet-4-6",
                api_base="http://test.local", api_key="k",
                extra_body={"thinking": THINKING, "output_config": OUTPUT_CONFIG},
            )
        body = captured[-1]
        assert "extra_body" in body
        assert body["extra_body"] == {"thinking": THINKING, "output_config": OUTPUT_CONFIG}

    def test_top_level_thinking_and_output_config_are_mapped(self):
        # The current extra_args channel: top-level kwargs are natively
        # mapped by litellm's Anthropic transformation.
        patcher, captured = _capture_request_bodies()
        with patcher:
            _acompletion(
                model="anthropic/claude-sonnet-4-6",
                api_base="http://test.local", api_key="k",
                thinking=THINKING, output_config=OUTPUT_CONFIG,
            )
        body = captured[-1]
        assert body["thinking"] == THINKING
        assert body["output_config"] == OUTPUT_CONFIG
        assert "extra_body" not in body


class TestOtherProvidersMergeExtraBody:
    def test_bedrock_merges_extra_body(self):
        patcher, captured = _capture_request_bodies()
        with patcher:
            _acompletion(
                model="bedrock/anthropic.claude-sonnet-4-6-v1:0",
                # api_base routes the request through httpx (interceptable);
                # without it litellm signs against the real AWS endpoint.
                api_base="http://test.local", api_key="k",
                extra_body={"thinking": THINKING},
                aws_access_key_id="x", aws_secret_access_key="y",
                aws_region_name="us-east-1",
            )
        body = captured[-1]
        assert body["thinking"] == THINKING
        assert "extra_body" not in body

    def test_openai_compat_merges_extra_body(self):
        patcher, captured = _capture_request_bodies()
        with patcher:
            _acompletion(
                model="openai/claude-sonnet-4-6",
                api_base="http://test.local", api_key="k",
                extra_body={"thinking": THINKING},
            )
        body = captured[-1]
        assert body["thinking"] == THINKING
        assert "extra_body" not in body


class TestConverterChannelChoice:
    """The converter must keep Claude thinking/output_config in extra_args."""

    def test_claude_params_in_extra_args_not_extra_body(self):
        from siada.models.model_run_config import ModelRunConfig
        from siada.models.model_setting_converter import ModelSettingsConverter

        cfg = ModelRunConfig("claude-sonnet-5")
        # claude-sonnet-5 defaults to adaptive thinking (DT=-1); token
        # budgets are never emitted (effort is the only strength control), so
        # "thinking" only ever appears in its adaptive form — which exercises
        # the same extra_args channel choice as the old budget form.
        cfg.reasoning_effort = "high"
        s = ModelSettingsConverter.convert_model_settings(cfg)

        # Top-level (extra_args) channel — natively mapped by the anthropic
        # transformation (see TestAnthropicProviderChannels above).
        assert s.extra_args is not None
        assert s.extra_args["thinking"] == {"type": "adaptive", "display": "summarized"}
        assert s.extra_args["output_config"] == {"effort": "high"}
        # Never in extra_body: the anthropic provider forwards it verbatim
        # and the gateway rejects it.
        assert s.extra_body is None

