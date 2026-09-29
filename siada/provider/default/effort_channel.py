"""Keep ``extra_body["reasoning_effort"]`` out of the top-level kwarg channel.

Background
----------
The SDK's ``LitellmModel._get_reasoning_effort`` resolves the effort from
three sources — ``ModelSettings.reasoning``, ``extra_body["reasoning_effort"]``
and ``extra_args["reasoning_effort"]`` — and passes the result as a TOP-LEVEL
``reasoning_effort`` kwarg to ``litellm.acompletion``, removing it from
``extra_body`` in the process.

For openai-protocol chat models on the default-provider path
(``openai/glm-*``, ``deepseek/deepseek-*``, ``moonshot/kimi-*`` and the
unprefixed gateway names), litellm's ``drop_params=True`` (set globally by
``siada.entrypoint._configure_litellm``) does NOT list ``reasoning_effort``
in the provider's supported params, so the top-level kwarg is silently
DROPPED and the effort never reaches the gateway. Routed via ``extra_body``
instead, litellm merges the value verbatim into the HTTP request body, where
it survives (verified by HTTP request capture against litellm 1.91.0 — see
``tests/provider/test_reasoning_params_parity.py``).

That is exactly why ``ModelSettingsConverter`` puts the effort for those
families into ``extra_body`` in the first place (mirroring the li provider's
channel rules). The SDK hoist would undo that choice on the default path.

Fix
---
``KeepExtraBodyReasoningEffortMixin`` overrides ``_get_reasoning_effort`` to
hoist ONLY ``ModelSettings.reasoning`` — the source used legitimately for
Claude (budget-only default effort=high) and Gemini (thinkingLevel), whose
providers natively accept the top-level kwarg. An effort living in
``extra_body`` stays there and reaches the request body.

``extra_args["reasoning_effort"]`` is likewise not hoisted; the converter
never uses that channel, and the SDK's own duplicate-prevention pop in
``_fetch_response`` would remove it from ``extra_kwargs`` anyway.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agents.model_settings import ModelSettings


class KeepExtraBodyReasoningEffortMixin:
    """Mixin for ``LitellmModel`` that stops the SDK hoisting
    ``extra_body["reasoning_effort"]`` into a top-level litellm kwarg.

    Intended usage::

        class DefaultLitellmModel(KeepExtraBodyReasoningEffortMixin, LitellmModel):
            ...
    """

    def _get_reasoning_effort(self, model_settings: "ModelSettings"):
        """Hoist only ``ModelSettings.reasoning`` (Claude / Gemini channel).

        An effort carried in ``extra_body`` is deliberately left in place:
        a top-level ``reasoning_effort`` kwarg is silently dropped by
        litellm's ``drop_params=True`` for openai-protocol models
        (glm/deepseek/qwen/kimi), while ``extra_body`` is merged verbatim
        into the HTTP request body and survives.
        """
        if model_settings.reasoning:
            return model_settings.reasoning.effort
        return None
