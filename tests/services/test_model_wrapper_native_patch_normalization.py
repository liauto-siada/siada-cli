"""ModelWrapper input normalization for native Responses apply_patch items.

Replayed session history can contain ``apply_patch_call`` /
``apply_patch_call_output`` items (produced by GPT-5/Astra sessions).  Those
items are Responses-protocol only: the ChatCompletions converter raises
``UserError("Unhandled item type or structure")`` on them.  ``ModelWrapper``
wraps every model returned by both the ``li`` and ``default`` providers, so
this is the single boundary where the rewrite must happen whenever the target
model cannot carry the native items.
"""
from __future__ import annotations

import pytest

from siada.services.model_wrapper import ModelWrapper
from siada.support.chat_compat_items import PROXY_TOOL_NAME


class _FakeChatModel:
    """Duck-typed chat-completions model: no native Responses items marker."""

    def __init__(self, model: str = "kimi-k2-0905-preview") -> None:
        self.model = model


class _FakeResponsesModel:
    """Duck-typed native Responses model (carries the opt-out marker)."""

    supports_native_responses_items = True

    def __init__(self, model: str = "gpt-5.4") -> None:
        self.model = model


def _history() -> list:
    return [
        {"role": "user", "content": "update a.py"},
        {
            "type": "apply_patch_call",
            "id": "apc_1",
            "call_id": "c1",
            "status": "completed",
            "operation": {"type": "update_file", "path": "a.py", "diff": "@@"},
        },
        {
            "type": "apply_patch_call_output",
            "id": "apco_1",
            "call_id": "c1",
            "status": "completed",
            "output": "Done!",
        },
        {"role": "user", "content": "thanks"},
    ]


class TestModelWrapperNormalization:
    def test_chat_model_input_is_rewritten(self):
        wrapper = ModelWrapper(_FakeChatModel(), input_processor=None)
        out = wrapper._process_input(_history())
        assert [i.get("type") or i.get("role") for i in out] == [
            "user",
            "function_call",
            "function_call_output",
            "user",
        ]
        assert out[1]["name"] == PROXY_TOOL_NAME
        assert out[1]["call_id"] == "c1"

    def test_responses_model_input_is_untouched(self):
        wrapper = ModelWrapper(_FakeResponsesModel(), input_processor=None)
        history = _history()
        assert wrapper._process_input(history) is history

    def test_real_responses_model_class_declares_marker(self):
        from siada.provider.responses.responses_model import ResponsesModel

        assert ResponsesModel.supports_native_responses_items is True

    @pytest.mark.asyncio
    async def test_get_response_path_rewrites_input(self):
        class _CapturingChatModel(_FakeChatModel):
            def __init__(self) -> None:
                super().__init__()
                self.seen_input = None

            async def get_response(self, **kwargs):
                self.seen_input = kwargs["input"]
                return "stub-response"

        model = _CapturingChatModel()
        wrapper = ModelWrapper(model, input_processor=None)
        await wrapper.get_response(
            system_instructions=None,
            input=_history(),
            model_settings=None,
            tools=[],
            output_schema=None,
            handoffs=[],
            tracing=None,
            previous_response_id=None,
            conversation_id=None,
            prompt=None,
        )
        assert model.seen_input[1]["type"] == "function_call"


class TestChatCompletionsRegression:
    """Offline proof that the rewrite fixes the exact crash this guards."""

    def test_raw_native_items_still_raise_in_converter(self):
        from agents.exceptions import UserError
        from agents.models.chatcmpl_converter import Converter

        with pytest.raises(UserError, match="Unhandled item type or structure"):
            Converter.items_to_messages(_history())

    def test_rewritten_items_convert_for_chat_completions(self):
        from agents.models.chatcmpl_converter import Converter

        wrapper = ModelWrapper(_FakeChatModel(), input_processor=None)
        messages = Converter.items_to_messages(
            wrapper._process_input(_history()), model="kimi-k2-0905-preview"
        )
        tool_calls = [m for m in messages if m.get("tool_calls")]
        assert tool_calls and tool_calls[0]["tool_calls"][0]["function"]["name"] == PROXY_TOOL_NAME
        tool_messages = [m for m in messages if m.get("role") == "tool"]
        assert tool_messages and tool_messages[0]["tool_call_id"] == "c1"

    def test_compacted_history_with_ack_converts_for_chat_completions(self):
        """Post-compaction history carries an id-less assistant ack message.

        ``ApiMessageTransferFilter`` replaces the outgoing history with the
        compacted list, so every later chat-completions replay (model switch,
        forked sub-agent) must be able to carry that ack.
        """
        from agents.models.chatcmpl_converter import Converter

        compacted = [
            {"role": "user", "content": "original task"},
            {"role": "user", "content": "<context>summary</context>"},
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "Got it. Thanks for the additional context!",
                    }
                ],
            },
            {"role": "user", "content": "next request"},
        ]

        wrapper = ModelWrapper(_FakeChatModel(), input_processor=None)
        messages = Converter.items_to_messages(
            wrapper._process_input(compacted), model="kimi-k2-0905-preview"
        )

        assert messages[2] == {
            "role": "assistant",
            "content": "Got it. Thanks for the additional context!",
        }

    @pytest.mark.asyncio
    async def test_default_provider_chat_model_accepts_rewritten_history(self):
        """The real DefaultProvider chat-model class must get past conversion.

        ``litellm.acompletion`` is patched with a sentinel: reaching it proves
        the SDK's item->message conversion (the step that used to raise
        ``UserError``) succeeded for the rewritten history.
        """
        from unittest.mock import AsyncMock, patch

        import litellm
        from agents import ModelSettings
        from agents.models.interface import ModelTracing

        from siada.provider.default.kimi_tool_ordering import (
            get_kimi_tool_ordering_litellm_model_cls,
        )

        model_cls = get_kimi_tool_ordering_litellm_model_cls()
        model = model_cls(
            model="kimi-k2-0905-preview",
            base_url="https://example.invalid",
            api_key="sk-test",
        )
        wrapper = ModelWrapper(model, input_processor=None)
        rewritten = wrapper._process_input(_history())

        class _SentinelReached(Exception):
            pass

        with patch.object(
            litellm, "acompletion", new=AsyncMock(side_effect=_SentinelReached())
        ):
            with pytest.raises(_SentinelReached):
                await model._fetch_response(
                    system_instructions=None,
                    input=rewritten,
                    model_settings=ModelSettings(),
                    tools=[],
                    output_schema=None,
                    handoffs=[],
                    span=None,
                    tracing=ModelTracing.DISABLED,
                    stream=False,
                )

    @pytest.mark.asyncio
    async def test_li_provider_chat_model_accepts_rewritten_history(self):
        """The li provider's own ``_fetch_response`` must get past conversion.

        ``LiModel._fetch_response`` calls ``Converter.items_to_messages``
        directly on the raw input, so the wrapper rewrite is what protects this
        path.  ``_client.chat_complete`` is patched with a sentinel: reaching
        it proves the conversion succeeded.
        """
        from unittest.mock import AsyncMock

        from agents import ModelSettings
        from agents.models.interface import ModelTracing

        from siada.internal.provider.li.li_provider import LiModel

        model = LiModel(model="claude-sonnet-4.6")
        wrapper = ModelWrapper(model, input_processor=None)
        rewritten = wrapper._process_input(_history())

        class _SentinelReached(Exception):
            pass

        model._client.chat_complete = AsyncMock(side_effect=_SentinelReached())

        with pytest.raises(_SentinelReached):
            await model._fetch_response(
                system_instructions=None,
                input=rewritten,
                model_settings=ModelSettings(),
                tools=[],
                output_schema=None,
                handoffs=[],
                span=None,
                tracing=ModelTracing.DISABLED,
                stream=False,
            )