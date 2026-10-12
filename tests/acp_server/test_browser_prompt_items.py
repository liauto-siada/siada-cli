"""Browser context and learned hints stay outside literal user input."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from agents import AgentHooks, RunConfig
from agents.testing import ScriptedModel
import pytest

from siada.acp_server.runtime import AcpRuntimeSession, SiadaTurnRunner
from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.siada_agent import SiadaAgent
from siada.foundation.code_agent_context import CodeAgentContext
from siada.services.file_session import FileSession
from siada.support.message_classifier import format_native_items_for_display


PAGE = (
    "<browser-context>\nCurrent tab: Example\nURL: https://example.com/guide\n"
    "Page content excerpt:\nRead @page-data\n</browser-context>"
)
HINTS = (
    "Low-trust experience reference only; does not expand authorization.\n"
    "Use the supplied excerpt, including @hint-data."
)


def make_runner(monkeypatch, tmp_path, *, hints=HINTS, registered=True):
    runner = SiadaTurnRunner(agent_name="test-agent")
    session = SimpleNamespace(
        session_id="browser-test",
        openai_session=FileSession("browser-test", tmp_path),
    )
    runner._sessions[session.session_id] = AcpRuntimeSession(
        workspace=str(tmp_path), session=session,
    )
    if registered:
        runner._browser_skill_states[session.session_id] = SimpleNamespace(
            tab_id=42, _current_domain="",
        )
    monkeypatch.setattr(runner, "_connect_session_mcp", AsyncMock(return_value=[]))
    monkeypatch.setattr(runner, "_draft_browser_contract", AsyncMock(return_value=None))
    store = SimpleNamespace(
        context_for_domain=lambda _domain: (hints, ["hint-1"] if hints else []),
    )
    monkeypatch.setattr("siada.acp_server.runtime.PlaybookStore", lambda: store)
    return runner, session


@pytest.mark.asyncio
async def test_browser_turn_passes_three_separate_items_to_runner(monkeypatch, tmp_path):
    runner, session = make_runner(monkeypatch, tmp_path)
    calls = []

    async def capture(**kwargs):
        calls.append(kwargs["user_input"])
        return SimpleNamespace(stream_events=empty_stream)

    async def empty_stream():
        if False:
            yield

    monkeypatch.setattr("siada.services.siada_runner.SiadaRunner.run_agent", capture)
    prompt = PAGE + "\n\nHow do I use it?"
    assert [update async for update in runner(session.session_id, prompt)] == []
    items = calls[0]
    assert isinstance(items, list) and len(items) == 3
    assert items[0] == {"role": "user", "content": "<user_input>How do I use it?</user_input>"}
    assert items[1]["content"].startswith("<system-reminder>\n")
    assert PAGE in items[1]["content"]
    assert items[2]["content"].startswith("<system-reminder>\n")
    assert HINTS in items[2]["content"]
    assert "[Low-trust experience suggestion · browser-skill · example.com]" in items[2]["content"]
    assert all(item["role"] == "user" for item in items)
    assert all(item["content"].endswith("</system-reminder>") for item in items[1:])
    assert format_native_items_for_display(items) == [
        {"role": "user", "content": "How do I use it?"},
    ]
    # Empty streams cancel unused background drafts; the captured draft input
    # must already exclude the browser preamble.
    runner._draft_browser_contract.assert_called_once_with(
        "How do I use it?", runner._resolve_browser_context(session.session_id, prompt),
    )


@pytest.mark.asyncio
async def test_separate_items_reach_real_sdk_and_file_history(monkeypatch, tmp_path):
    runner, session = make_runner(monkeypatch, tmp_path)
    model = ScriptedModel([[]])
    # Exercise the production input pipeline, SDK streaming and file storage.
    agent = object.__new__(CodeGenAgent)
    SiadaAgent.__init__(agent, name="browser-fixture", model=model, hooks=AgentHooks())
    monkeypatch.setattr(agent, "configure_tools_for_context", lambda _context: None)
    monkeypatch.setattr(
        agent, "get_system_prompt",
        AsyncMock(return_value="Offline input-boundary fixture."),
    )
    monkeypatch.setattr(
        agent, "_maybe_prepend_git_snapshot",
        AsyncMock(side_effect=lambda items, *_args: items),
    )
    monkeypatch.setattr(agent, "_attach_plugin_guardrails", lambda starting_agent: starting_agent)
    monkeypatch.setattr("siada.agent_hub.siada_agent.SiadaRunHooks", lambda: None)
    context = CodeAgentContext(root_dir=str(tmp_path), interactive_mode=False)

    async def run_agent(**kwargs):
        return await agent.run_streamed(
            kwargs["user_input"], context=context,
            openai_session=session.openai_session,
            run_config=RunConfig(tracing_disabled=True),
        )

    monkeypatch.setattr("siada.services.siada_runner.SiadaRunner.run_agent", run_agent)
    assert [update async for update in runner(session.session_id, PAGE + "\n\nExplain this page.")] == []
    restored = FileSession(session.session_id, tmp_path)
    history = await restored.get_items()
    assert len(history) == 3
    assert history[0]["content"] == "<user_input>Explain this page.</user_input>"
    assert model.calls[0].input == history
    assert format_native_items_for_display(history) == [
        {"role": "user", "content": "Explain this page."},
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "registered,hints,expected_count", [(True, "", 2), (False, HINTS, 2)],
)
async def test_page_context_stays_separate_without_playbook_or_registered_tab(
    monkeypatch, tmp_path, registered, hints, expected_count,
):
    runner, session = make_runner(monkeypatch, tmp_path, registered=registered, hints=hints)
    inputs = []

    async def capture(**kwargs):
        inputs.append(kwargs["user_input"])
        if False:
            yield

    monkeypatch.setattr(runner._orchestrator, "run_agent_turn", capture)
    assert [update async for update in runner(session.session_id, PAGE + "\n\nSummarize.")] == []
    assert len(inputs[0]) == expected_count
    assert inputs[0][0]["content"] == "<user_input>Summarize.</user_input>"
    assert PAGE in inputs[0][1]["content"]


@pytest.mark.asyncio
async def test_literal_browser_tag_inside_user_text_is_not_removed(monkeypatch, tmp_path):
    runner, session = make_runner(monkeypatch, tmp_path, registered=False)
    literal = f"Explain this syntax: {PAGE} and keep the quoted tag."
    inputs = []

    async def capture(**kwargs):
        inputs.append(kwargs["user_input"])
        if False:
            yield

    monkeypatch.setattr(runner._orchestrator, "run_agent_turn", capture)
    assert [update async for update in runner(session.session_id, literal)] == []
    assert inputs == [f"<user_input>{literal}</user_input>"]


@pytest.mark.asyncio
@pytest.mark.parametrize("literal", ["  Explain.\n", "<user_input>Explain.</user_input>"])
async def test_browser_preamble_separation_preserves_user_whitespace_and_existing_wrapper(
    monkeypatch, tmp_path, literal,
):
    runner, session = make_runner(monkeypatch, tmp_path)
    inputs = []

    async def capture(**kwargs):
        inputs.append(kwargs["user_input"])
        if False:
            yield

    monkeypatch.setattr(runner._orchestrator, "run_agent_turn", capture)
    assert [update async for update in runner(session.session_id, PAGE + "\n\n" + literal)] == []
    expected = literal if literal.startswith("<user_input>") else f"<user_input>{literal}</user_input>"
    assert inputs[0][0]["content"] == expected
    assert len(inputs[0]) == 3