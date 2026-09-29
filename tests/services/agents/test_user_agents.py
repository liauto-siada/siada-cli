"""
Tests for siada/services/agents - user-defined agent definitions
(``.agents/agents/*.md`` and the compatibility layouts).

Covers the definition file format (frontmatter parsing + validation), root
priority/deduplication, prompt rendering, and the runtime helpers that apply a
definition to a sub-agent spawn (tool filtering, skill preloading, effort
mapping, MCP server resolution).
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from siada.services.agents import (
    AgentScope,
    filter_tools_for_agent,
    get_agent_definition,
    get_agents_section,
    load_agents_for_cwd,
    load_preloaded_skills,
    normalize_tool_names,
    open_agent_mcp_servers,
    parse_agent_file,
    render_agents_section,
    resolve_effort_for_model,
)
from siada.services.agents.runtime import _split_mcp_specs


def _write(root: Path, name: str, content: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / name
    path.write_text(content, encoding="utf-8")
    return path


VALID_DEFINITION = """---
name: code-reviewer
description: Reviews diffs for bugs, style and security issues.
tools: [read_file, regex_search_files, run_cmd]
skills: [wiki, open-source-release]
mcpServers:
  - lark
background: true
effort: high
model: gpt-6-luna
---

You are a meticulous code reviewer. Report findings with file:line references.
"""


class _FakeTool:
    def __init__(self, name: str):
        self.name = name


# ============================================================================
# Loader: file parsing
# ============================================================================


class TestParseAgentFile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _parse(self, content: str, filename: str = "agent.md"):
        path = _write(self.root, filename, content)
        return parse_agent_file(path, AgentScope.REPO)

    def test_parses_every_supported_field(self):
        definition = self._parse(VALID_DEFINITION)

        self.assertEqual(definition.name, "code-reviewer")
        self.assertIn("meticulous code reviewer", definition.prompt)
        self.assertEqual(
            definition.tools, ["read_file", "regex_search_files", "run_cmd"]
        )
        self.assertEqual(definition.skills, ["wiki", "open-source-release"])
        self.assertEqual(definition.mcp_servers, ["lark"])
        self.assertTrue(definition.background)
        self.assertEqual(definition.effort, "high")
        self.assertEqual(definition.model, "gpt-6-luna")
        self.assertEqual(definition.scope, AgentScope.REPO)

    def test_prompt_body_excludes_frontmatter(self):
        definition = self._parse(VALID_DEFINITION)
        self.assertNotIn("---", definition.prompt)
        self.assertNotIn("name: code-reviewer", definition.prompt)
        self.assertTrue(definition.prompt.startswith("You are a meticulous"))

    def test_missing_name_is_a_load_error(self):
        from siada.services.agents import AgentDefinitionParseError

        with self.assertRaises(AgentDefinitionParseError):
            self._parse("---\ndescription: no name here\n---\n\nBody\n")

    def test_missing_description_is_a_load_error(self):
        from siada.services.agents import AgentDefinitionParseError

        with self.assertRaises(AgentDefinitionParseError):
            self._parse("---\nname: no-desc\n---\n\nBody\n")

    def test_missing_frontmatter_is_a_load_error(self):
        from siada.services.agents import AgentDefinitionParseError

        with self.assertRaises(AgentDefinitionParseError):
            self._parse("Just markdown, no frontmatter.\n")

    def test_tools_accept_comma_separated_string(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\ntools: read_file, run_cmd\n---\n\nBody\n"
        )
        self.assertEqual(definition.tools, ["read_file", "run_cmd"])

    def test_tools_star_means_all(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\ntools: ['*']\n---\n\nBody\n"
        )
        self.assertEqual(definition.tools, ["*"])

    def test_tools_are_mapped_from_claude_code_names(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\ntools: [Read, Bash, Grep, Task]\n---\n\nBody\n"
        )
        self.assertEqual(
            definition.tools, ["read_file", "run_cmd", "regex_search_files", "run_subtask"]
        )

    def test_tools_omitted_stays_none(self):
        definition = self._parse("---\nname: a\ndescription: d\n---\n\nBody\n")
        self.assertIsNone(definition.tools)

    def test_skills_are_lowercased(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\nskills: Wiki, Open-Source-Release\n---\n\nBody\n"
        )
        self.assertEqual(definition.skills, ["wiki", "open-source-release"])

    def test_mcp_servers_accept_names_and_inline_definitions(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\n"
            "mcpServers:\n"
            "  - lark\n"
            "  - browser: {url: 'https://example.test/mcp'}\n"
            "---\n\nBody\n"
        )
        self.assertEqual(
            definition.mcp_servers,
            ["lark", {"browser": {"url": "https://example.test/mcp"}}],
        )

    def test_background_string_true_is_accepted(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\nbackground: 'true'\n---\n\nBody\n"
        )
        self.assertTrue(definition.background)

    def test_background_invalid_value_degrades_to_false(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\nbackground: sometimes\n---\n\nBody\n"
        )
        self.assertFalse(definition.background)

    def test_effort_invalid_value_is_dropped(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\neffort: ludicrous\n---\n\nBody\n"
        )
        self.assertIsNone(definition.effort)

    def test_model_omitted_stays_none(self):
        definition = self._parse("---\nname: a\ndescription: d\n---\n\nBody\n")
        self.assertIsNone(definition.model)

    def test_model_inherit_means_not_configured(self):
        # Claude Code's explicit "same model as the main agent" is expressed in
        # Siada as "not configured", which already resolves to the conf.yaml
        # sub-agent model (or the parent's model).
        definition = self._parse(
            "---\nname: a\ndescription: d\nmodel: inherit\n---\n\nBody\n"
        )
        self.assertIsNone(definition.model)

    def test_model_invalid_value_is_dropped(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\nmodel: [not, a, string]\n---\n\nBody\n"
        )
        self.assertIsNone(definition.model)

    def test_unknown_frontmatter_fields_are_ignored(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\npermissionMode: acceptEdits\n"
            "color: blue\n---\n\nBody\n"
        )
        self.assertEqual(definition.name, "a")

    def test_unquoted_colon_in_description_is_recovered(self):
        # Real third-party packs ship descriptions like this one; strict YAML
        # rejects them ("Triggers on: ..."), but the definition must still load.
        definition = self._parse(
            "---\n"
            "name: ab-test-analysis\n"
            "description: Use when the user wants to analyze A/B test results. "
            "Triggers on: 'analyze A/B test', 'p-value', 'did it work'.\n"
            "tools: Read, Grep, Glob\n"
            "---\n\nBody\n"
        )
        self.assertEqual(definition.name, "ab-test-analysis")
        self.assertIn("Triggers on: 'analyze A/B test'", definition.description)
        self.assertEqual(
            definition.tools, ["read_file", "regex_search_files"]
        )

    def test_unrecoverable_frontmatter_is_still_an_error(self):
        from siada.services.agents import AgentDefinitionParseError

        with self.assertRaises(AgentDefinitionParseError):
            self._parse("---\nname: [unclosed\n  description: d\n---\n\nBody\n")

    def test_tools_are_deduplicated_after_alias_mapping(self):
        definition = self._parse(
            "---\nname: a\ndescription: d\n"
            "tools: Read, Write, Edit, Bash, Glob, Grep\n---\n\nBody\n"
        )
        self.assertEqual(
            definition.tools,
            ["read_file", "edit_file", "run_cmd", "regex_search_files"],
        )


# ============================================================================
# Loader: discovery, priority and deduplication
# ============================================================================


class TestAgentRoots(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "home"
        self.cwd = self.root / "repo"
        self.cwd.mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)
        # Hermetic user scope: never read the developer's own
        # ~/.claude/agents or ~/.agents/agents.
        home_patch = patch("pathlib.Path.home", return_value=self.home)
        home_patch.start()
        self.addCleanup(home_patch.stop)

    def _load(self):
        return load_agents_for_cwd(self.cwd, siada_home=self.home)

    def test_discovers_nested_markdown_files(self):
        _write(self.cwd / ".agents" / "agents" / "team", "nested.md",
               "---\nname: nested\ndescription: nested agent\n---\n\nBody\n")

        outcome = self._load()
        self.assertEqual([a.name for a in outcome.agents], ["nested"])

    def test_non_markdown_files_are_ignored(self):
        _write(self.cwd / ".agents" / "agents", "README.txt", "not an agent")
        _write(self.cwd / ".agents" / "agents", "ok.md",
               "---\nname: ok\ndescription: d\n---\n\nBody\n")

        outcome = self._load()
        self.assertEqual([a.name for a in outcome.agents], ["ok"])

    def test_siada_cli_layout_wins_over_agents_layout(self):
        _write(self.cwd / ".agents" / "agents", "a.md",
               "---\nname: dup\ndescription: from .agents\n---\n\nBody\n")
        _write(self.cwd / ".siada-cli" / "agents", "a.md",
               "---\nname: dup\ndescription: from .siada-cli\n---\n\nBody\n")

        definition = self._load().get("dup")
        self.assertEqual(definition.description, "from .siada-cli")

    def test_agents_layout_wins_over_claude_layout(self):
        _write(self.cwd / ".claude" / "agents", "a.md",
               "---\nname: dup\ndescription: from .claude\n---\n\nBody\n")
        _write(self.cwd / ".agents" / "agents", "a.md",
               "---\nname: dup\ndescription: from .agents\n---\n\nBody\n")

        definition = self._load().get("dup")
        self.assertEqual(definition.description, "from .agents")

    def test_user_scope_wins_over_repo_scope(self):
        _write(self.cwd / ".agents" / "agents", "a.md",
               "---\nname: dup\ndescription: from repo\n---\n\nBody\n")
        _write(self.home / "agents", "a.md",
               "---\nname: dup\ndescription: from user\n---\n\nBody\n")

        definition = self._load().get("dup")
        self.assertEqual(definition.description, "from user")
        self.assertEqual(definition.scope, AgentScope.USER)

    def test_broken_definition_is_reported_without_hiding_valid_ones(self):
        _write(self.cwd / ".agents" / "agents", "broken.md",
               "---\ndescription: missing name\n---\n\nBody\n")
        _write(self.cwd / ".agents" / "agents", "good.md",
               "---\nname: good\ndescription: d\n---\n\nBody\n")

        outcome = self._load()
        self.assertEqual([a.name for a in outcome.agents], ["good"])
        self.assertEqual(len(outcome.errors), 1)

    def test_lookup_is_case_insensitive(self):
        _write(self.cwd / ".agents" / "agents", "a.md",
               "---\nname: MixedCase\ndescription: d\n---\n\nBody\n")

        self.assertIsNotNone(self._load().get("mixedcase"))
        self.assertIsNotNone(get_agent_definition(self.cwd, "MIXEDCASE", siada_home=self.home))

    def test_missing_roots_are_not_an_error(self):
        outcome = self._load()
        self.assertEqual(outcome.agents, [])
        self.assertEqual(outcome.errors, [])


# ============================================================================
# Renderer
# ============================================================================


class TestRenderAgentsSection(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        # Hermetic user scope (see TestAgentRoots).
        home_patch = patch("pathlib.Path.home", return_value=self.root / "home")
        home_patch.start()
        self.addCleanup(home_patch.stop)

    def _definition(self, name: str, description: str):
        path = _write(self.root, f"{name}.md",
                      f"---\nname: {name}\ndescription: {description}\n---\n\nBody\n")
        return parse_agent_file(path, AgentScope.REPO)

    def test_empty_list_renders_nothing(self):
        self.assertIsNone(render_agents_section([]))

    def test_section_lists_name_and_description(self):
        section = render_agents_section([self._definition("reviewer", "Reviews diffs.")])

        self.assertIn("AGENT TYPES", section)
        self.assertIn("- `reviewer` — Reviews diffs.", section)
        self.assertIn('agent: "<name>"', section)

    def test_section_omits_agents_beyond_the_budget(self):
        from siada.services.agents.config import MAX_DESCRIPTION_LENGTH
        from siada.services.agents.renderer import MAX_AGENTS_SECTION_CHARS

        # Each description is at the parse-time cap, so four entries overflow
        # the section budget.
        long_description = "x" * MAX_DESCRIPTION_LENGTH
        agents = [
            self._definition(f"agent-{index}", long_description) for index in range(5)
        ]
        section = render_agents_section(agents)

        self.assertIn("`agent-0`", section)
        self.assertNotIn("`agent-4`", section)
        self.assertIn("omitted", section)
        self.assertLessEqual(len(section), MAX_AGENTS_SECTION_CHARS + 500)

    def test_get_agents_section_is_none_without_definitions(self):
        self.assertIsNone(get_agents_section(self.root))

    def test_get_agents_section_renders_definitions(self):
        _write(self.root / ".agents" / "agents", "a.md",
               "---\nname: helper\ndescription: Helps out.\n---\n\nBody\n")

        section = get_agents_section(self.root)
        self.assertIn("`helper` — Helps out.", section)


class TestPromptInjection(unittest.TestCase):
    """The catalog reaches the main agent's prompt only when it is usable."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        home_patch = patch("pathlib.Path.home", return_value=self.root / "home")
        home_patch.start()
        self.addCleanup(home_patch.stop)
        _write(
            self.root / ".agents" / "agents",
            "reviewer.md",
            "---\nname: reviewer\ndescription: Reviews diffs.\n---\n\nBody\n",
        )

    def _prompt(self, subagent_enabled: bool) -> str:
        from siada.agent_hub.coder.prompt import code_gen_prompt

        with patch.object(code_gen_prompt, "get_username", lambda: None):
            return code_gen_prompt.get_system_prompt(
                str(self.root),
                model_name="claude-sonnet-5",
                subagent_enabled=subagent_enabled,
            )

    def test_catalog_is_injected_when_the_feature_is_on(self):
        prompt = self._prompt(subagent_enabled=True)
        self.assertIn("AGENT TYPES", prompt)
        self.assertIn("- `reviewer` — Reviews diffs.", prompt)

    def test_catalog_is_dropped_when_the_feature_is_off(self):
        # `sub_agent.enabled: false` removes the `run_subtask` tool, so the
        # prompt must not mention the tool or any launchable agent.
        prompt = self._prompt(subagent_enabled=False)
        self.assertNotIn("AGENT TYPES", prompt)
        self.assertNotIn("run_subtask", prompt)


# ============================================================================
# Runtime: tools
# ============================================================================


class TestFilterToolsForAgent(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.default_tools = [
            _FakeTool("edit_file"),
            _FakeTool("regex_search_files"),
            _FakeTool("run_cmd"),
            _FakeTool("run_subtask"),
        ]

    def _definition(self, tools_line: str = ""):
        content = "---\nname: a\ndescription: d\n" + tools_line + "---\n\nBody\n"
        path = _write(self.root, "a.md", content)
        return parse_agent_file(path, AgentScope.REPO)

    def test_no_tools_field_keeps_the_default_set(self):
        definition = self._definition()
        self.assertEqual(
            filter_tools_for_agent(self.default_tools, definition), self.default_tools
        )

    def test_star_keeps_the_default_set(self):
        definition = self._definition("tools: ['*']\n")
        self.assertEqual(
            filter_tools_for_agent(self.default_tools, definition), self.default_tools
        )

    def test_subset_keeps_only_named_tools(self):
        definition = self._definition("tools: [run_cmd, run_subtask]\n")
        kept = filter_tools_for_agent(self.default_tools, definition)
        self.assertEqual([t.name for t in kept], ["run_cmd", "run_subtask"])

    def test_unknown_names_are_dropped(self):
        definition = self._definition("tools: [run_cmd, does_not_exist]\n")
        kept = filter_tools_for_agent(self.default_tools, definition)
        self.assertEqual([t.name for t in kept], ["run_cmd"])

    def test_all_unknown_names_fall_back_to_the_default_set(self):
        definition = self._definition("tools: [does_not_exist]\n")
        kept = filter_tools_for_agent(self.default_tools, definition)
        self.assertEqual(kept, self.default_tools)

    def test_file_tool_group_keeps_whichever_member_exists(self):
        # A definition naming `read_file` (native-patch surface) must still get
        # a working editing surface on a chat-completions model, whose default
        # set exposes `edit_file` instead.
        definition = self._definition("tools: [read_file, run_cmd]\n")
        kept = filter_tools_for_agent(self.default_tools, definition)
        self.assertEqual([t.name for t in kept], ["edit_file", "run_cmd"])

    def test_normalize_tool_names_passes_siada_names_through(self):
        self.assertEqual(
            normalize_tool_names(["run_cmd", "apply_patch"]),
            ["run_cmd", "apply_patch"],
        )


# ============================================================================
# Runtime: skills
# ============================================================================


class TestPreloadedSkills(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.home = self.root / "siada-home"
        self.cwd = self.root / "repo"
        self.cwd.mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)
        home_patch = patch("pathlib.Path.home", return_value=self.root / "user-home")
        home_patch.start()
        self.addCleanup(home_patch.stop)

        from siada.services.skills import SkillsManager

        # Rebuild the singleton against a throwaway siada home so the test
        # never touches the developer's real skills.
        SkillsManager.reset_instance()
        self.manager = SkillsManager(siada_home=self.home)
        self.addCleanup(SkillsManager.reset_instance)

        _write(
            self.cwd / ".agents" / "skills" / "review-helper",
            "SKILL.md",
            "---\nname: review-helper\ndescription: Helps with reviews.\n---\n\n"
            "# Review helper\n\nRead the diff twice.\n",
        )

    def _definition(self, skills_line: str):
        path = _write(
            self.cwd / ".agents" / "agents",
            "a.md",
            f"---\nname: a\ndescription: d\n{skills_line}---\n\nBody\n",
        )
        return parse_agent_file(path, AgentScope.REPO)

    def test_no_skills_configured_returns_nothing(self):
        self.assertEqual(load_preloaded_skills(self._definition(""), self.cwd), [])

    def test_named_skill_body_is_loaded_without_frontmatter(self):
        skills = load_preloaded_skills(
            self._definition("skills: [review-helper]\n"), self.cwd
        )

        self.assertEqual(len(skills), 1)
        self.assertEqual(skills[0].name, "review-helper")
        self.assertIn("Read the diff twice.", skills[0].content)
        self.assertNotIn("description:", skills[0].content)

    def test_unknown_skill_is_skipped(self):
        skills = load_preloaded_skills(
            self._definition("skills: [review-helper, nope]\n"), self.cwd
        )

        self.assertEqual([s.name for s in skills], ["review-helper"])


# ============================================================================
# Runtime: effort
# ============================================================================


class TestResolveEffortForModel(unittest.TestCase):
    def test_no_effort_configured_returns_none(self):
        self.assertIsNone(resolve_effort_for_model(None, "kivy-glm-5.3"))

    def test_level_accepted_by_the_model_passes_through(self):
        self.assertEqual(resolve_effort_for_model("high", "kivy-glm-5.3"), "high")

    def test_level_not_accepted_maps_to_the_nearest_neighbour(self):
        # GLM-5.3 accepts low/high/max — "medium" is the default-abroad tier
        # that aligns with "high".
        self.assertEqual(resolve_effort_for_model("medium", "kivy-glm-5.3"), "high")

    def test_level_unknown_to_the_model_maps_to_the_nearest_neighbour(self):
        # xhigh is a Claude-only tier; on a plain low/medium/high model the
        # nearest (and stronger) neighbour is "high".
        self.assertEqual(
            resolve_effort_for_model("xhigh", "unknown-model-xyz", "medium"), "high"
        )

    def test_unrecognised_level_falls_back_to_the_model_default(self):
        self.assertEqual(
            resolve_effort_for_model("ludicrous", "unknown-model-xyz", "medium"),
            "medium",
        )


# ============================================================================
# Runtime: MCP servers
# ============================================================================


class TestAgentMcpServers(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _definition(self, mcp_line: str):
        path = _write(
            self.root,
            "a.md",
            f"---\nname: a\ndescription: d\n{mcp_line}---\n\nBody\n",
        )
        return parse_agent_file(path, AgentScope.REPO)

    def test_no_mcp_servers_yields_empty_list(self):
        import asyncio

        async def _run():
            async with open_agent_mcp_servers(self._definition("")) as servers:
                return servers

        self.assertEqual(asyncio.run(_run()), [])

    def test_unknown_server_name_is_skipped(self):
        definition = self._definition("mcpServers: [ghost]\n")

        with patch(
            "siada.services.agents.runtime._global_connected_servers", return_value={}
        ), patch(
            "siada.services.agents.runtime._configured_server_configs", return_value={}
        ):
            reused, to_create = _split_mcp_specs(definition.mcp_servers)

        self.assertEqual(reused, [])
        self.assertEqual(to_create, [])

    def test_configured_server_name_is_scheduled_for_connection(self):
        from siada.config.mcp_config import MCPServerConfig

        definition = self._definition("mcpServers: [lark]\n")
        fake_config = MCPServerConfig(command="lark-mcp")

        with patch(
            "siada.services.agents.runtime._global_connected_servers", return_value={}
        ), patch(
            "siada.services.agents.runtime._configured_server_configs",
            return_value={"lark": fake_config},
        ):
            reused, to_create = _split_mcp_specs(definition.mcp_servers)

        self.assertEqual(reused, [])
        self.assertEqual([server.name for server in to_create], ["lark"])

    def test_already_connected_server_is_reused_not_reconnected(self):
        definition = self._definition("mcpServers: [lark]\n")
        connected_server = object()

        with patch(
            "siada.services.agents.runtime._global_connected_servers",
            return_value={"lark": connected_server},
        ), patch(
            "siada.services.agents.runtime._configured_server_configs",
            return_value={"lark": object()},
        ):
            reused, to_create = _split_mcp_specs(definition.mcp_servers)

        self.assertEqual(reused, [connected_server])
        self.assertEqual(to_create, [])

    def test_inline_definition_builds_a_server(self):
        definition = self._definition(
            "mcpServers:\n  - browser: {url: 'https://example.test/mcp'}\n"
        )

        with patch(
            "siada.services.agents.runtime._global_connected_servers", return_value={}
        ), patch(
            "siada.services.agents.runtime._configured_server_configs", return_value={}
        ):
            _, to_create = _split_mcp_specs(definition.mcp_servers)

        self.assertEqual([server.name for server in to_create], ["browser"])

    def test_disabled_server_is_skipped(self):
        from siada.config.mcp_config import MCPServerConfig

        definition = self._definition("mcpServers: [off]\n")

        with patch(
            "siada.services.agents.runtime._global_connected_servers", return_value={}
        ), patch(
            "siada.services.agents.runtime._configured_server_configs",
            return_value={"off": MCPServerConfig(command="x", enabled=False)},
        ):
            reused, to_create = _split_mcp_specs(definition.mcp_servers)

        self.assertEqual(reused, [])
        self.assertEqual(to_create, [])


if __name__ == "__main__":
    unittest.main()
