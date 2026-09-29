"""
End-to-end tests for user-defined agents (``.agents/agents/*.md``).

The wiring tests in ``test_run_subtask_user_agent.py`` mock
``Runner.run_streamed``; these tests instead drive the **real** runner loop with
a scripted streaming model. Nothing touches the network or a real LLM, but the
whole pipeline is exercised for real:

    definition file on disk
      → run_subtask / run_subtask_impl
      → build_sub_agent_run_config (real effort mapping)
      → SubTaskAgent (real prompt + filtered tools + attached MCP servers)
      → agents.Runner.run_streamed (real tool execution, real MCP stdio server)
      → sub-agent notifier + returned summary

Scenario used by the main test case::

    workspace/
      .agents/agents/reviewer.md                  # the agent definition
      .agents/skills/review-checklist/SKILL.md    # preloaded by the definition
      target.py                                   # the file the agent inspects
"""

import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from typing import AsyncIterator
from unittest.mock import MagicMock, patch

from agents import RunConfig, function_tool
from agents.items import ModelResponse, TResponseStreamEvent
from agents.models.interface import Model
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
)

from siada.foundation.code_agent_context import CodeAgentContext
from siada.models.model_run_config import ModelRunConfig
from siada.services.agents import get_agent_definition
from siada.services.sub_agent_run_config import build_sub_agent_run_config
from siada.session.session_models import RunningSession
from siada.tools.agent.run_subtask import run_subtask, run_subtask_impl
from siada.tools.agent.subagent_async import wait_for_session_background_subtasks

# ---------------------------------------------------------------------------
# Scripted streaming model
# ---------------------------------------------------------------------------


def _text_message(text: str) -> ResponseOutputMessage:
    return ResponseOutputMessage(
        id="msg_final",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text=text, annotations=[])],
    )


def _tool_call(call_id: str, name: str, arguments: dict) -> ResponseFunctionToolCall:
    return ResponseFunctionToolCall(
        id=call_id,
        call_id=call_id,
        name=name,
        arguments=json.dumps(arguments),
        type="function_call",
    )


class ScriptedStreamingModel(Model):
    """A ``Model`` that replays scripted outputs and records every request.

    Each entry of *scripted_outputs* is the output item list for one model turn
    (a tool call, then a final message, ...). Every request's system
    instructions, tool names, model settings and input are recorded so tests can
    assert on what the sub-agent actually sent.
    """

    def __init__(self, scripted_outputs: list[list]):
        self._scripted = scripted_outputs
        self.turn = 0
        self.requests: list[dict] = []

    async def get_response(self, *args, **kwargs) -> ModelResponse:  # pragma: no cover
        raise NotImplementedError("only streaming is used by run_subtask")

    async def stream_response(
        self,
        system_instructions,
        input,
        model_settings,
        tools,
        output_schema,
        handoffs,
        tracing,
        *,
        previous_response_id,
        conversation_id,
        prompt,
    ) -> AsyncIterator[TResponseStreamEvent]:
        self.requests.append(
            {
                "instructions": system_instructions or "",
                "tools": [getattr(tool, "name", str(tool)) for tool in tools],
                "model_settings": model_settings,
                "input": input,
            }
        )
        output = self._scripted[min(self.turn, len(self._scripted) - 1)]
        self.turn += 1
        yield ResponseCompletedEvent(
            type="response.completed",
            sequence_number=self.turn,
            response=Response(
                id=f"resp_{self.turn}",
                created_at=0,
                model="scripted-model",
                object="response",
                output=output,
                parallel_tool_calls=False,
                tool_choice="auto",
                tools=[],
            ),
        )


# ---------------------------------------------------------------------------
# Workspace / context helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _make_tool_context(run_ctx):
    from agents.tool_context import ToolContext

    return ToolContext.from_agent_context(
        run_ctx, "call_1", tool_name="run_subtask", tool_arguments="{}"
    )


def _stand_in_internal_web_search():
    """Stand-in for the internal-only ``web_search`` tool.

    The real implementation ships in ``siada.internal`` (not open-sourced), so
    ``siada.tools.web.web_search`` is None here and the tool would silently
    disappear from the sub-agent's default surface. That surface is what the
    generic-sub-agent test pins down, so a placeholder with the same name
    restores the baseline shape; nothing in the run ever calls it.
    """

    @function_tool
    def web_search(query: str) -> str:
        """Search the web (stand-in, never invoked by these tests)."""
        raise AssertionError("the stand-in web_search must never be called")

    return web_search


class _UserAgentE2ETestCase(unittest.IsolatedAsyncioTestCase):
    """Shared workspace + context setup for the end-to-end scenarios."""

    MODEL_NAME = "claude-sonnet-5"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        # Hermetic user scope: never pick up agents installed in the
        # developer's own ~/.claude/agents or ~/.agents/agents.
        home_patch = patch("pathlib.Path.home", return_value=self.workspace / "home")
        home_patch.start()
        self.addCleanup(home_patch.stop)

    def _make_context(self) -> CodeAgentContext:
        session = MagicMock(spec=RunningSession)
        session.session_id = "e2e-user-agent-session"
        session.siada_config = MagicMock()
        llm_config = ModelRunConfig(self.MODEL_NAME)
        llm_config.provider = "default"
        session.siada_config.llm_config = llm_config
        session.siada_config.tracing_disabled = True
        return CodeAgentContext(root_dir=str(self.workspace), session=session)

    def _build_run_config(self, context, model, effort=None) -> RunConfig:
        """Build the sub-agent RunConfig through the real code path.

        ``resolve_sub_agent_llm_config`` is pinned to the parent's config so the
        effective model is deterministic (a developer's ``conf.yaml`` may point
        ``sub_agent.llm_config`` at a different model). The scripted model is
        then swapped in for the actual call.
        """
        with patch(
            "siada.services.sub_agent_run_config.resolve_sub_agent_llm_config",
            return_value=context.session.siada_config.llm_config,
        ):
            run_config = build_sub_agent_run_config(context, effort=effort)
        run_config.model = model
        run_config.tracing_disabled = True
        return run_config

    def _write_reviewer_agent(self, extra_frontmatter: str = "") -> None:
        _write(
            self.workspace / ".agents" / "skills" / "review-checklist" / "SKILL.md",
            "---\nname: review-checklist\ndescription: Review checklist.\n---\n\n"
            "CHECKLIST-RULE: verify naming and error handling.\n",
        )
        frontmatter_lines = [
            "---",
            "name: reviewer",
            "description: Reviews a file and reports findings.",
            "tools: [read_file, run_cmd]",
            "skills: [review-checklist]",
            "effort: medium",
        ]
        if extra_frontmatter:
            frontmatter_lines.append(extra_frontmatter.rstrip("\n"))
        frontmatter_lines.append("---")
        _write(
            self.workspace / ".agents" / "agents" / "reviewer.md",
            "\n".join(frontmatter_lines)
            + "\n\nYou are a meticulous reviewer. Inspect the file, then report.\n",
        )
        _write(self.workspace / "target.py", "VALUE = 42\n")


# ---------------------------------------------------------------------------
# 1. The complete test case: a definition-driven agent, start to finish
# ---------------------------------------------------------------------------


class TestUserAgentEndToEnd(_UserAgentE2ETestCase):
    async def test_definition_driven_agent_runs_end_to_end(self):
        self._write_reviewer_agent()
        definition = get_agent_definition(self.workspace, "reviewer")
        context = self._make_context()

        model = ScriptedStreamingModel(
            [
                [_tool_call("call_1", "run_cmd", {"command": "cat target.py"})],
                [_text_message("REVIEW-DONE: VALUE = 42 looks fine")],
            ]
        )
        run_config = self._build_run_config(context, model, effort=definition.effort)

        summary = await run_subtask_impl(
            instruction="Review target.py",
            agent_context=context,
            run_config=run_config,
            agent_definition=definition,
        )

        # 1. The sub-agent's own summary is returned to the caller.
        self.assertEqual(summary, "REVIEW-DONE: VALUE = 42 looks fine")

        # 2. The model really was called with the definition's system prompt:
        #    the standard sub-agent instructions come first, followed by the
        #    definition body, with preloaded skill content inlined.
        instructions = model.requests[0]["instructions"]
        self.assertTrue(
            instructions.startswith(
                "You are a highly skilled software engineer executing a "
                "specific, bounded task."
            )
        )
        self.assertIn("## Unattended Execution Rules", instructions)
        self.assertIn("You are a meticulous reviewer.", instructions)
        self.assertIn("## Preloaded Skills", instructions)
        self.assertIn("CHECKLIST-RULE: verify naming and error handling.", instructions)

        # 3. Only the definition's tools were offered. `read_file` names the
        #    file-tool group, which resolves to this model's `edit_file`
        #    surface; `run_subtask` / web tools must be absent.
        self.assertEqual(sorted(model.requests[0]["tools"]), ["edit_file", "run_cmd"])

        # 4. The tool actually executed and its output reached the next model
        #    call (the sub-agent saw the real file content).
        self.assertEqual(len(model.requests), 2)
        self.assertIn("VALUE = 42", str(model.requests[1]["input"]))

        # 5. `effort: medium` was mapped by the real RunConfig builder and is
        #    present in the model settings of the real call (Claude 4.6+ channel).
        self.assertEqual(
            model.requests[0]["model_settings"].extra_args["output_config"],
            {"effort": "medium"},
        )

        # 6. The sub-agent notifier recorded the run (same state the UI shows).
        self.assertEqual(len(context.sub_agent_items), 1)
        item = context.sub_agent_items[0]
        self.assertEqual(item.status, "completed")
        self.assertEqual(item.summary, "REVIEW-DONE: VALUE = 42 looks fine")

    async def test_generic_sub_agent_is_unchanged_without_a_definition(self):
        """Baseline: no definition → default prompt and default tool set."""
        context = self._make_context()
        model = ScriptedStreamingModel([[_text_message("generic summary")]])
        run_config = self._build_run_config(context, model)

        with patch(
            "siada.agent_hub.coder.sub_task_agent.web_search",
            _stand_in_internal_web_search(),
        ):
            summary = await run_subtask_impl(
                instruction="Do something generic",
                agent_context=context,
                run_config=run_config,
            )

        self.assertEqual(summary, "generic summary")
        instructions = model.requests[0]["instructions"]
        self.assertTrue(
            instructions.startswith(
                "You are a highly skilled software engineer executing a specific, "
                "bounded task."
            )
        )
        self.assertNotIn("## Preloaded Skills", instructions)
        # The untouched default sub-agent surface for this model family: no
        # memory tools, no lark tools, and no `run_subtask` (recursion is off
        # by default).
        self.assertEqual(
            sorted(model.requests[0]["tools"]),
            [
                "edit_file",
                "list_code_definition_names",
                "regex_search_files",
                "run_cmd",
                "web_fetch",
                "web_search",
            ],
        )


# ---------------------------------------------------------------------------
# 2. Inline MCP server: connected for the run, used, then cleaned up
# ---------------------------------------------------------------------------

_MCP_SERVER_SCRIPT = '''\
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("checklist")


@mcp.tool()
def checklist_status(item: str) -> str:
    """Return the review status of a checklist item."""
    return f"CHECKED:{item}"


if __name__ == "__main__":
    mcp.run()
'''

try:  # the MCP client/server stack ships with the agents SDK's mcp extra
    import mcp.server.fastmcp  # noqa: F401

    _MCP_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    _MCP_AVAILABLE = False


@unittest.skipUnless(_MCP_AVAILABLE, "mcp package is not installed")
class TestUserAgentInlineMcpEndToEnd(_UserAgentE2ETestCase):
    async def test_inline_mcp_server_is_used_and_cleaned_up(self):
        from agents.mcp import MCPServerManager

        server_script = _write(self.workspace / "checklist_server.py", _MCP_SERVER_SCRIPT)
        self._write_reviewer_agent(
            extra_frontmatter=(
                "mcpServers:\n"
                f"  - checklist: {{command: \"{sys.executable}\", "
                f"args: [\"{server_script}\"]}}\n"
            )
        )
        definition = get_agent_definition(self.workspace, "reviewer")
        self.assertEqual(len(definition.mcp_servers), 1)

        context = self._make_context()
        model = ScriptedStreamingModel(
            [
                [_tool_call("call_1", "checklist_status", {"item": "naming"})],
                [_text_message("MCP-DONE: CHECKED:naming")],
            ]
        )
        run_config = self._build_run_config(context, model, effort=definition.effort)

        # Record what the run's MCP manager did, without replacing it.
        cleaned_up: list[bool] = []

        class _RecordingManager(MCPServerManager):
            async def cleanup_all(self):
                cleaned_up.append(True)
                return await super().cleanup_all()

        with patch("agents.mcp.MCPServerManager", _RecordingManager):
            summary = await run_subtask_impl(
                instruction="Review target.py using the checklist server",
                agent_context=context,
                run_config=run_config,
                agent_definition=definition,
            )

        # The MCP tool was exposed to the model and actually executed.
        self.assertIn("checklist_status", model.requests[0]["tools"])
        self.assertIn("CHECKED:naming", str(model.requests[1]["input"]))
        self.assertEqual(summary, "MCP-DONE: CHECKED:naming")

        # The definition's server was cleaned up when the run finished.
        self.assertEqual(cleaned_up, [True])

    async def test_mcp_server_is_not_connected_when_the_run_is_not_a_definition(self):
        """No definition → no MCP servers opened (default path untouched)."""
        context = self._make_context()
        model = ScriptedStreamingModel([[_text_message("plain summary")]])
        run_config = self._build_run_config(context, model)

        with patch(
            "siada.tools.agent.run_subtask.open_agent_mcp_servers"
        ) as mock_open:
            summary = await run_subtask_impl(
                instruction="Do something generic",
                agent_context=context,
                run_config=run_config,
            )

        self.assertEqual(summary, "plain summary")
        mock_open.assert_not_called()


# ---------------------------------------------------------------------------
# 3. `background: true` — the tool returns immediately, the run still finishes
# ---------------------------------------------------------------------------


class TestUserAgentBackgroundEndToEnd(_UserAgentE2ETestCase):
    async def test_background_definition_runs_and_notifies_the_parent(self):
        _write(
            self.workspace / ".agents" / "agents" / "watcher.md",
            textwrap.dedent(
                """\
                ---
                name: watcher
                description: Watches something in the background.
                tools: [run_cmd]
                background: true
                ---

                You watch things and report back.
                """
            ),
        )
        context = self._make_context()
        model = ScriptedStreamingModel([[_text_message("WATCH-DONE: nothing to report")]])
        run_config = self._build_run_config(context, model)

        from agents import RunContextWrapper

        # The patch must stay active while the background task actually runs
        # (the tool returns before the sub-agent starts), hence the manual
        # start/stop instead of a `with` block around the tool call only.
        config_patch = patch(
            "siada.tools.agent.run_subtask.build_sub_agent_run_config",
            return_value=run_config,
        )
        config_patch.start()
        self.addCleanup(config_patch.stop)
        try:
            result = await run_subtask.on_invoke_tool(
                _make_tool_context(RunContextWrapper(context=context)),
                json.dumps({"instruction": "Watch target.py", "agent": "watcher"}),
            )

            # The tool returned immediately with a task id instead of waiting.
            self.assertIn("background", result)
            self.assertIn("task_id=", result)

            # ... but the sub-agent really did run: the completion note lands in
            # the parent's pending-context queue (how the parent "hears back").
            await wait_for_session_background_subtasks(context.session_id, timeout=30)
        finally:
            config_patch.stop()

        self.assertTrue(context.hook_pending_contexts, "no completion note staged")
        note = context.hook_pending_contexts[0]
        self.assertIn("Background sub-agent task", note)
        self.assertIn("WATCH-DONE: nothing to report", note)

        # The definition's own prompt/tool surface drove that run.
        self.assertIn("You watch things and report back.", model.requests[0]["instructions"])
        self.assertEqual(model.requests[0]["tools"], ["run_cmd"])
        self.assertEqual(context.sub_agent_items[0].status, "completed")


# ---------------------------------------------------------------------------
# 4. `model:` — the definition's model drives the real RunConfig
# ---------------------------------------------------------------------------


class TestUserAgentModelOverrideEndToEnd(_UserAgentE2ETestCase):
    async def test_definition_model_drives_the_real_run_config(self):
        """The definition's `model` wins over the resolved sub-agent model and
        is what the run is built for; the scripted model is merely swapped in
        for the call itself, exactly like the other end-to-end cases."""
        self._write_reviewer_agent(extra_frontmatter="model: gpt-6-luna")
        definition = get_agent_definition(self.workspace, "reviewer")
        self.assertEqual(definition.model, "gpt-6-luna")

        context = self._make_context()
        scripted = ScriptedStreamingModel([[_text_message("MODEL-OVERRIDE-DONE")]])
        captured: dict = {}
        real_build = build_sub_agent_run_config

        def _build(context, effort=None, model=None):
            run_config = real_build(context, effort=effort, model=model)
            captured["model"] = run_config.model
            captured["settings"] = run_config.model_settings
            run_config.model = scripted
            run_config.tracing_disabled = True
            return run_config

        from agents import RunContextWrapper

        with patch(
            "siada.tools.agent.run_subtask.build_sub_agent_run_config",
            side_effect=_build,
        ), patch(
            "siada.services.sub_agent_run_config.resolve_sub_agent_llm_config",
            return_value=context.session.siada_config.llm_config,
        ):
            summary = await run_subtask.on_invoke_tool(
                _make_tool_context(RunContextWrapper(context=context)),
                json.dumps({"instruction": "Review target.py", "agent": "reviewer"}),
            )

        # The definition's model — not the parent's claude-sonnet-5 — was the
        # effective model of the run, with the effort mapped onto it
        # (GPT-5/6 effort channel).
        self.assertEqual(captured["model"], "gpt-6-luna")
        self.assertEqual(
            captured["settings"].extra_body["reasoning"], {"effort": "medium"}
        )

        # ... and the run really happened on that configuration.
        self.assertEqual(summary, "MODEL-OVERRIDE-DONE")
        self.assertIn("meticulous reviewer", scripted.requests[0]["instructions"])

    async def test_unknown_definition_model_falls_back_to_the_resolved_config(self):
        """An unknown model name is ignored: the run keeps claude-sonnet-5
        (the same behaviour the loader/conf resolution had before)."""
        self._write_reviewer_agent(extra_frontmatter="model: gpt-5.6-luna")
        definition = get_agent_definition(self.workspace, "reviewer")
        self.assertEqual(definition.model, "gpt-5.6-luna")

        context = self._make_context()
        with patch(
            "siada.services.sub_agent_run_config.resolve_sub_agent_llm_config",
            return_value=context.session.siada_config.llm_config,
        ):
            run_config = build_sub_agent_run_config(
                context, effort=definition.effort, model=definition.model
            )

        self.assertEqual(run_config.model, "claude-sonnet-5")


if __name__ == "__main__":
    unittest.main()
