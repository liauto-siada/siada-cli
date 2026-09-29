"""
Sub-Task Agent Module

Provides SubTaskAgent: a general-purpose unattended sub-agent that executes a
bounded task in a clean context window and returns a summary.
"""
from typing import Optional

from agents import Agent, RunContextWrapper

from siada.agent_hub.hooks.siada_basic_agent_hooks import SiadaBasicAgentHooks
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.coder.native_file_tools import create_native_apply_patch_tool, read_file
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.run_powershell import get_run_powershell_tool_if_available
from siada.tools.web import web_search, web_fetch
from siada.agent_hub.coder.prompt.base.gpt5_instructions import (
    uses_native_patch_file_tools,
)


_SUBTASK_IDENTITY = """\
You are a highly skilled software engineer executing a specific, bounded task.

"""

_SUBTASK_RUNTIME_RULES = """\
## Unattended Execution Rules

You MUST follow these rules strictly:

1. **Do NOT ask the user any questions or request any confirmations.** You operate completely autonomously.
2. **When facing ambiguity**, first consult any context provided in your input. If the context does not resolve the ambiguity, stop and describe the blocker in your final output — do NOT ask the user.
3. **Do NOT expand the scope of your work beyond the task instruction.** Complete exactly what is asked, nothing more.
4. **Do NOT stop early** unless you encounter an unresolvable blocker. Always attempt to complete the task.

## Inputs You Will Receive

Your input contains:
- **Context** (optional): background information provided by the caller — read and use it to understand the task scope.
- **Task instruction**: the specific task you must execute.

## Output Requirement

When you finish, summarize what you did, which files you modified, and any key decisions made.

"""

# The default sub-agent prompt: identity line + runtime rules. Kept as one
# constant so the default (non-user-agent) prompt is byte-identical to before.
_SUBTASK_SYSTEM_PROMPT_BASE = _SUBTASK_IDENTITY + _SUBTASK_RUNTIME_RULES



_SUBTASK_RECURSIVE_HINT = """\
## Delegating Part of Your Task

You have access to `run_subtask`, the same tool your parent agent used to
launch you. Use it ONLY if a piece of your own task has a clear,
self-contained boundary that would otherwise cost you a large amount of
unrelated intermediate exploration. You are the last level allowed to
delegate further — any sub-agent you launch cannot itself delegate again.

"""


_NATIVE_PATCH_FILE_TOOLS_HINT = """\
## File Changes

Use `read_file` to inspect files and `apply_patch` for every text-file creation,
update, deletion, or move. `edit_file` is not available in this run. Use focused
patches with enough unchanged context to identify one location.

"""


def _build_subtask_instructions(
    run_context: RunContextWrapper[CodeAgentContext], agent: "SubTaskAgent"
) -> str:
    root_dir = run_context.context.root_dir
    recursive_hint = (
        _SUBTASK_RECURSIVE_HINT
        if getattr(agent, "include_run_subtask", False)
        else ""
    )
    native_file_tools_hint = (
        _NATIVE_PATCH_FILE_TOOLS_HINT
        if uses_native_patch_file_tools(getattr(agent, "model_name", None))
        else ""
    )

    # A user-defined agent (`.agents/agents/*.md`) supplies its own persona as
    # the head of the prompt; the unattended runtime rules still apply, since a
    # sub-agent can never ask the user anything. Without a definition the
    # prompt starts with the default identity line, exactly as before.
    definition_prompt = (getattr(agent, "definition_prompt", None) or "").strip()
    if definition_prompt:
        head = (
            f"{_SUBTASK_SYSTEM_PROMPT_BASE}"
            f"====\n\n"
            f"{definition_prompt}\n\n"
        )
    else:
        head = _SUBTASK_SYSTEM_PROMPT_BASE

    prompt = (
        head
        + f"\n## Working Directory\n\n"
        + f"The current working directory is: `{root_dir}`\n"
        + f"\n{recursive_hint}"
        + f"\n{native_file_tools_hint}"
        + "\n" + _get_preloaded_skills_section(getattr(agent, "preloaded_skills", None))
        + f"\n{_get_skills_hint_section(root_dir)}\n"
    )
    return prompt


def _get_preloaded_skills_section(preloaded_skills) -> str:
    """Inline the SKILL.md bodies an agent definition asked to preload.

    ``skills: [wiki, open-source-release]`` in a definition means those skills
    are already part of the agent's instructions — it must not have to discover
    and read them at run time.
    """
    if not preloaded_skills:
        return ""

    parts = [
        "====\n",
        "## Preloaded Skills\n",
        "The following skills are preloaded for this run. Follow their "
        "instructions whenever the task touches their domain.\n",
    ]
    for skill in preloaded_skills:
        parts.append(
            f"\n### Skill: {skill.name} (from `{skill.path}`)\n\n{skill.content}\n"
        )
    return "\n".join(parts)



def _get_skills_hint_section(root_dir) -> str:
    """Return a compact hint that tells the sub-agent where SKILL.md files live.

    Unlike the parent agent, which materializes the full skill catalog into
    its prompt, the sub-agent only gets a directory hint. If a skill is
    actually needed, the sub-agent can list/read these directories on demand
    using ``run_cmd`` or ``regex_search_files`` — keeping the system prompt
    short while preserving access to the same skill set.
    """
    from siada.services.skills.config import (
        get_repo_agents_skills_root,
        get_repo_claude_skills_root,
        get_repo_skills_root,
        get_user_agents_skills_root,
        get_user_claude_skills_root,
        get_user_skills_root,
    )
    from pathlib import Path

    cwd = Path(root_dir)
    candidate_roots = [
        get_repo_skills_root(cwd),
        get_repo_agents_skills_root(cwd),
        get_repo_claude_skills_root(cwd),
        get_user_skills_root(),
        get_user_agents_skills_root(),
        get_user_claude_skills_root(),
    ]
    bullet_lines = "\n".join(f"- `{p}`" for p in candidate_roots)

    return (
        "====\n\n"
        "## Skills\n\n"
        "Skills are reusable instructions stored as `SKILL.md` files under "
        "the directories listed below. The parent agent has already discovered "
        "the full catalog; you don't get the rendered list to keep this prompt "
        "small. If a task hints at using a skill (or the user names one), "
        "list these directories with `run_cmd` (e.g. `ls <root>`) and read the "
        "matching `SKILL.md` before acting.\n\n"
        f"Candidate skill roots (relative to cwd `{root_dir}` and the user home):\n"
        f"{bullet_lines}\n"
    )


def _build_default_tools(
    web_tools_enabled: bool = False,
    include_run_subtask: bool = False,
    model_name: Optional[str] = None,
) -> list:
    """Build the fixed tool set for SubTaskAgent.

    Mirrors ``CodeGenAgent._get_base_tools()`` minus:
    - memory tools (search_memory / memory / fact_store / fact_feedback): the
      sub-agent runs with a clean conversation history and shouldn't
      participate in long-term memory recall or curation.
    - run_subtask: prevents recursion (sub-agent spawning sub-agents), UNLESS
      ``include_run_subtask=True`` — set by the caller (``run_subtask_impl``)
      only when ``sub_agent.allow_recursive_subagents`` is on AND this
      sub-agent is still below the nesting depth cap, so it may itself spawn
      one further level of nested sub-agents (see subagent_recursion.py).
    - todo_write: the sub-agent works on a single bounded task and doesn't
      need a TODO list (the parent agent owns the high-level plan).

    Web tools are added when ``web_tools_enabled`` is True (resolved by the
    caller from the parent context's provider + web switch) and the optional
    internal package exposes them. Lark tools are intentionally not added —
    they're parent-agent-specific and depend on session-bound credentials.
    """
    file_tools = (
        [read_file, create_native_apply_patch_tool()]
        if uses_native_patch_file_tools(model_name)
        else [edit]
    )
    tools = [*file_tools, regex_search_files, run_cmd, list_code_definition_names]
    if web_tools_enabled:
        if web_search is not None:
            tools.append(web_search)
        if web_fetch is not None:
            tools.append(web_fetch)
    pwsh = get_run_powershell_tool_if_available()
    if pwsh is not None:
        tools.append(pwsh)
    if include_run_subtask:
        from siada.tools.agent.run_subtask import run_subtask
        tools.append(run_subtask)
    return tools


class SubTaskAgent(Agent):
    """
    General-purpose unattended sub-agent that executes a bounded task.

    Two modes, selected by whether ``fork_tools`` / ``fork_instructions`` are
    provided:

    - **Non-fork (default)**: ships with a fixed, trimmed tool set derived
      from ``CodeGenAgent`` (minus memory tools and minus ``run_subtask`` to
      prevent recursion) and its own system prompt. MCP servers, long-term
      memory, and lark tools are intentionally NOT included — unless the caller
      spawned a user-defined agent (``.agents/agents/*.md``), in which case the
      definition's ``tools`` / ``skills`` / ``mcpServers`` decide the surface
      (see ``siada/services/agents``).
    - **Fork**: ``fork_tools`` / ``fork_instructions`` are used verbatim
      instead of the trimmed set above, so the sub-agent's tool schema and
      system prompt are byte-for-byte identical to the parent agent's
      current turn — the two prefix layers Claude's prompt cache checks
      before the (also-aligned) message history. See ``run_subtask_impl``'s
      fork branch for where these are assembled from the parent's
      ``RunContextWrapper``.
    """

    def __init__(
        self,
        web_tools_enabled: bool = False,
        fork_tools: Optional[list] = None,
        fork_instructions: Optional[str] = None,
        include_run_subtask: bool = False,
        model_name: Optional[str] = None,
        definition_prompt: Optional[str] = None,
        preloaded_skills: Optional[list] = None,
        mcp_servers: Optional[list] = None,
        tools_override: Optional[list] = None,
    ):
        super().__init__(
            name="SubTaskAgent",
            instructions=fork_instructions if fork_instructions is not None else _build_subtask_instructions,
            tools=(
                fork_tools
                if fork_tools is not None
                else tools_override
                if tools_override is not None
                else _build_default_tools(
                    web_tools_enabled=web_tools_enabled,
                    include_run_subtask=include_run_subtask,
                    model_name=model_name,
                )
            ),
            mcp_servers=list(mcp_servers or []),

            # Scope AGENT_NAME per LLM call so the X-Siada-Event-Type header
            # is tagged as "SubTaskAgent" and then cleared on on_llm_end —
            # prevents the tag from leaking back into the parent agent's
            # follow-up requests on the same asyncio task.
            hooks=SiadaBasicAgentHooks(),
        )
        if mcp_servers:
            # Same strictness policy SiadaRunner applies to the main agent's
            # MCP servers.
            self.mcp_config = {"convert_schemas_to_strict": True}
        # Consulted by _build_subtask_instructions to decide whether to add
        # the recursive-delegation prompt hint. Not an Agent-native field —
        # attached post-init (Agent is a plain dataclass, no __slots__).
        self.include_run_subtask = include_run_subtask
        # The non-fork prompt needs the same file-tool contract as its tool
        # registration. Forked subagents already inherit both verbatim.
        self.model_name = model_name
        # User-defined agent support (non-fork only): the definition's Markdown
        # body heads the system prompt, its `skills` are inlined as preloaded
        # instructions, and `tools_override` carries the tool list the caller
        # filtered down from the definition's `tools`. Forked subagents inherit
        # the parent's prompt/tools verbatim and never see any of these.
        self.definition_prompt = definition_prompt
        self.preloaded_skills = list(preloaded_skills or [])
