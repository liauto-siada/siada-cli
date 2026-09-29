"""
Tests for the user-defined agent (`.agents/agents/*.md`) integration in
``run_subtask``.

Covers:
1. Tool-level resolution: the ``agent`` parameter picks up a definition, an
   unknown name is reported back as text (with the names that do exist), and a
   definition with ``background: true`` forces the background path.
2. ``run_subtask_impl`` wiring: the definition's prompt / tools / skills / MCP
   servers reach ``SubTaskAgent``, and its ``effort`` reaches the RunConfig
   builder.
3. ``SubTaskAgent`` prompt composition: the definition body heads the prompt,
   the unattended runtime rules still apply, preloaded skills are inlined, and
   the default (no definition) prompt is unchanged.

All tests avoid real network/LLM calls — Runner.run_streamed, SubTaskAgent and
the RunConfig builder are mocked, mirroring the style of
test_run_subtask_fork_async.py.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from agents import RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.services.agents import get_agent_definition
from siada.session.session_models import RunningSession
from siada.tools.agent.run_subtask import (
    run_subtask,
    run_subtask_impl,
    unknown_agent_message,
)


def _write_agent(root: Path, filename: str, content: str) -> Path:
    agents_dir = root / ".agents" / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    path = agents_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def _make_tool_context(run_ctx: RunContextWrapper):
    """Build a minimal ToolContext wrapping *run_ctx* for on_invoke_tool calls."""
    from agents.tool_context import ToolContext

    return ToolContext.from_agent_context(
        run_ctx,
        "call_1",
        tool_name="run_subtask",
        tool_arguments="{}",
    )


def _make_fake_result(summary: str = "agent summary"):
    fake_result = MagicMock()

    async def _stream():
        return
        yield  # pragma: no cover - keeps this an async generator

    fake_result.stream_events = _stream
    fake_result.final_output = summary
    return fake_result


# ============================================================================
# 1. Tool-level resolution
# ============================================================================


class TestRunSubtaskAgentParameter(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        # Hermetic user scope: never pick up agents installed in the
        # developer's own ~/.claude/agents or ~/.agents/agents.
        home_patch = patch("pathlib.Path.home", return_value=self.workspace / "home")
        home_patch.start()
        self.addCleanup(home_patch.stop)
        _write_agent(
            self.workspace,
            "reviewer.md",
            "---\nname: reviewer\ndescription: Reviews code.\n---\n\nReview code.\n",
        )
        _write_agent(
            self.workspace,
            "watcher.md",
            "---\nname: watcher\ndescription: Watches things.\n"
            "background: true\n---\n\nWatch things.\n",
        )

    def _run_ctx(self):
        return RunContextWrapper(context=CodeAgentContext(root_dir=str(self.workspace)))

    async def test_unknown_agent_is_reported_with_available_names(self):
        result = await run_subtask.on_invoke_tool(
            _make_tool_context(self._run_ctx()),
            json.dumps({"instruction": "do it", "agent": "ghost"}),
        )

        self.assertIn("Unknown agent 'ghost'", result)
        self.assertIn("`reviewer`", result)
        self.assertIn("`watcher`", result)

    async def test_unknown_agent_without_any_definitions_explains_the_layout(self):
        with tempfile.TemporaryDirectory() as empty:
            ctx = CodeAgentContext(root_dir=empty)
            result = await run_subtask.on_invoke_tool(
                _make_tool_context(RunContextWrapper(context=ctx)),
                json.dumps({"instruction": "do it", "agent": "ghost"}),
            )

        self.assertIn("no user-defined agents were found", result)
        self.assertIn(".agents/agents/", result)

    async def test_named_agent_is_passed_to_the_implementation(self):
        with patch(
            "siada.tools.agent.run_subtask.run_subtask_impl",
            new=AsyncMock(return_value="ok"),
        ) as mock_impl:
            result = await run_subtask.on_invoke_tool(
                _make_tool_context(self._run_ctx()),
                json.dumps({"instruction": "do it", "agent": "reviewer"}),
            )

        self.assertEqual(result, "ok")
        definition = mock_impl.await_args.kwargs["agent_definition"]
        self.assertEqual(definition.name, "reviewer")

    async def test_omitting_agent_keeps_the_generic_sub_agent(self):
        with patch(
            "siada.tools.agent.run_subtask.run_subtask_impl",
            new=AsyncMock(return_value="ok"),
        ) as mock_impl:
            await run_subtask.on_invoke_tool(
                _make_tool_context(self._run_ctx()),
                json.dumps({"instruction": "do it"}),
            )

        self.assertIsNone(mock_impl.await_args.kwargs["agent_definition"])

    async def test_background_definition_forces_the_background_path(self):
        with patch(
            "siada.tools.agent.run_subtask.register_background_subtask",
            return_value="task-42",
        ) as mock_register:
            result = await run_subtask.on_invoke_tool(
                _make_tool_context(self._run_ctx()),
                json.dumps({"instruction": "do it", "agent": "watcher"}),
            )

        mock_register.assert_called_once()
        self.assertIn("task-42", result)
        self.assertIn("background", result)

    async def test_definition_without_background_stays_synchronous(self):
        with patch(
            "siada.tools.agent.run_subtask.run_subtask_impl",
            new=AsyncMock(return_value="sync summary"),
        ) as mock_impl, patch(
            "siada.tools.agent.run_subtask.register_background_subtask"
        ) as mock_register:
            result = await run_subtask.on_invoke_tool(
                _make_tool_context(self._run_ctx()),
                json.dumps({"instruction": "do it", "agent": "reviewer"}),
            )

        self.assertEqual(result, "sync summary")
        mock_register.assert_not_called()
        mock_impl.assert_awaited_once()


# ============================================================================
# 2. run_subtask_impl wiring
# ============================================================================


class TestRunSubtaskImplWithUserAgent(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        home_patch = patch("pathlib.Path.home", return_value=self.workspace / "home")
        home_patch.start()
        self.addCleanup(home_patch.stop)
        _write_agent(
            self.workspace,
            "reviewer.md",
            "---\nname: reviewer\ndescription: Reviews code.\n"
            "tools: [run_cmd]\n"
            "effort: high\n"
            "model: gpt-6-luna\n"
            "---\n\nReview code carefully.\n",
        )
        self.definition = get_agent_definition(self.workspace, "reviewer")

    def _agent_context(self):
        # A real context (not a MagicMock) so `session` / `model_run_config`
        # resolve exactly like they do in production; the session itself is a
        # spec'd mock since no real model call happens in these tests.
        session = MagicMock(spec=RunningSession)
        session.siada_config = MagicMock()
        # A concrete model name: run_subtask_impl classifies it to pick the
        # model-family-specific file-tool surface.
        session.siada_config.llm_config.model_name = "claude-sonnet-5"
        context = CodeAgentContext(
            root_dir=str(self.workspace),
            session=session,
        )
        context.allow_recursive_subagents = False
        return context

    async def _run_impl(self, **kwargs):
        with patch(
            "siada.tools.agent.run_subtask.Runner.run_streamed",
            return_value=_make_fake_result(),
        ) as mock_run_streamed, patch(
            "siada.tools.agent.run_subtask.build_sub_agent_run_config",
            return_value=MagicMock(tracing_disabled=True),
        ) as mock_build_config, patch(
            "siada.tools.agent.run_subtask.SubTaskAgent"
        ) as mock_subtask_agent_cls:
            summary = await run_subtask_impl(
                instruction="review the diff",
                agent_context=self._agent_context(),
                **kwargs,
            )
        return summary, mock_run_streamed, mock_build_config, mock_subtask_agent_cls

    async def test_definition_drives_tools_prompt_and_effort(self):
        summary, _, mock_build_config, mock_subtask_agent_cls = await self._run_impl(
            agent_definition=self.definition
        )

        self.assertEqual(summary, "agent summary")

        # effort and model reach the RunConfig builder (mapped against the
        # effective model there)
        self.assertEqual(mock_build_config.call_args.kwargs["effort"], "high")
        self.assertEqual(mock_build_config.call_args.kwargs["model"], "gpt-6-luna")

        _, kwargs = mock_subtask_agent_cls.call_args
        self.assertEqual(kwargs["definition_prompt"], "Review code carefully.")
        self.assertEqual(
            [tool.name for tool in kwargs["tools_override"]], ["run_cmd"]
        )
        self.assertEqual(kwargs["mcp_servers"], [])
        # fork materials stay empty for a definition-driven run
        self.assertIsNone(kwargs["fork_tools"])
        self.assertIsNone(kwargs["fork_instructions"])

    async def test_fork_is_ignored_for_a_definition_driven_run(self):
        _, _, _, mock_subtask_agent_cls = await self._run_impl(
            agent_definition=self.definition,
            fork=True,
            run_ctx=MagicMock(),
        )

        _, kwargs = mock_subtask_agent_cls.call_args
        self.assertIsNone(kwargs["fork_tools"])
        self.assertIsNone(kwargs["fork_instructions"])

    async def test_no_definition_keeps_the_previous_behaviour(self):
        _, _, mock_build_config, mock_subtask_agent_cls = await self._run_impl()

        self.assertIsNone(mock_build_config.call_args.kwargs["effort"])
        self.assertIsNone(mock_build_config.call_args.kwargs["model"])

        _, kwargs = mock_subtask_agent_cls.call_args
        self.assertIsNone(kwargs["definition_prompt"])
        self.assertIsNone(kwargs["tools_override"])
        self.assertEqual(kwargs["preloaded_skills"], [])
        self.assertEqual(kwargs["mcp_servers"], [])

    async def test_definition_mcp_servers_are_opened_for_the_run(self):
        definition = MagicMock()
        definition.name = "with-mcp"
        definition.effort = None
        definition.prompt = "Body"
        definition.tools = None
        definition.skills = []
        definition.mcp_servers = ["lark"]

        sentinel = object()
        opened = MagicMock()
        opened.__aenter__ = AsyncMock(return_value=[sentinel])
        opened.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "siada.tools.agent.run_subtask.open_agent_mcp_servers",
            return_value=opened,
        ) as mock_open, patch(
            "siada.tools.agent.run_subtask.Runner.run_streamed",
            return_value=_make_fake_result(),
        ), patch(
            "siada.tools.agent.run_subtask.build_sub_agent_run_config",
            return_value=MagicMock(tracing_disabled=True),
        ), patch(
            "siada.tools.agent.run_subtask.SubTaskAgent"
        ) as mock_subtask_agent_cls:
            await run_subtask_impl(
                instruction="do it",
                agent_context=self._agent_context(),
                agent_definition=definition,
            )

        mock_open.assert_called_once_with(definition)
        opened.__aexit__.assert_awaited_once()
        _, kwargs = mock_subtask_agent_cls.call_args
        self.assertEqual(kwargs["mcp_servers"], [sentinel])

    async def test_unknown_agent_message_mentions_alternatives(self):
        message = unknown_agent_message("ghost", self._agent_context())
        self.assertIn("Unknown agent 'ghost'", message)
        self.assertIn("`reviewer`", message)

    async def test_real_sub_task_agent_gets_the_filtered_surface(self):
        """The real SubTaskAgent (not a mock) must carry the definition's
        prompt and the tool list filtered from the default set."""
        captured = {}

        def _capture(*args, **kwargs):
            captured["agent"] = kwargs["starting_agent"]
            return _make_fake_result()

        with patch(
            "siada.tools.agent.run_subtask.Runner.run_streamed",
            side_effect=_capture,
        ), patch(
            "siada.tools.agent.run_subtask.build_sub_agent_run_config",
            return_value=MagicMock(tracing_disabled=True),
        ):
            await run_subtask_impl(
                instruction="review the diff",
                agent_context=self._agent_context(),
                agent_definition=self.definition,
            )

        agent = captured["agent"]
        self.assertEqual(agent.definition_prompt, "Review code carefully.")
        self.assertEqual([tool.name for tool in agent.tools], ["run_cmd"])


class TestSubAgentEffort(unittest.TestCase):
    """The definition's `effort` must reach the RunConfig's model settings."""

    def _context(self, llm_config):
        session = MagicMock(spec=RunningSession)
        session.siada_config = MagicMock()
        session.siada_config.llm_config = llm_config
        session.siada_config.tracing_disabled = True
        return CodeAgentContext(root_dir="/tmp", session=session)

    def _build(self, llm_config, effort=None):
        from siada.services.sub_agent_run_config import build_sub_agent_run_config

        # Pin the effective sub-agent LLM config to the parent's, so the
        # assertion does not depend on the developer's own conf.yaml
        # `sub_agent.llm_config` override.
        with patch(
            "siada.services.sub_agent_run_config.resolve_sub_agent_llm_config",
            return_value=llm_config,
        ):
            return build_sub_agent_run_config(self._context(llm_config), effort=effort)

    def test_effort_is_applied_and_does_not_mutate_the_parent_config(self):
        from siada.models.model_run_config import ModelRunConfig

        parent_llm_config = ModelRunConfig("claude-sonnet-5")
        parent_llm_config.provider = "default"
        parent_effort_before = parent_llm_config.reasoning_effort

        run_config = self._build(parent_llm_config, effort="medium")

        # Claude 4.6+ carries the effort through output_config.
        self.assertEqual(
            run_config.model_settings.extra_args["output_config"], {"effort": "medium"}
        )
        # the parent session's own /effort setting is untouched
        self.assertEqual(parent_llm_config.reasoning_effort, parent_effort_before)
        self.assertIsNone(parent_llm_config.user_reasoning_effort)

    def test_no_effort_keeps_the_parent_config_settings(self):
        from siada.models.model_run_config import ModelRunConfig
        from siada.models.model_setting_converter import ModelSettingsConverter

        parent_llm_config = ModelRunConfig("claude-sonnet-5")
        parent_llm_config.provider = "default"
        expected = ModelSettingsConverter.convert_model_settings(parent_llm_config)

        run_config = self._build(parent_llm_config)

        self.assertEqual(run_config.model_settings.extra_args, expected.extra_args)
        self.assertEqual(run_config.model_settings.extra_body, expected.extra_body)


# ============================================================================
# 3. SubTaskAgent prompt composition
# ============================================================================


class TestSubTaskAgentDefinitionPrompt(unittest.TestCase):
    def _instructions(self, **kwargs) -> str:
        from siada.agent_hub.coder.sub_task_agent import SubTaskAgent, _build_subtask_instructions

        agent = SubTaskAgent(model_name=None, **kwargs)
        run_context = MagicMock()
        run_context.context.root_dir = "/tmp/workspace"
        return _build_subtask_instructions(run_context, agent)

    def test_default_prompt_is_unchanged(self):
        prompt = self._instructions()

        self.assertTrue(
            prompt.startswith(
                "You are a highly skilled software engineer executing a "
                "specific, bounded task."
            )
        )
        self.assertIn("## Unattended Execution Rules", prompt)
        self.assertNotIn("## Preloaded Skills", prompt)

    def test_base_prompt_precedes_the_definition_body(self):
        """A definition is appended to the standard sub-agent instructions.

        The base system prompt (identity + unattended rules) always comes
        first — runtime invariants are not configurable — and the definition's
        own prompt follows it.
        """
        prompt = self._instructions(definition_prompt="You are a code reviewer.")

        self.assertTrue(
            prompt.startswith(
                "You are a highly skilled software engineer executing a "
                "specific, bounded task."
            )
        )
        self.assertIn("## Unattended Execution Rules", prompt)
        self.assertIn("You are a code reviewer.", prompt)
        self.assertLess(
            prompt.index("## Unattended Execution Rules"),
            prompt.index("You are a code reviewer."),
        )
        self.assertIn("## Working Directory", prompt)

    def test_preloaded_skills_are_inlined(self):
        from siada.services.agents import PreloadedSkill

        prompt = self._instructions(
            definition_prompt="You are a code reviewer.",
            preloaded_skills=[
                PreloadedSkill(
                    name="review-helper",
                    path=Path("/tmp/skills/review-helper/SKILL.md"),
                    content="# Review helper\n\nRead the diff twice.",
                )
            ],
        )

        self.assertIn("## Preloaded Skills", prompt)
        self.assertIn("### Skill: review-helper", prompt)
        self.assertIn("Read the diff twice.", prompt)

    def test_definition_tools_replace_the_default_set(self):
        from siada.agent_hub.coder.sub_task_agent import SubTaskAgent

        agent = SubTaskAgent(model_name=None, tools_override=[])
        self.assertEqual(agent.tools, [])

    def test_mcp_servers_are_attached_to_the_agent(self):
        from siada.agent_hub.coder.sub_task_agent import SubTaskAgent

        server = MagicMock()
        agent = SubTaskAgent(model_name=None, mcp_servers=[server])
        self.assertEqual(agent.mcp_servers, [server])
        self.assertEqual(agent.mcp_config, {"convert_schemas_to_strict": True})


if __name__ == "__main__":
    unittest.main()
