"""Native Responses apply_patch rendering through ConversationTurn."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agents import Agent, RawResponsesStreamEvent, RunItemStreamEvent, ToolCallOutputItem
from openai.types.responses import (
    Response,
    ResponseApplyPatchToolCall,
    ResponseCreatedEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
)

from siada.entrypoint.interaction.turn.conversation_turn import ConversationTurn
from siada.tools.coder.apply_patch_presentation import (
    APPLY_PATCH_CUSTOM_DATA_KEY,
    APPLY_PATCH_DISPLAY_END,
    APPLY_PATCH_DISPLAY_START,
)


def _mc(cls, **kwargs):
    """Build OpenAI stream models without irrelevant response fields."""
    return cls.model_construct(**kwargs)


class _FakeResult:
    def __init__(self, events):
        self._events = events

    async def stream_events(self):
        for event in self._events:
            yield event


class _RecordingIO:
    pretty = False
    acp_enabled = False

    def __init__(self) -> None:
        self.tool_calls: list[tuple[str, bool]] = []
        self.advance_count = 0

    def advance_tool_call_stage(self) -> None:
        self.advance_count += 1

    def print_tool_call_all_stages(self, content: str, final: bool = False) -> None:
        self.tool_calls.append((content, final))


def _created_event() -> RawResponsesStreamEvent:
    response = _mc(
        Response,
        id="resp_patch",
        created_at=0,
        model="gpt-6-astra",
        object="response",
        output=[],
        parallel_tool_calls=False,
        tool_choice="auto",
        tools=[],
    )
    return RawResponsesStreamEvent(
        data=_mc(
            ResponseCreatedEvent,
            response=response,
            sequence_number=0,
            type="response.created",
        )
    )


def _native_call() -> ResponseApplyPatchToolCall:
    return _mc(
        ResponseApplyPatchToolCall,
        id="item_patch",
        call_id="call_patch_conversation_001",
        operation={"type": "update_file", "path": "src/service.py", "diff": "@@\n-old\n+new\n"},
        status="completed",
        type="apply_patch_call",
        caller=None,
        created_by=None,
    )


def _turn(io: _RecordingIO) -> ConversationTurn:
    turn = ConversationTurn.__new__(ConversationTurn)
    turn.config = SimpleNamespace(
        io=io,
        llm_config=SimpleNamespace(model_name="gpt-6-astra"),
    )
    turn.session = SimpleNamespace(
        spinner=None,
        state=SimpleNamespace(spinner=None, usage=None),
    )
    turn._message_counter = 0
    turn._current_message_id = None
    turn._stream_start_id = None
    turn._repetition_detector = None
    turn.current_result = None
    return turn


def test_native_apply_patch_output_uses_one_final_tool_use_display_with_custom_data():
    io = _RecordingIO()
    native_call = _native_call()
    custom_data = {
        APPLY_PATCH_CUSTOM_DATA_KEY: {
            "version": 1,
            "call_id": "call_patch_conversation_001",
            "status": "completed",
            "operations": [
                {
                    "action": "update_file",
                    "path": "src/service.py",
                    "move_to": None,
                    "old_text": "old\n",
                    "new_text": "new\n",
                    "status": "completed",
                    "error": None,
                },
                {
                    "action": "create_file",
                    "path": "tests/test_service.py",
                    "move_to": None,
                    "old_text": "",
                    "new_text": "assert True\n",
                    "status": "completed",
                    "error": None,
                },
            ],
        }
    }
    output = ToolCallOutputItem(
        agent=Agent(name="patch-render-test"),
        output="Updated src/service.py\nCreated tests/test_service.py",
        raw_item={
            "type": "apply_patch_call_output",
            "call_id": "call_patch_conversation_001",
            "status": "completed",
        },
        custom_data=custom_data,
    )
    events = [
        _created_event(),
        RawResponsesStreamEvent(
            data=_mc(
                ResponseOutputItemAddedEvent,
                item=native_call,
                output_index=0,
                sequence_number=1,
                type="response.output_item.added",
            )
        ),
        RawResponsesStreamEvent(
            data=_mc(
                ResponseOutputItemDoneEvent,
                item=native_call,
                output_index=0,
                sequence_number=2,
                type="response.output_item.done",
            )
        ),
        RunItemStreamEvent(name="tool_output", item=output),
    ]

    turn = _turn(io)
    asyncio.run(turn.output_stream_content(_FakeResult(events)))

    assert turn.tool_calls["call_patch_conversation_001"]["raw_item"] is native_call
    assert io.advance_count == 1
    assert len(io.tool_calls) == 1
    content, final = io.tool_calls[0]
    assert final is True
    assert content.startswith("Apply patch: 2 files changed")
    assert APPLY_PATCH_DISPLAY_START in content
    assert "### Update `src/service.py`" in content
    assert "### Create `tests/test_service.py`" in content
    assert APPLY_PATCH_DISPLAY_END in content
