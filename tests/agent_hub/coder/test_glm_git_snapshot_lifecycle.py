"""Lifecycle of the shared runtime Git snapshot content part.

- CodeGenAgent merges one snapshot into the turn's user content only when
  the effective history has none; later turns and all model families reuse it.
- Compaction (passive and /compact) replaces older copies with exactly one
  fresh snapshot, and the compaction header keeps the original request.
- The snapshot never shows up as a chat bubble or as the session title.
Git itself is mocked here; tests/services/test_git_snapshot.py covers it.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agents import Agent, RunConfig, Runner
from agents.items import ModelResponse
from agents.models.interface import Model
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.context_filter.api_message_transfer_filter import (
    ApiMessageTransferFilter,
)
from siada.agent_hub.context_filter.compaction_strategy import (
    CompactionResult,
    CompactionStrategy,
)
from siada.foundation.code_agent_context import CodeAgentContext
from siada.services import git_snapshot
from siada.services.git_snapshot import (
    GIT_SNAPSHOT_ENV,
    GitSnapshot,
    build_git_snapshot_item,
    has_git_snapshot,
    is_git_snapshot_item,
    is_git_snapshot_text,
)
from siada.session.task_message_state import RealApiMessage, TaskMessageState
from siada.support.message_classifier import format_native_items_for_display


def _snapshot(branch="main", captured_at="2026-01-02T03:04:05Z"):
    return GitSnapshot(
        branch=branch, head="abc1234", upstream="", ahead=0, behind=0, entries=(),
        total_changes=0, staged=0, unstaged=0, untracked=0, captured_at=captured_at,
    )


@pytest.fixture(autouse=True)
def _fake_git(monkeypatch):
    monkeypatch.delenv(GIT_SNAPSHOT_ENV, raising=False)
    capture = MagicMock(return_value=_snapshot())
    monkeypatch.setattr(git_snapshot, "capture_git_snapshot", capture)
    monkeypatch.setattr("siada.agent_hub.coder.code_gen_agent.get_available_lark_tools", lambda: [])
    return capture


def _context(model_name="zhipuai/glm-5.3", real_messages=None, is_subagent=False):
    context = CodeAgentContext(root_dir="/tmp/ws")
    context.is_subagent = is_subagent
    state = TaskMessageState()
    if real_messages:
        state.set_real_messages(RealApiMessage(real_api_history=list(real_messages)))
    context.session = SimpleNamespace(
        siada_config=SimpleNamespace(llm_config=SimpleNamespace(model_name=model_name)),
        state=SimpleNamespace(task_message_state=state, openai_session=None),
    )
    return context


def _session(items=()):
    return SimpleNamespace(get_items=AsyncMock(return_value=list(items)))


def _assert_merged_snapshot(item, text):
    assert item["role"] == "user"
    assert item["content"][0] == {"type": "input_text", "text": text}
    assert is_git_snapshot_text(item["content"][-1]["text"])
    assert item["content"][-1]["type"] == "input_text"
    assert not is_git_snapshot_item(item)


# --------------------------------------------------------------------------- #
# CodeGenAgent: injection at turn start
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["zhipuai/glm-5.3", "z-ai/glm-5.2", "claude-sonnet-5", "gpt-5.6-luna"])
async def test_new_session_gets_one_snapshot_before_the_human_request(_fake_git, model_name):
    result = await CodeGenAgent()._maybe_prepend_git_snapshot(
        "fix the bug", _context(model_name=model_name), _session()
    )

    assert len(result) == 1
    _assert_merged_snapshot(result[0], "fix the bug")
    assert has_git_snapshot(result)
    _fake_git.assert_called_once_with("/tmp/ws")


@pytest.mark.asyncio
async def test_list_input_keeps_its_parts_and_order():
    user_input = [{"role": "user", "content": [
        {"type": "input_text", "text": "look"},
        {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
    ]}]

    result = await CodeGenAgent()._maybe_prepend_git_snapshot(user_input, _context(), _session())

    assert len(result) == 1
    assert result[0]["content"][:2] == user_input[0]["content"]
    assert is_git_snapshot_text(result[0]["content"][2]["text"])
    assert user_input[0]["content"] == [
        {"type": "input_text", "text": "look"},
        {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
    ]
    assert format_native_items_for_display(result) == [{"role": "user", "content": "look"}]


@pytest.mark.asyncio
async def test_list_input_merges_into_last_user_message_after_goal_reminder():
    goal_part = {"type": "input_text", "text": "<system-reminder>goal</system-reminder>"}
    user_input = [
        {"role": "user", "content": "older request"},
        {"type": "message", "role": "assistant", "content": "ok"},
        {"role": "user", "content": [{"type": "input_text", "text": "new request"}, goal_part]},
    ]

    result = await CodeGenAgent()._maybe_prepend_git_snapshot(user_input, _context(), _session())

    assert len(result) == len(user_input)
    assert result[:2] == user_input[:2]
    assert result[2]["content"][:2] == user_input[2]["content"]
    assert is_git_snapshot_text(result[2]["content"][2]["text"])
    assert user_input[2]["content"] == [{"type": "input_text", "text": "new request"}, goal_part]
    assert format_native_items_for_display(result)[-1] == {"role": "user", "content": "new request"}


@pytest.mark.asyncio
async def test_list_input_with_string_content_merges_into_same_message():
    user_input = [{"role": "user", "content": "fix it"}]

    result = await CodeGenAgent()._maybe_prepend_git_snapshot(user_input, _context(), _session())

    _assert_merged_snapshot(result[0], "fix it")
    assert user_input[0]["content"] == "fix it"


@pytest.mark.asyncio
async def test_list_input_without_user_falls_back_to_snapshot_only_message():
    user_input = [{"type": "message", "role": "assistant", "content": "ok"}]

    result = await CodeGenAgent()._maybe_prepend_git_snapshot(user_input, _context(), _session())

    assert len(result) == 2 and result[0] == user_input[0]
    assert is_git_snapshot_item(result[1])
    assert isinstance(result[1]["content"], list)


@pytest.mark.asyncio
async def test_later_turns_reuse_the_snapshot_in_history(_fake_git):
    history = [build_git_snapshot_item(_snapshot()), {"role": "user", "content": "first"}]

    result = await CodeGenAgent()._maybe_prepend_git_snapshot(
        "next turn", _context(), _session(history)
    )

    assert result == "next turn"
    _fake_git.assert_not_called()


@pytest.mark.asyncio
async def test_later_turns_detect_a_merged_snapshot_in_effective_history(_fake_git):
    history = git_snapshot.merge_git_snapshot_into_input("first", build_git_snapshot_item(_snapshot()))

    result = await CodeGenAgent()._maybe_prepend_git_snapshot(
        "next turn", _context(), _session(history)
    )

    assert result == "next turn"
    _fake_git.assert_not_called()


@pytest.mark.asyncio
async def test_resume_consults_session_items_until_the_history_is_rebuilt(_fake_git):
    session_items = [build_git_snapshot_item(_snapshot()), {"role": "user", "content": "first"}]

    result = await CodeGenAgent()._maybe_prepend_git_snapshot(
        "resumed turn", _context(), _session(session_items)
    )

    assert result == "resumed turn"
    _fake_git.assert_not_called()


@pytest.mark.asyncio
async def test_resumed_session_without_snapshot_gets_one_for_this_turn():
    history = [{"role": "user", "content": "old request"}]

    result = await CodeGenAgent()._maybe_prepend_git_snapshot(
        "resumed turn", _context(real_messages=history), _session()
    )

    assert len(result) == 1
    _assert_merged_snapshot(result[0], "resumed turn")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "is_subagent, agent_name",
    [
        (True, "CodeGenAgent"),
        (False, "ReviewFixtureAgent"),
    ],
    ids=["sub-agent", "other-agent"],
)
async def test_gating(_fake_git, is_subagent, agent_name):
    agent = CodeGenAgent(name=agent_name)
    context = _context(model_name="claude-sonnet-5", is_subagent=is_subagent)

    assert await agent._maybe_prepend_git_snapshot("hi", context, _session()) == "hi"
    _fake_git.assert_not_called()


@pytest.mark.asyncio
async def test_switch_off_and_capture_failure_omit_the_snapshot(monkeypatch, _fake_git):
    agent = CodeGenAgent()
    monkeypatch.setenv(GIT_SNAPSHOT_ENV, "off")
    assert await agent._maybe_prepend_git_snapshot(
        "hi", _context(model_name="claude-sonnet-5"), _session()
    ) == "hi"

    monkeypatch.delenv(GIT_SNAPSHOT_ENV)
    _fake_git.return_value = None  # not a repository / git unavailable
    assert await agent._maybe_prepend_git_snapshot("hi", _context(), _session()) == "hi"


@pytest.mark.asyncio
async def test_run_hands_the_snapshot_to_the_sdk_after_at_command_processing():
    agent = CodeGenAgent()
    agent.run_impl = AsyncMock(return_value="result")

    await agent.run("plain request", _context(), run_config=None, openai_session=_session())

    sdk_input = agent.run_impl.await_args.kwargs["input"]
    assert len(sdk_input) == 1
    _assert_merged_snapshot(sdk_input[0], "plain request")


@pytest.mark.asyncio
async def test_streamed_run_hands_the_snapshot_to_the_sdk():
    agent = CodeGenAgent()
    agent.run_streamed_impl = AsyncMock(return_value="stream")

    await agent.run_streamed("plain request", _context(model_name="gpt-5.6-luna"), openai_session=_session())

    sdk_input = agent.run_streamed_impl.await_args.kwargs["input"]
    assert len(sdk_input) == 1
    _assert_merged_snapshot(sdk_input[0], "plain request")


@pytest.mark.asyncio
async def test_sdk_persists_snapshot_and_reuses_it_after_session_reload(tmp_path, _fake_git):
    from siada.services.file_session import FileSession

    class RecordingModel(Model):
        def __init__(self):
            self.inputs = []

        async def get_response(self, system_instructions, input, *args, **kwargs):
            self.inputs.append(input)
            output = ResponseOutputMessage(
                id="msg_1", type="message", role="assistant", status="completed",
                content=[ResponseOutputText(type="output_text", text="ok", annotations=[])],
            )
            return ModelResponse(output=[output], usage=Usage(), response_id=None)

        def stream_response(self, *args, **kwargs):
            raise NotImplementedError

    session = FileSession("s1", sessions_dir=tmp_path)
    context = _context(model_name="claude-sonnet-5")
    context.root_dir = str(tmp_path)
    agent = CodeGenAgent()
    first = await agent._maybe_prepend_git_snapshot("first request", context, session)
    model = RecordingModel()
    sdk_agent = Agent(name="test-agent", model=model)
    run_config = RunConfig(tracing_disabled=True)

    await Runner.run(sdk_agent, input=first, session=session, run_config=run_config)
    saved = json.loads(session.session_file.read_text(encoding="utf-8"))["items"]
    _assert_merged_snapshot(saved[0], "first request")
    _assert_merged_snapshot(model.inputs[0][0], "first request")
    assert session._read_metadata()["first_user_message"] == "first request"

    reopened = FileSession("s1", sessions_dir=tmp_path)
    _assert_merged_snapshot((await reopened.get_effective_messages())[0], "first request")
    second = await agent._maybe_prepend_git_snapshot("second request", context, reopened)
    assert second == "second request"
    await Runner.run(sdk_agent, input=second, session=reopened, run_config=run_config)

    assert (await reopened.get_items())[0] == saved[0]
    assert sum(has_git_snapshot([item]) for item in await reopened.get_items()) == 1
    assert sum(has_git_snapshot([item]) for item in model.inputs[1]) == 1
    _fake_git.assert_called_once_with(str(tmp_path))



# --------------------------------------------------------------------------- #
# Compaction: refresh, dedupe and header selection
# --------------------------------------------------------------------------- #

_OLD = build_git_snapshot_item(_snapshot(branch="old", captured_at="2026-01-01T00:00:00Z"))


async def _passive_compaction(context, pre, compacted):
    strategy = MagicMock()
    strategy.should_compact.return_value = True
    strategy.compact = AsyncMock(return_value=CompactionResult(messages=compacted, compacted=True))
    with patch(
        "siada.agent_hub.context_filter.api_message_transfer_filter.get_compaction_strategy",
        return_value=strategy,
    ), patch(
        "siada.agent_hub.context_filter.api_message_transfer_filter."
        "CompactionStrategy.calculate_fixed_overhead",
        return_value=0,
    ):
        return await ApiMessageTransferFilter()._try_compact_real_api_messages(
            context=context, real_api_messages=pre, tokens_count=100,
            model_config=context.model_run_config,
        )


@pytest.mark.asyncio
async def test_passive_compaction_refreshes_a_merged_snapshot_without_losing_user_text():
    pre = git_snapshot.merge_git_snapshot_into_input("original request", _OLD)
    compacted = [{"role": "user", "content": "summary"}, *pre]

    result = await _passive_compaction(_context(), pre, compacted)

    assert len(result) == 2
    assert result[0] == compacted[0]
    _assert_merged_snapshot(result[1], "original request")
    assert '"main"' in result[1]["content"][-1]["text"]
    assert '"old"' not in result[1]["content"][-1]["text"]
    assert sum(has_git_snapshot([item]) for item in result) == 1
    assert pre[0]["content"][-1]["text"] == _OLD["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["zhipuai/glm-5.3", "claude-sonnet-5", "z-ai/glm-5.2"])
async def test_passive_compaction_keeps_exactly_one_fresh_snapshot(model_name):
    pre = [_OLD, {"role": "user", "content": "task"}]
    # The kept tail may still carry the outdated copy.
    compacted = [{"role": "user", "content": "summary"}, _OLD, {"role": "user", "content": "recent"}]

    result = await _passive_compaction(_context(model_name=model_name), pre, compacted)

    assert len(result) == 2
    assert result[0] == compacted[0]
    _assert_merged_snapshot(result[1], "recent")
    assert '"main"' in result[1]["content"][-1]["text"]
    assert '"old"' not in result[1]["content"][-1]["text"]
    assert sum(has_git_snapshot([item]) for item in result) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pre, is_subagent",
    [
        ([{"role": "user", "content": "task"}], False),  # session never had one
        ([_OLD, {"role": "user", "content": "task"}], True),  # sub-agent
    ],
    ids=["no-prior-snapshot", "sub-agent"],
)
async def test_passive_compaction_does_not_add_a_snapshot(_fake_git, pre, is_subagent):
    compacted = [{"role": "user", "content": "summary"}]

    result = await _passive_compaction(
        _context(model_name="claude-sonnet-5", is_subagent=is_subagent), pre, compacted
    )

    assert not any(is_git_snapshot_item(item) for item in result)
    _fake_git.assert_not_called()


def test_manual_compact_refresh_uses_the_same_rules(_fake_git):
    compacted = [{"role": "user", "content": "summary"}]

    refreshed = ApiMessageTransferFilter.refresh_git_snapshot_after_manual_compaction(
        _context(model_name="claude-sonnet-5"), [_OLD], compacted
    )
    assert len(refreshed) == 1
    _assert_merged_snapshot(refreshed[0], "summary")
    assert compacted == [{"role": "user", "content": "summary"}]

    _fake_git.return_value = None
    assert ApiMessageTransferFilter.refresh_git_snapshot_after_manual_compaction(
        _context(), [_OLD], compacted
    ) is compacted


@pytest.mark.asyncio
async def test_compaction_refresh_survives_disk_reload(tmp_path, monkeypatch):
    from siada.services.file_session import FileSession
    from siada.utils import DirectoryUtils

    monkeypatch.setattr(DirectoryUtils, "get_global_sessions_dir", lambda _root: str(tmp_path))
    context = _context(model_name="claude-sonnet-5")
    context.session.session_id = "s1"
    session = FileSession("s1", sessions_dir=tmp_path)
    await session.add_items([_OLD, {"role": "user", "content": "first request"}])

    refreshed = ApiMessageTransferFilter.refresh_git_snapshot_after_manual_compaction(
        context, await session.get_items(), [{"role": "user", "content": "summary"}]
    )
    context.task_message_state.set_real_messages(RealApiMessage(real_api_history=refreshed))
    ApiMessageTransferFilter()._sync_api_message_to_file(
        context, refreshed, last_index=1,
    )

    reopened = FileSession("s1", sessions_dir=tmp_path)
    effective = await reopened.get_effective_messages()
    _assert_merged_snapshot(effective[0], "summary")
    assert effective[0] == refreshed[0]
    assert sum(has_git_snapshot([item]) for item in effective) == 1
    assert await CodeGenAgent()._maybe_prepend_git_snapshot("next turn", context, reopened) == "next turn"


def test_switch_off_prevents_compaction_refresh(monkeypatch, _fake_git):
    monkeypatch.setenv(GIT_SNAPSHOT_ENV, "0")
    compacted = [{"role": "user", "content": "summary"}]
    assert ApiMessageTransferFilter.refresh_git_snapshot_after_manual_compaction(
        _context(model_name="claude-sonnet-5"), [_OLD], compacted,
    ) is compacted
    _fake_git.assert_not_called()


def test_compaction_header_keeps_first_user_message_with_merged_snapshot():
    human = {"role": "user", "content": "original task"}
    reply = {"type": "message", "role": "assistant", "id": "msg_1", "status": "completed",
             "content": [{"type": "output_text", "text": "ok", "annotations": []}]}
    merged_human = git_snapshot.merge_git_snapshot_into_input("original task", _OLD)[0]
    later = {"role": "user", "content": "later"}

    assert CompactionStrategy.try_get_first_user_assistant_pair(
        [human, reply, later]
    ) == [human, reply]
    assert CompactionStrategy.try_get_first_user_assistant_pair(
        [merged_human, reply, later]
    ) == [merged_human, reply]
    assert CompactionStrategy.try_get_first_user_assistant_pair(
        [merged_human, later]
    ) == [merged_human]


# --------------------------------------------------------------------------- #
# Display and session metadata
# --------------------------------------------------------------------------- #

def test_snapshot_is_never_rendered_as_a_chat_bubble():
    displayed = format_native_items_for_display([_OLD, {"role": "user", "content": "real"}])
    assert displayed == [{"role": "user", "content": "real"}]
    merged = git_snapshot.merge_git_snapshot_into_input("real", _OLD)
    assert format_native_items_for_display(merged) == displayed


@pytest.mark.asyncio
async def test_session_title_skips_the_snapshot(tmp_path):
    from siada.services.file_session import FileSession
    from siada.services.session_management import SessionManager

    session = FileSession("s1", sessions_dir=tmp_path)
    await session.add_items([_OLD, {"role": "user", "content": "real request"}])
    assert session._read_metadata()["first_user_message"] == "real request"

    manager = SessionManager.__new__(SessionManager)
    manager.sessions_dir = tmp_path
    metadata = manager._extract_metadata_from_history("s1", [_OLD, {"role": "user", "content": "real"}])
    assert metadata["first_user_message"] == "real"

    merged = git_snapshot.merge_git_snapshot_into_input("merged request", _OLD)
    merged_session = FileSession("s2", sessions_dir=tmp_path)
    await merged_session.add_items(merged)
    assert merged_session._read_metadata()["first_user_message"] == "merged request"
    merged_metadata = manager._extract_metadata_from_history("s2", merged)
    assert merged_metadata["first_user_message"] == "merged request"
