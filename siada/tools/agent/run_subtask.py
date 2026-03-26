"""
run_subtask tool

Launches a SubTaskAgent with a clean context window to execute a bounded task.
"""
from typing import Optional

from agents import RunContextWrapper, Runner, RunConfig, function_tool, RunItemStreamEvent, RawResponsesStreamEvent
from agents.items import ToolCallItem, ToolCallOutputItem, MessageOutputItem

from siada.agent_hub.coder.sub_task_agent import SubTaskAgent, SubTaskResult  # noqa: F401
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.logging import logger as logging
from siada.foundation.setting import settings
from siada.io.stream_utils import render_tool_call_output
from siada.services.sub_agent_run_config import build_sub_agent_run_config
from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory


RUN_SUBTASK_DOCS = """\
Launch a sub-agent with a clean context window to execute a specific, bounded task.

**Only call this tool when the current instruction explicitly requires it.**
Do NOT invoke it autonomously based on your own judgment.

Args:
    instruction: The complete input for the sub-agent. The caller is responsible
        for assembling all necessary context (e.g. design document path, previous
        step result, task directive) into this single string.

Returns:
    SubTaskResult with fields:
        status: "completed" | "failed" | "blocked"
        summary: What was done, which files were modified, and key decisions made.
        blockers: (only when status == "blocked") Description of the blocker and
            suggested resolution.
"""


# ---- Helper functions --------------------------------


def _get_io(agent_context: CodeAgentContext):
    """Return the IO object from the session, or None if unavailable."""
    try:
        if agent_context.session and agent_context.session.siada_config:
            return agent_context.session.siada_config.io
    except Exception:
        pass
    return None


# ---- Implementation function --------------------------------

async def run_subtask_impl(
    instruction: str,
    agent_context: Optional[CodeAgentContext] = None,
    run_config: Optional[RunConfig] = None,
):
    """
    Internal implementation of run_subtask, intended to be called directly in tests.

    Args:
        instruction: The complete input for the sub-agent.
        agent_context: CodeAgentContext used for root_dir and IO push. When None,
            a minimal context with the current working directory is created.
        run_config: RunConfig to use. When None, one is built from the session
            config (requires an active agent session).

    Returns:
        SubTaskResult produced by the SubTaskAgent.
    """
    if run_config is None:
        run_config = build_sub_agent_run_config(agent_context)

    io = _get_io(agent_context)
    logging.info(f"[run_subtask] Launching sub-agent: {instruction[:80]}...")

    result = Runner.run_streamed(
        starting_agent=SubTaskAgent(),
        input=instruction,
        context=CodeAgentContext(root_dir=agent_context.root_dir),
        run_config=run_config,
        max_turns=settings.MAX_TURNS,
    )

    async for event in result.stream_events():
        if not isinstance(event, RunItemStreamEvent):
            continue

        item = event.item

        if isinstance(item, ToolCallItem):
            raw = item.raw_item
            tool_name = getattr(raw, "name", str(raw))
            call_id = getattr(raw, "call_id", "")
            arguments = getattr(raw, "arguments", "") or ""
            if io:
                formatter = ToolCallFormatterFactory.get_formatter(tool_name)
                content, _ = formatter.format_input(call_id, tool_name, arguments)
                io.advance_tool_call_stage()
                io.print_tool_call_all_stages(content, final=True)

        elif isinstance(item, ToolCallOutputItem):
            if io:
                render_tool_call_output(io, item.output)

        elif isinstance(item, MessageOutputItem):
            text_parts = [
                part.text
                for part in getattr(item.raw_item, "content", [])
                if getattr(part, "type", None) == "output_text" and hasattr(part, "text")
            ]
            if text_parts and io:
                text = "".join(text_parts)
                # Show sub-agent planning text as thinking-style (dim on terminal, thinking block on ACP)
                io.acp_thinking(text)
                if not io.acp_enabled:
                    io.console.print(text, style="dim")

    subtask_result: SubTaskResult = result.final_output
    logging.info(
        f"[run_subtask] Sub-agent finished — status: {subtask_result.status} | "
        f"summary: {subtask_result.summary[:120]}"
    )
    return subtask_result


# ---- Public tool function --------------------------------

@function_tool(name_override="run_subtask", description_override=RUN_SUBTASK_DOCS)
async def run_subtask(
    run_ctx: RunContextWrapper[CodeAgentContext],
    instruction: str,
):
    return await run_subtask_impl(
        instruction=instruction,
        agent_context=run_ctx.context,
    )
