"""
Memory Agent

Processes session conversations to generate structured memory files.

Architecture:
- Fixed system prompt  : defines the agent's role and the full memory landscape
- Task instruction list: one prompt per memory type, executed sequentially
- Shared context       : full conversation history passed between task runs
- Generic tool         : reuses edit_file for all file operations

To add a new memory type:
  1. Create task_instructions/<type>.py with an INSTRUCTION template
  2. Append a tuple to _build_task_list() below
"""

from pathlib import Path
from datetime import datetime
from agents import Agent, Runner, RunConfig, function_tool, RunContextWrapper
from siada.models.model_setting_converter import ModelSettingsConverter
from siada.provider.provider_factory import get_provider
from siada.services.model_wrapper import ModelProviderWrapper
from siada.services.input_processor import process_input
from siada.foundation.context import get_context_var, set_context_var, LLM_CONFIG, AGENT_NAME
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.logging import logger
from siada.tools.coder.file_operator import edit
from siada.services.memory.task_instructions.system_prompt import SYSTEM_PROMPT
from siada.services.memory.task_instructions.structured_event import INSTRUCTION as STRUCTURED_EVENT
from siada.services.memory.task_instructions.experience import INSTRUCTION as EXPERIENCE
from siada.tools.coder.file_search import regex_search_files


def _get_memory_dir() -> Path:
    memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    return memory_dir


# ---- Tools --------------------------------

@function_tool
def delete_memory_file(context: RunContextWrapper[CodeAgentContext], path: str) -> str:
    """
    Delete a file inside the memory directory.

    Only files under the memory directory (~/.siada-cli/workspace/memory/) are
    permitted. Attempts to delete files outside this boundary are rejected.

    Args:
        path: Absolute path to the memory file to delete.

    Returns:
        Success or error message.
    """
    memory_dir = _get_memory_dir().resolve()
    try:
        target = Path(path).resolve()
    except Exception as e:
        return f"Error: invalid path — {e}"

    if not str(target).startswith(str(memory_dir)):
        return f"Error: '{path}' is outside the memory directory. Only files under {memory_dir} may be deleted."

    if not target.exists():
        return f"Error: '{path}' does not exist."

    if not target.is_file():
        return f"Error: '{path}' is not a file."

    target.unlink()
    logger.info(f"[memory-agent] Deleted memory file: {target}")
    return f"Deleted: {path}"


def _list_dir_files(subdir: str) -> str:
    target = _get_memory_dir() / subdir
    lines = [f"{target}/"]
    for f in sorted(target.iterdir()):
        if not f.name.startswith("."):
            lines.append(f"  {f}")
    return "\n".join(lines)


def _build_task_list() -> list[tuple[str, str]]:
    """
    Ordered list of (task_name, instruction) pairs with memory_dir substituted.
    To add a new memory type: import its INSTRUCTION and append a tuple here.
    """
    memory_dir = str(_get_memory_dir())
    return [
        ("structured_event", STRUCTURED_EVENT.format(memory_dir=memory_dir, events_file_list=_list_dir_files("events"))),
        ("experience",       EXPERIENCE.format(memory_dir=memory_dir, experience_file_list=_list_dir_files("experience")))
    ]


# ---- Agent --------------------------------

def _get_memory_agent() -> Agent:
    system_prompt = SYSTEM_PROMPT.format(memory_dir=str(_get_memory_dir()))
    return Agent(
        name="MemoryAgent",
        instructions=system_prompt,
        tools=[edit, delete_memory_file, regex_search_files],
    )


# ---- Run Config --------------------------------

def _build_run_config() -> RunConfig:
    llm_config = get_context_var(LLM_CONFIG)
    if not llm_config:
        raise ValueError("[MemoryAgent] LLM_CONFIG not found in global context")

    model_settings = ModelSettingsConverter.convert_model_settings(llm_config)
    model_provider = get_provider(llm_config.provider)
    provider_wrapper = ModelProviderWrapper(
        base_provider=model_provider,
        input_processor=process_input,
    )

    logger.info(f"[MemoryAgent] model={llm_config.model_name} provider={llm_config.provider}")

    return RunConfig(
        tracing_disabled=getattr(llm_config, 'tracing_disabled', False),
        model=llm_config.model_name,
        model_provider=provider_wrapper,
        model_settings=model_settings,
    )


# ---- Main Entry Point --------------------------------

async def analyze_and_update_memory(session_content: str) -> dict:
    """
    Run all memory task instructions sequentially on the given session content.

    Each instruction is a separate Runner.run call. The full conversation history
    from previous tasks is forwarded to each subsequent task, so later instructions
    can leverage the complete reasoning context of earlier ones.
d
    Args:
        session_content: Formatted session conversation text

    Returns:
        dict with 'success' bool and 'completed_tasks' list
    """
    try:
        logger.info("[memory-agent] Starting memory pipeline")

        agent = _get_memory_agent()
        run_config = _build_run_config()
        # edit_file needs a CodeAgentContext; memory files use absolute paths
        # so root_dir points to the workspace directory
        workspace_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        for sub in ("events", "experience"):
            (workspace_dir / sub).mkdir(parents=True, exist_ok=True)
        agent_context = CodeAgentContext(root_dir=str(workspace_dir))

        task_list = _build_task_list()
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Seed the history with session content; all tasks append their instruction
        history = [{"role": "user", "content": (
            f"Current Time: {current_time}\n\n"
            f"Session content:\n\n{session_content}"
        )}]
        result = None
        completed = []

        # Set agent name in contextvars so LLM request headers can pick it up
        set_context_var(AGENT_NAME, "MemoryAgent")

        for i, (task_name, instruction) in enumerate(task_list, start=1):
            logger.info(f"[memory-agent] Task {i}/{len(task_list)}: {task_name}")
            if result is not None:
                history = result.to_input_list()
            result = await Runner.run(
                agent,
                input=history + [{"role": "user", "content": instruction}],
                run_config=run_config,
                context=agent_context,
                max_turns=30,
            )
            completed.append(task_name)

        final_history = result.to_input_list() if result is not None else history
        model_calls = sum(1 for msg in final_history if isinstance(msg, dict) and msg.get("role") == "assistant")
        logger.info(f"[memory-agent] Pipeline complete: {completed}, model_calls={model_calls}")
        return {"success": True, "completed_tasks": completed}

    except Exception as e:
        logger.error(f"[memory-agent] Pipeline failed: {e}", exc_info=True)
        return {"success": False, "error": str(e), "completed_tasks": []}
