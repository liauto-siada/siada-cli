"""At-command expansion must not merge hidden runtime items into user text."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent


@pytest.mark.asyncio
async def test_at_expansion_preserves_three_message_boundaries(monkeypatch):
    items = [
        {"role": "user", "content": "<user_input>Explain @file.py</user_input>"},
        {"role": "user", "content": "<system-reminder>\n<browser-context>@page</browser-context>\n</system-reminder>"},
        {"role": "user", "content": "<system-reminder>\nLow-trust @hint\n</system-reminder>"},
    ]
    snapshot = deepcopy(items)
    expanded = "<user_input>Explain file.py\nReferenced file content</user_input>"
    handler = AsyncMock(return_value=SimpleNamespace(should_proceed=True, processed_query=[{"text": expanded}]))
    monkeypatch.setattr("siada.agent_hub.coder.code_gen_agent.handle_at_command", handler)
    agent = object.__new__(CodeGenAgent)
    context = SimpleNamespace(root_dir=".", interactive_mode=False, session=None)

    result = await agent.process_at_commands(items, context)

    handler.assert_awaited_once()
    assert handler.await_args.kwargs["query"] == items[0]["content"]
    assert len(result) == 3
    assert result[0]["content"] == expanded
    assert result[1:] == items[1:]
    assert items == snapshot


@pytest.mark.asyncio
async def test_at_symbols_in_reminders_never_trigger_file_expansion(monkeypatch):
    items = [
        {"role": "user", "content": "<user_input>Summarize.</user_input>"},
        {"role": "user", "content": "<system-reminder>@page</system-reminder>"},
        {"role": "user", "content": "<system-reminder>@hint</system-reminder>"},
    ]
    handler = AsyncMock()
    monkeypatch.setattr("siada.agent_hub.coder.code_gen_agent.handle_at_command", handler)
    agent = object.__new__(CodeGenAgent)
    result = await agent.process_at_commands(items, SimpleNamespace(root_dir=".", interactive_mode=False, session=None))
    assert result == items
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_expansion_preserves_image_and_hidden_content_parts(monkeypatch):
    image = {"type": "input_image", "image_url": "data:image/png;base64,synthetic"}
    reminder = {"type": "input_text", "text": "<system-reminder>@hint</system-reminder>"}
    items = [{"role": "user", "content": [
        {"type": "input_text", "text": "<user_input>Explain @file.py</user_input>"}, image, reminder,
    ]}]
    handler = AsyncMock(return_value=SimpleNamespace(should_proceed=True, processed_query=[{"text": "expanded"}]))
    monkeypatch.setattr("siada.agent_hub.coder.code_gen_agent.handle_at_command", handler)
    result = await object.__new__(CodeGenAgent).process_at_commands(items, SimpleNamespace(root_dir=".", session=None))
    assert handler.await_args.kwargs["query"] == items[0]["content"][0]["text"]
    assert result[0]["content"] == [{"type": "input_text", "text": "expanded"}, image, reminder]


@pytest.mark.asyncio
async def test_expansion_targets_user_input_after_runtime_and_non_user_items(monkeypatch):
    items = [
        {"role": "system", "content": "Do not expand @system."},
        {"role": "user", "content": "<system-reminder>@page</system-reminder>"},
        {"role": "assistant", "content": "Previously discussed @prior."},
        {"role": "user", "content": [{"type": "input_text", "text": "<system-reminder>@hint</system-reminder>"}]},
        {"role": "user", "content": "<user_input>Explain @file.py</user_input>"},
        {"role": "user", "content": "Later message with @other.py"},
    ]
    snapshot = deepcopy(items)
    handler = AsyncMock(return_value=SimpleNamespace(should_proceed=True, processed_query=[{"text": "expanded"}]))
    monkeypatch.setattr("siada.agent_hub.coder.code_gen_agent.handle_at_command", handler)

    result = await object.__new__(CodeGenAgent).process_at_commands(items, SimpleNamespace(root_dir=".", session=None))

    assert handler.await_args.kwargs["query"] == items[4]["content"]
    assert result[:4] == items[:4]
    assert result[4] == {"role": "user", "content": "expanded"}
    assert result[5:] == items[5:]
    assert items == snapshot
