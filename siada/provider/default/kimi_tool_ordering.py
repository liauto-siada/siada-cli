"""Kimi/Moonshot tool-message ordering fix for the legacy LiteLLM path.

Background
----------
Moonshot's Kimi K3 Chat-Completions endpoint strictly validates ``role: "tool"``
messages: every one of them must carry a resolvable tool name -- either an
explicit ``tool``/``name`` field, or a ``tool_call_id`` that matches one of the
``tool_calls`` of the *immediately preceding* assistant message.  The
OpenAI-style messages produced by the SDK's ``Converter.items_to_messages``
only carry ``tool_call_id`` (never ``name``), so message ordering is the only
way to satisfy that check.

When Kimi K3 interleaves a text message between two function tool calls of a
single turn, e.g.::

    [reasoning, function_call A, message(text), function_call B, output A, output B]

``Converter.items_to_messages`` splits the turn into two assistant messages
while the ``function_call_output`` items are appended, in their original order,
at the end of the item list.  The resulting history is::

    assistant(tool_calls=[A]), assistant(text, tool_calls=[B]), tool(A), tool(B)

``tool(A)`` no longer follows the assistant message that declared it, so
Moonshot rejects the whole request with::

    400 InternalError.Algo.InvalidParameter: Kimi K3 tool messages need a
    resolvable tool name: carry `tool`/`name`, or match a preceding assistant
    tool_call by order.

Fix
---
One way to solve this is at the message level, by applying
``LitellmModel._fix_tool_message_ordering`` for kimi/moonshot models inside
``_fetch_response``.  The default provider's legacy LiteLLM path builds requests
through the SDK's ``LitellmModel._fetch_response``, which applies that fix only
for anthropic/claude/gemini models.  The direct Chat Completions adapter instead
uses the provider-neutral input-ordering mixin in ``chat_completions.py``.

``KimiToolOrderingLitellmMixin`` re-pairs items at the *input* level: each
``function_call_output`` is moved to directly follow the ``function_call``
holding the same ``call_id``.  After the SDK's own conversion this yields
exactly the message list the endpoint requires::

    assistant(tool_calls=[A]), tool(A), assistant(text, tool_calls=[B]), tool(B)

(verified by ``tests/provider/test_chat_completions_providers.py``).

anthropic/claude/gemini are deliberately *not* handled here: the SDK already
applies ``_fix_tool_message_ordering`` for them inside ``_fetch_response``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from siada.provider.chat_completions import reorder_tool_call_output_items

if TYPE_CHECKING:
    from agents import AgentOutputSchemaBase
    from agents.handoffs import Handoff
    from agents.items import TResponseInputItem
    from agents.model_settings import ModelSettings
    from agents.models.interface import ModelTracing
    from agents.tool import Tool
    from agents.tracing import Span
    from agents.tracing.span_data import GenerationSpanData

# Model-family keywords whose Chat-Completions endpoints require tool outputs
# to immediately follow the assistant message declaring the tool call.
_KIMI_TOOL_ORDERING_MODEL_KEYWORDS: tuple[str, ...] = ("kimi", "moonshot")


class KimiToolOrderingLitellmMixin:
    """Mixin for ``LitellmModel`` that fixes tool-message ordering for Kimi/Moonshot.

    Intended usage::

        class KimiToolOrderingLitellmModel(KimiToolOrderingLitellmMixin, LitellmModel):
            ...

    The mixin overrides the single request entry point that both
    ``get_response`` (non-streaming) and ``stream_response`` (streaming) go
    through, so the fix covers both paths.
    """

    # Provided by LitellmModel at runtime; declared for type checkers.
    model: str

    async def _fetch_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        span: Span[GenerationSpanData],
        tracing: ModelTracing,
        stream: bool = False,
        prompt: Any | None = None,
    ) -> Any:
        """Re-pair tool outputs with their calls for kimi/moonshot, then delegate.

        For kimi/moonshot models, ``function_call_output`` input items are moved
        to directly follow their ``function_call`` before the SDK converts items
        into Chat-Completions messages. Everything else is delegated unchanged
        to ``LitellmModel``.
        """
        model_lower = self.model.lower()
        if (
            isinstance(input, list)
            and input
            and any(keyword in model_lower for keyword in _KIMI_TOOL_ORDERING_MODEL_KEYWORDS)
        ):
            input = reorder_tool_call_output_items(input)
        return await super()._fetch_response(
            system_instructions,
            input,
            model_settings,
            tools,
            output_schema,
            handoffs,
            span,
            tracing,
            stream=stream,
            prompt=prompt,
        )


_model_cls_cache: type | None = None


def get_kimi_tool_ordering_litellm_model_cls() -> type:
    """Build (once) and return the legacy ``LitellmModel`` subclass.

    ``LitellmModel`` lives in a module that imports litellm, which is heavy, so
    the subclass is created lazily and cached: importing this module (and
    ``default_provider.py``) never pulls in litellm.

    Two legacy default-provider customisations are stacked on the SDK class:

    - ``KimiToolOrderingLitellmMixin``: tool-message ordering fix for
      kimi/moonshot models (see module docstring above).
    - ``KeepExtraBodyReasoningEffortMixin``: stops the SDK hoisting
      ``extra_body["reasoning_effort"]`` into a top-level litellm kwarg,
      which ``drop_params=True`` would silently drop for openai-protocol
      models (see ``siada/provider/default/effort_channel.py``).
    """
    global _model_cls_cache
    if _model_cls_cache is None:
        from agents.extensions.models.litellm_model import LitellmModel

        from siada.provider.default.effort_channel import (
            KeepExtraBodyReasoningEffortMixin,
        )

        class KimiToolOrderingLitellmModel(
            KeepExtraBodyReasoningEffortMixin,
            KimiToolOrderingLitellmMixin,
            LitellmModel,
        ):
            """``LitellmModel`` with the default provider's channel fixes.

            Behaviour is identical to plain ``LitellmModel`` except that:

            - for kimi/moonshot models, ``function_call_output`` input items
              are re-paired with their ``function_call`` before the SDK
              converts items into Chat-Completions messages (prevents
              Moonshot's 400 rejection when a single turn interleaves text
              between tool calls);
            - an effort configured in ``extra_body`` stays in the request
              body instead of being hoisted into a top-level kwarg that
              litellm's ``drop_params`` would drop for openai-protocol
              models.
            """

        _model_cls_cache = KimiToolOrderingLitellmModel
    return _model_cls_cache
