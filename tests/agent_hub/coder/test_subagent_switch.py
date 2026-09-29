"""
Coverage for the ``sub_agent.enabled`` master switch (conf.yaml, default ON).

With the switch off:
- ``CodeGenAgent`` must not expose ``run_subtask`` (neither through the base
  tool builder nor through ``configure_tools_for_context``);
- the CAPABILITIES prompt section must not advertise ``run_subtask``;
- an invocation that still reaches the tool object (e.g. through an inherited
  fork tool list built before the switch was turned off) must be rejected
  instead of launching a sub-agent.
"""
import json
import unittest
from unittest.mock import AsyncMock, patch

from agents import RunContextWrapper
from agents.tool_context import ToolContext

from siada.agent_hub.coder.code_gen_agent import CodeGenAgent
from siada.agent_hub.coder.prompt import code_gen_prompt
from siada.agent_hub.coder.prompt.base.capabilities import get_capabilities_section
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.agent.run_subtask import run_subtask


# Model names covering both prompt families (native-patch vs default).
_MODEL_NAMES = (None, "claude-sonnet-5", "gpt-5.4", "gpt-6-astra")


def _tool_names(tools) -> set:
    return {getattr(tool, "name", None) for tool in tools}


def _context(subagent_enabled: bool) -> CodeAgentContext:
    context = CodeAgentContext(root_dir="/tmp/ws")
    context.subagent_enabled = subagent_enabled
    return context


class TestBaseTools(unittest.TestCase):
    def test_run_subtask_present_by_default(self):
        self.assertIn("run_subtask", _tool_names(CodeGenAgent()._get_base_tools()))

    def test_run_subtask_dropped_when_disabled(self):
        names = _tool_names(CodeGenAgent()._get_base_tools(include_run_subtask=False))
        self.assertNotIn("run_subtask", names)
        # Only the sub-agent tool is dropped — the rest of the surface stays.
        self.assertLessEqual(
            {"regex_search_files", "run_cmd", "list_code_definition_names", "todo_write"},
            names,
        )


class TestConfigureToolsForContext(unittest.TestCase):
    def test_enabled_context_exposes_run_subtask(self):
        agent = CodeGenAgent()
        agent.configure_tools_for_context(_context(True))
        self.assertIn("run_subtask", _tool_names(agent.tools))

    def test_disabled_context_hides_run_subtask(self):
        agent = CodeGenAgent()
        agent.configure_tools_for_context(_context(False))
        self.assertNotIn("run_subtask", _tool_names(agent.tools))


class TestPromptGuidance(unittest.TestCase):
    def test_bullet_kept_when_enabled(self):
        for model_name in _MODEL_NAMES:
            with self.subTest(model_name=model_name):
                self.assertIn(
                    "run_subtask", get_capabilities_section(model_name=model_name)
                )

    def test_bullet_dropped_when_disabled(self):
        for model_name in _MODEL_NAMES:
            with self.subTest(model_name=model_name):
                section = get_capabilities_section(
                    model_name=model_name, subagent_enabled=False
                )
                self.assertNotIn("run_subtask", section)
                # The section itself and its other tool bullets must survive.
                self.assertIn("CAPABILITIES", section)
                self.assertIn("todo_write", section)

    def test_system_prompt_drops_guidance_when_disabled(self):
        for model_name in (None, "gpt-5.4"):
            with self.subTest(model_name=model_name):
                enabled_prompt = code_gen_prompt.get_system_prompt(
                    "/cwd", model_name=model_name
                )
                disabled_prompt = code_gen_prompt.get_system_prompt(
                    "/cwd", model_name=model_name, subagent_enabled=False
                )
                self.assertIn("run_subtask", enabled_prompt)
                self.assertNotIn("run_subtask", disabled_prompt)


class TestToolLevelGuard(unittest.IsolatedAsyncioTestCase):
    """The tool object stays reachable through an inherited (fork) tool list."""

    @staticmethod
    def _tool_context(subagent_enabled: bool) -> ToolContext:
        run_ctx = RunContextWrapper(context=_context(subagent_enabled))
        return ToolContext.from_agent_context(
            run_ctx, "call_1", tool_name="run_subtask", tool_arguments="{}"
        )

    async def test_invocation_rejected_when_disabled(self):
        result = await run_subtask.on_invoke_tool(
            self._tool_context(False), json.dumps({"instruction": "do something"})
        )
        self.assertIn("disabled by configuration", result)

    async def test_invocation_proceeds_when_enabled(self):
        with patch(
            "siada.tools.agent.run_subtask.run_subtask_impl",
            new=AsyncMock(return_value="sub-agent summary"),
        ):
            result = await run_subtask.on_invoke_tool(
                self._tool_context(True), json.dumps({"instruction": "do something"})
            )
        self.assertEqual(result, "sub-agent summary")


if __name__ == "__main__":
    unittest.main(verbosity=2)