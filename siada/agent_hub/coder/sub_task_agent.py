"""
Sub-Task Agent Module

Provides SubTaskAgent: a general-purpose unattended sub-agent that executes a
bounded task in a clean context window and returns a summary.
"""
from agents import Agent, RunContextWrapper

from siada.agent_hub.hooks.siada_basic_agent_hooks import SiadaBasicAgentHooks
from siada.agent_hub.coder.prompt.base.tool_use import get_tool_use_section, should_enable_parallel_tool_calls_in_prompt
from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.ast.ast_tool import list_code_definition_names
from siada.tools.coder.file_operator import edit
from siada.tools.coder.file_search import regex_search_files
from siada.tools.coder.run_cmd import run_cmd
from siada.tools.coder.run_powershell import get_run_powershell_tool_if_available
from siada.tools.web import web_search, web_fetch


_SUBTASK_PARALLEL_ENHANCEMENT = (
    "\n\nFor efficiency, always parallelize independent operations in a single response"
    " — especially reads and searches."
    " Only serialize when a later call depends on an earlier result."
)

_SUBTASK_SYSTEM_PROMPT_BASE = """\
You are a highly skilled software engineer executing a specific, bounded task.

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


def _build_subtask_instructions(
    run_context: RunContextWrapper[CodeAgentContext], agent: "SubTaskAgent"
) -> str:
    root_dir = run_context.context.root_dir

    enable_parallel = should_enable_parallel_tool_calls_in_prompt(run_context)
    model_name = None
    try:
        model_name = run_context.context.session.siada_config.llm_config.model_name
    except (AttributeError, TypeError):
        pass

    tool_use_section = get_tool_use_section(
        enable_parallel_tool_calls=enable_parallel,
        model_name=model_name,
    )

    if enable_parallel:
        tool_use_section += _SUBTASK_PARALLEL_ENHANCEMENT

    prompt = (
        _SUBTASK_SYSTEM_PROMPT_BASE
        + f"\n## Working Directory\n\n"
        + f"The current working directory is: `{root_dir}`\n"
        + f"\n{tool_use_section}\n"
        + f"\n{_get_skills_hint_section(root_dir)}\n"
    )
    return prompt


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


def _build_default_tools(web_tools_enabled: bool = True) -> list:
    """Build the fixed tool set for SubTaskAgent.

    Mirrors ``CodeGenAgent._get_base_tools()`` minus:
    - memory tools (search_memory / memory / fact_store / fact_feedback): the
      sub-agent runs with a clean conversation history and shouldn't
      participate in long-term memory recall or curation.
    - run_subtask: prevents recursion (sub-agent spawning sub-agents).
    - todo_write: the sub-agent works on a single bounded task and doesn't
      need a TODO list (the parent agent owns the high-level plan).

    Web tools are added when ``web_tools_enabled`` is True (resolved by the
    caller from the parent context's provider + web switch) and the optional
    internal package exposes them. Lark tools are intentionally not added —
    they're parent-agent-specific and depend on session-bound credentials.
    """
    tools = [edit, regex_search_files, run_cmd, list_code_definition_names]
    if web_tools_enabled:
        if web_search is not None:
            tools.append(web_search)
        if web_fetch is not None:
            tools.append(web_fetch)
    pwsh = get_run_powershell_tool_if_available()
    if pwsh is not None:
        tools.append(pwsh)
    return tools


class SubTaskAgent(Agent):
    """
    General-purpose unattended sub-agent that executes a bounded task.

    Ships with a fixed tool set derived from ``CodeGenAgent`` (minus memory
    tools and minus ``run_subtask`` to prevent recursion). MCP servers,
    long-term memory, and lark tools are intentionally NOT included.
    """

    def __init__(self, web_tools_enabled: bool = True):
        super().__init__(
            name="SubTaskAgent",
            instructions=_build_subtask_instructions,
            tools=_build_default_tools(web_tools_enabled=web_tools_enabled),
            # Scope AGENT_NAME per LLM call so the X-Siada-Event-Type header
            # is tagged as "SubTaskAgent" and then cleared on on_llm_end —
            # prevents the tag from leaking back into the parent agent's
            # follow-up requests on the same asyncio task.
            hooks=SiadaBasicAgentHooks(),
        )
