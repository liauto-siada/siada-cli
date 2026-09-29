"""
run_subtask tool

Launches a SubTaskAgent with a clean context window to execute a bounded task.

The whole feature is gated behind the ``sub_agent.enabled`` master switch
(conf.yaml, default true): when it is off, ``CodeGenAgent`` never puts this
tool in the agent's tool list, the matching capability bullet is dropped from
the system prompt, and this module's own entry point rejects any call that
still reaches it (see the ``subagent_enabled`` check in ``run_subtask``).

Two independent boolean parameters control how the sub-agent is launched:

- ``fork``: when True, the sub-agent's tools, system prompt, and message
  history are aligned byte-for-byte with the parent agent's current turn
  (see ``_run_fork_subtask``), so the model provider's prompt cache — which
  matches strictly on the ``tools -> system -> messages`` prefix — can be
  reused instead of starting cold. When False (default), the sub-agent gets
  its own trimmed tool set / prompt / empty history exactly as before.
- ``async_mode`` (model-facing name: ``async``): when True, the sub-agent run
  is scheduled as a background asyncio task and the tool returns immediately
  with a task id instead of waiting for completion. See
  ``siada.tools.agent.subagent_async`` for the background-task registry and
  parent-notification mechanism.
"""
from typing import Optional

from contextlib import AsyncExitStack
from pathlib import Path

from agents import RunContextWrapper, Runner, RunConfig, function_tool, RunItemStreamEvent, RawResponsesStreamEvent, ToolOutputText, ToolOutputImage
from agents.items import ToolCallItem, ToolCallOutputItem, MessageOutputItem
from agents.tracing import trace as agent_trace
from pydantic import Field

from siada.agent_hub.coder.sub_task_agent import SubTaskAgent, _build_default_tools
from siada.foundation.code_agent_context import CodeAgentContext
from siada.foundation.logging import logger as logging
from siada.foundation.setting import settings
from siada.services.agents import (
    UserAgentDefinition,
    filter_tools_for_agent,
    get_agent_definition,
    load_agents_for_cwd,
    load_preloaded_skills,
    open_agent_mcp_servers,
)
from siada.services.sub_agent_run_config import (
    adapt_fork_tools_for_effective_model,
    build_sub_agent_run_config,
)
from siada.tools.agent.subagent_async import register_background_subtask
from siada.tools.agent.subagent_guard import is_blocked_for_subagent, rejection_message_for
from siada.tools.agent.subagent_recursion import (
    MAX_NESTING_DEPTH,
    check_can_spawn,
    register_alive,
    release_alive,
)
from siada.tools.agent import subagent_persistence
from siada.tools.agent.sub_agent_compaction_filter import (
    InMemorySession,
    make_sub_agent_compaction_filter,
    make_sub_agent_session_input_callback,
)
from siada.tools.agent.sub_agent_notifier import (
    finish_sub_agent,
    push_sub_agent_message,
    start_sub_agent,
)
from siada.tools.tool_call_format.formatter_factory import ToolCallFormatterFactory
from siada.tools.coder.apply_patch_presentation import (
    is_apply_patch_call,
    is_apply_patch_output,
    render_apply_patch_call_summary,
    render_apply_patch_display,
)


RUN_SUBTASK_DOCS = """\
Launch a sub-agent with a clean context window to execute a specific, bounded task.

Proactively reach for this tool when a piece of work has a clear, self-contained
boundary, would otherwise pollute your own context with a large amount of
unrelated intermediate exploration, or can be carried out independently in
parallel with other work — don't wait for the user to explicitly ask for a
sub-agent.

Args:
    instruction: The complete input for the sub-agent. The caller is responsible
        for assembling all necessary context (e.g. design document path, previous
        step result, task directive) into this single string.
    agent: Name of a user-defined agent to run the task with, when the system
        prompt lists one whose description matches the task (see the AGENT TYPES
        section). The named agent supplies its own system prompt, tools, skills,
        MCP servers and effort level. Omit it to use the general-purpose
        sub-agent.
    fork: Whether the sub-agent should inherit your current context (your tools,
        your system prompt, and your full conversation history so far) instead of
        starting with a clean slate. Set this to True when you will still need the
        sub-agent's intermediate reasoning / context later, or when its work is a
        continuation of what you're doing rather than an isolated side-task.
        Defaults to False. Ignored when `agent` names a user-defined agent, which
        always brings its own configuration.
    async: Whether to run the sub-agent in the background instead of waiting for
        it to finish. Set this to True when you do NOT need the result immediately
        and can keep making progress on other parts of the task while it runs;
        you will be notified with its summary once it completes. Defaults to False
        (wait for the result before continuing).

Returns:
    When async is False: a plain-text summary of what was done, which files were
    modified, and key decisions made.
    When async is True: a short acknowledgement that the sub-agent was started in
    the background; the actual summary arrives later as an injected notification.
"""


# ---- User-defined agents (`.agents/agents/*.md`) -------------------------


def _resolve_workspace(agent_context: Optional[CodeAgentContext]) -> Path:
    """Workspace directory a user-agent definition is resolved against."""
    root_dir = getattr(agent_context, "root_dir", None)
    return Path(root_dir) if root_dir else Path.cwd()


def resolve_user_agent_definition(
    agent_name: str,
    agent_context: Optional[CodeAgentContext],
) -> Optional[UserAgentDefinition]:
    """Look up a user-defined agent by name in the workspace's agent roots."""
    return get_agent_definition(_resolve_workspace(agent_context), agent_name)


def unknown_agent_message(agent_name: str, agent_context: Optional[CodeAgentContext]) -> str:
    """Model-facing error text for an agent name that resolves to nothing."""
    outcome = load_agents_for_cwd(_resolve_workspace(agent_context))
    if outcome.agents:
        available = ", ".join(f"`{a.name}`" for a in outcome.agents)
        return (
            f"Unknown agent '{agent_name}'. Available agents: {available}. "
            "Re-issue the call with one of those names, or omit `agent` to use "
            "the general-purpose sub-agent."
        )
    return (
        f"Unknown agent '{agent_name}': no user-defined agents were found. "
        "Agents are defined as Markdown files with YAML frontmatter under "
        "`<project>/.agents/agents/`, `<project>/.siada-cli/agents/`, or "
        "`~/.siada-cli/agents/`. Omit `agent` to use the general-purpose "
        "sub-agent."
    )


# ---- Helper functions --------------------------------


def _tool_output_to_text(output) -> str:
    """Mirror stream_utils.render_tool_call_output's type dispatch, returning text.

    Used to push tool outputs to the sub-agent detail view (via ACP) without
    rendering them to the main message flow.
    """
    if hasattr(output, "format_for_display"):
        return output.format_for_display()
    if isinstance(output, list):
        parts = []
        for item in output:
            if isinstance(item, ToolOutputText):
                parts.append(item.text)
            elif isinstance(item, ToolOutputImage):
                parts.append("✓ Image loaded successfully")
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if isinstance(output, ToolOutputImage):
        return "✓ Image loaded successfully"
    if isinstance(output, ToolOutputText):
        return output.text
    return str(output) if output is not None else ""


def _clone_context_for_subagent(
    agent_context: CodeAgentContext,
    *,
    depth: int = 1,
    self_id: Optional[str] = None,
) -> CodeAgentContext:
    """Build the sub-agent's own CodeAgentContext, marked ``is_subagent=True``.

    Kept minimal (root_dir only) to match the pre-existing non-fork behaviour;
    the ``is_subagent`` flag is what the recursion guard
    (``subagent_guard.is_blocked_for_subagent``) checks at tool-invocation
    time, regardless of fork mode.

    ``depth`` / ``allow_recursive_subagents`` / ``root_session_id`` are
    propagated so a depth-1 sub-agent context (when recursion is enabled)
    carries what it needs to itself call ``run_subtask`` one more level
    (depth check + concurrency tracking + persistence path). When recursion
    is disabled (default), ``allow_recursive_subagents`` is False and these
    extra fields are inert — behaviour is identical to before.

    ``session`` is only propagated when recursion is enabled: a depth-1
    sub-agent that itself calls ``run_subtask`` needs a live ``session`` on
    its own context, because ``build_sub_agent_run_config`` (called for the
    depth-2 spawn) hard-requires ``context.session`` to source the LLM
    config. Gating this on ``allow_recursive_subagents`` keeps the default
    (off) path's cloned context exactly as before (``session=None``).
    """
    return CodeAgentContext(
        root_dir=agent_context.root_dir,
        is_subagent=True,
        subagent_depth=depth,
        root_session_id=agent_context.root_session_id,
        allow_recursive_subagents=agent_context.allow_recursive_subagents,
        subagent_self_id=self_id,
        session=agent_context.session if agent_context.allow_recursive_subagents else None,
    )


async def _build_fork_materials(run_ctx: RunContextWrapper[CodeAgentContext]):
    """Assemble the three fork-alignment materials from the parent's run context.

    Returns a ``(tools, instructions, history)`` tuple:

    - ``tools``: the parent agent's current tool list (``run_ctx.agent.tools``),
      used verbatim so the tool-schema prefix layer is byte-identical.
    - ``instructions``: the parent's system prompt for this turn, recomputed via
      ``agent.get_system_prompt(run_ctx)`` (same context -> same rendered text).
    - ``history``: the parent's real (post-compaction) API message history —
      i.e. exactly what was actually sent to the model — read via
      ``context.task_message_state.get_real_messages()``. This (not the raw
      session log) is what determines the model-facing prefix.

    Falls back to ``(None, None, [])`` per-field when the parent agent isn't
    reachable (e.g. ``run_ctx`` is a bare ``RunContextWrapper`` in tests) so
    callers can still fall through to non-fork behaviour.
    """
    parent_agent = getattr(run_ctx, "agent", None)
    tools = list(parent_agent.tools) if parent_agent is not None else None
    instructions: Optional[str] = None
    if parent_agent is not None:
        try:
            instructions = await parent_agent.get_system_prompt(run_ctx)
        except Exception as e:
            logging.warning(f"[run_subtask][fork] failed to get parent system prompt: {e}")

    history = []
    agent_context = run_ctx.context
    if agent_context is not None and agent_context.session is not None:
        try:
            history = list(agent_context.task_message_state.get_real_messages())
        except Exception as e:
            logging.warning(f"[run_subtask][fork] failed to read parent real messages: {e}")

    return tools, instructions, history


# ---- Implementation function --------------------------------

async def run_subtask_impl(
    instruction: str,
    agent_context: Optional[CodeAgentContext] = None,
    run_config: Optional[RunConfig] = None,
    *,
    fork: bool = False,
    run_ctx: Optional[RunContextWrapper[CodeAgentContext]] = None,
    child_depth: int = 1,
    agent_definition: Optional[UserAgentDefinition] = None,
):
    """
    Internal implementation of run_subtask, intended to be called directly in tests.

    Args:
        instruction: The complete input for the sub-agent.
        agent_context: CodeAgentContext used for root_dir and the sub-agent
            display-state push. When None, a minimal context with the current
            working directory is created.
        run_config: RunConfig to use. When None, one is built from the session
            config (requires an active agent session).
        fork: When True, aligns the sub-agent's tools / system prompt / seeded
            history with the parent agent's current turn (see
            ``_build_fork_materials``) so the model provider's prompt cache can
            be reused. Requires ``run_ctx`` (the parent's live
            ``RunContextWrapper``/``ToolContext``) to actually source those
            materials; falls back to non-fork behaviour with a warning if
            ``run_ctx`` is not supplied or the parent agent isn't reachable
            through it.
        run_ctx: The parent's ``RunContextWrapper`` (or ``ToolContext``) for
            this call. Only consulted when ``fork=True``.
        child_depth: The nesting depth the SPAWNED sub-agent will run at (1
            for a normal main-agent-launched sub-agent, 2 for a sub-sub-agent
            launched by a sub-agent under ``allow_recursive_subagents``).
            Only meaningful when recursion is enabled; otherwise always 1.
        agent_definition: A user-defined agent (``.agents/agents/*.md``) whose
            configuration drives this run: its body becomes the system prompt,
            its ``tools`` / ``skills`` / ``mcpServers`` / ``effort`` / ``model``
            are applied. When set, ``fork`` is ignored (a definition always
            brings its own tools and prompt, so the parent's cache-aligned
            prefix cannot be reused).

    Returns:
        Plain-text summary produced by the SubTaskAgent.
    """
    if agent_definition is not None and fork:
        logging.warning(
            "[run_subtask] fork=True is ignored for user-defined agent '%s' "
            "(the definition supplies its own tools and prompt).",
            agent_definition.name,
        )
        fork = False

    if run_config is None:
        run_config = build_sub_agent_run_config(
            agent_context,
            effort=agent_definition.effort if agent_definition is not None else None,
            model=agent_definition.model if agent_definition is not None else None,
        )

    # Create an in-memory session for this sub-agent run. It accumulates history
    # across turns (replacing the default no-session / RunState-only path) and
    # serves as the write-back target for the compaction callback below.
    in_memory_session = InMemorySession()

    # Attach the two cooperating compaction hooks whenever the parent context
    # has a live session (i.e. model_run_config is accessible). In tests that
    # supply run_config directly without a session, both hooks are skipped.
    #   - session_input_callback: seeds this run's new input into the session so
    #     the filter's session.get_items() does not lose it.
    #   - call_model_input_filter: performs the actual per-model-call compaction,
    #     reading from (and writing back to) the session.
    if agent_context and agent_context.session:
        run_config.session_input_callback = make_sub_agent_session_input_callback(
            in_memory_session
        )
        run_config.call_model_input_filter = make_sub_agent_compaction_filter(
            agent_context.model_run_config, in_memory_session
        )

    logging.info(
        f"[run_subtask] Launching sub-agent (fork={fork}): {instruction[:80]}..."
    )

    # Inherit the parent agent's resolved web-tools switch so the sub-agent
    # respects the same provider-based default / manual toggle as the parent.
    # Prefer the resolved provider name written per-run by _build_run_config
    # (agent_context.provider) — the actual provider used for model calls — and
    # fall back to the raw llm_config value with model-based routing applied.
    from siada.tools.web import resolve_web_tools_enabled, resolve_provider_from_context
    sub_web_enabled = resolve_web_tools_enabled(
        resolve_provider_from_context(agent_context),
        getattr(agent_context, "web_tools_enabled", None),
    )
    model_name = None
    try:
        model_name = agent_context.model_run_config.model_name
    except (AttributeError, TypeError):
        pass

    # The sub-agent may run on a different model than the parent (see
    # ``resolve_sub_agent_llm_config``).  Tool-protocol decisions must follow
    # the *effective* sub-agent model: the non-fork default tool set is built
    # for the model that will actually serve this run, and inherited fork
    # tools must not carry the native Responses apply_patch tool onto a
    # chat-completions model (its tool conversion rejects hosted tools).
    sub_model_name = getattr(run_config, "model", None)
    if not isinstance(sub_model_name, str) or not sub_model_name:
        sub_model_name = model_name

    # ---- Fork alignment: tools / instructions / seeded history ----
    #
    # Only attempted when the caller actually asked for fork AND handed us
    # the parent's live run_ctx (the source of its current tool list +
    # renderable system prompt). Any failure — or fork=False — falls straight
    # through to the pre-existing non-fork path (fork_tools/instructions stay
    # None, seeded_history stays empty), so this is purely additive.
    fork_tools = None
    fork_instructions = None
    seeded_history: list = []
    if fork and run_ctx is not None:
        fork_tools, fork_instructions, seeded_history = await _build_fork_materials(run_ctx)
        if fork_tools is None:
            logging.warning(
                "[run_subtask][fork] parent agent not reachable via run_ctx; "
                "falling back to non-fork tool set/prompt for this run."
            )
        else:
            fork_tools = adapt_fork_tools_for_effective_model(fork_tools, sub_model_name)
            logging.info(
                "[run_subtask][fork] aligned tools=%d instructions_len=%d history_items=%d",
                len(fork_tools), len(fork_instructions or ""), len(seeded_history),
            )
    elif fork and run_ctx is None:
        logging.warning(
            "[run_subtask][fork] fork=True but no run_ctx supplied; "
            "falling back to non-fork tool set/prompt for this run."
        )

    if seeded_history:
        # Seed the fork's own in-memory session with the parent's real
        # (post-compaction) message history BEFORE the run starts, so the
        # first model call's history-layer prefix matches the parent's.
        # add_items dedups by content fingerprint, which is a no-op here
        # since the session starts empty.
        await in_memory_session.add_items(seeded_history)

    sa_item = start_sub_agent(agent_context, instruction)

    # ---- Recursive-mode extras: nesting depth for the spawned agent's own
    # tool set, and on-disk persistence (both are pure additions, gated on
    # allow_recursive_subagents so the non-recursive path is untouched). ----
    recursive_enabled = bool(agent_context and agent_context.allow_recursive_subagents)
    include_run_subtask = recursive_enabled and child_depth < MAX_NESTING_DEPTH

    # ---- User-defined agent (`.agents/agents/*.md`) ----
    #
    # A definition replaces the generic sub-agent surface: its body becomes the
    # system prompt, its `tools` restrict the default tool set, its `skills` are
    # preloaded into the prompt, and its `mcpServers` are connected for the run
    # (see the `async with` below). `effort` and `model` were already applied
    # when the RunConfig was built. Everything here is a no-op without a
    # definition.
    definition_tools = None
    preloaded_skills: list = []
    if agent_definition is not None:
        preloaded_skills = load_preloaded_skills(
            agent_definition, _resolve_workspace(agent_context)
        )
        definition_tools = filter_tools_for_agent(
            _build_default_tools(
                web_tools_enabled=sub_web_enabled,
                include_run_subtask=include_run_subtask,
                model_name=sub_model_name or model_name,
            ),
            agent_definition,
        )
        logging.info(
            "[run_subtask] agent='%s' tools=%d preloaded_skills=%d mcp_servers=%d",
            agent_definition.name,
            len(definition_tools),
            len(preloaded_skills),
            len(agent_definition.mcp_servers),
        )

    persist = (
        recursive_enabled
        and agent_context is not None
        and agent_context.root_dir
        and agent_context.root_session_id
    )
    if persist:
        subagent_persistence.record_start(
            agent_context.root_dir,
            agent_context.root_session_id,
            agent_id=sa_item.id,
            parent_id=agent_context.subagent_self_id,
            depth=child_depth,
            title=sa_item.title,
            instruction=instruction,
        )

    # Wrap execution in a dedicated trace so sub-agent spans are recorded under
    # a "SubTaskAgent" trace (distinct from the parent agent's "Agent workflow"
    # trace). Without this, Runner.run_streamed detects get_current_trace() is
    # already set and reuses the parent trace — making log routing impossible.
    with agent_trace(
        workflow_name="SubTaskAgent",
        disabled=run_config.tracing_disabled,
    ):
        try:
            # Connect the definition's MCP servers for the duration of this run:
            # servers the global MCP manager already connected are reused as-is,
            # servers only configured (or defined inline) in the definition are
            # created, connected here, and cleaned up on the way out. The stack
            # stays empty — and both calls are no-ops — without a definition.
            mcp_stack = AsyncExitStack()
            definition_mcp_servers = (
                await mcp_stack.enter_async_context(
                    open_agent_mcp_servers(agent_definition)
                )
                if agent_definition is not None
                else []
            )

            result = Runner.run_streamed(
                starting_agent=SubTaskAgent(
                    web_tools_enabled=sub_web_enabled,
                    fork_tools=fork_tools,
                    fork_instructions=fork_instructions,
                    include_run_subtask=include_run_subtask,
                    model_name=sub_model_name or model_name,
                    definition_prompt=(
                        agent_definition.prompt if agent_definition is not None else None
                    ),
                    preloaded_skills=preloaded_skills,
                    mcp_servers=definition_mcp_servers,
                    tools_override=definition_tools,
                ),
                input=instruction,
                context=_clone_context_for_subagent(
                    agent_context, depth=child_depth, self_id=sa_item.id
                ),
                run_config=run_config,
                max_turns=settings.MAX_TURNS,
                session=in_memory_session,
            )

            native_patch_calls: dict[str, object] = {}
            async for event in result.stream_events():
                if not isinstance(event, RunItemStreamEvent):
                    continue

                item = event.item

                # Sub-agent activity is pushed only to the sub-agent detail
                # view via ACP; it is not rendered in the main message flow.
                if isinstance(item, ToolCallItem):
                    raw = item.raw_item
                    call_id = getattr(raw, "call_id", "")
                    if is_apply_patch_call(raw):
                        tool_name = "apply_patch"
                        native_patch_calls[call_id] = raw
                        content = render_apply_patch_call_summary(raw)
                    else:
                        tool_name = getattr(raw, "name", str(raw))
                        arguments = getattr(raw, "arguments", "") or ""
                        formatter = ToolCallFormatterFactory.get_formatter(tool_name)
                        content, _ = formatter.format_input(call_id, tool_name, arguments)
                    push_sub_agent_message(sa_item.id, "tool_call", content, tool_name=tool_name)
                    if persist:
                        subagent_persistence.append_log(
                            agent_context.root_dir, agent_context.root_session_id,
                            sa_item.id, "tool_call", content, tool_name=tool_name,
                        )

                elif isinstance(item, ToolCallOutputItem):
                    raw_output = getattr(item, "raw_item", None)
                    if is_apply_patch_output(raw_output):
                        call_id = (
                            raw_output.get("call_id", "")
                            if isinstance(raw_output, dict)
                            else getattr(raw_output, "call_id", "")
                        )
                        output_text = render_apply_patch_display(
                            custom_data=getattr(item, "custom_data", None),
                            raw_call=native_patch_calls.get(call_id),
                            output=item.output,
                        )
                    else:
                        output_text = _tool_output_to_text(item.output)
                    push_sub_agent_message(sa_item.id, "tool_output", output_text)
                    if persist:
                        subagent_persistence.append_log(
                            agent_context.root_dir, agent_context.root_session_id,
                            sa_item.id, "tool_output", output_text,
                        )

                elif isinstance(item, MessageOutputItem):
                    text_parts = [
                        part.text
                        for part in getattr(item.raw_item, "content", [])
                        if getattr(part, "type", None) == "output_text" and hasattr(part, "text")
                    ]
                    if text_parts:
                        thinking_text = "".join(text_parts)
                        push_sub_agent_message(sa_item.id, "thinking", thinking_text)
                        if persist:
                            subagent_persistence.append_log(
                                agent_context.root_dir, agent_context.root_session_id,
                                sa_item.id, "thinking", thinking_text,
                            )
        except Exception as e:
            finish_sub_agent(agent_context, sa_item.id, "failed", str(e))
            if persist:
                subagent_persistence.record_finish(
                    agent_context.root_dir, agent_context.root_session_id,
                    sa_item.id, "failed", str(e),
                )
            raise
        finally:
            # Closes the definition's MCP servers (no-op when the stack is
            # empty). Runs on success, failure, and cancellation alike.
            await mcp_stack.aclose()

    # Final end-of-run snapshot: capture the full session context after the
    # sub-agent has finished streaming (i.e. after the last turn and any last
    # compaction have been written back to the session). This complements the
    # per-turn dump points (session-input-callback / filter-entry /
    # before-compaction / after-compaction) with a single authoritative
    # end-state. Like every dump point it is a no-op unless dump mode is enabled
    # and never raises into the caller.
    await in_memory_session.dump_items("subtask-finished")

    summary: str = result.final_output
    if not isinstance(summary, str):
        summary = str(summary)
    push_sub_agent_message(sa_item.id, "message", summary)
    finish_sub_agent(agent_context, sa_item.id, "completed", summary)
    if persist:
        subagent_persistence.record_finish(
            agent_context.root_dir, agent_context.root_session_id,
            sa_item.id, "completed", summary,
        )
    logging.info(
        f"[run_subtask] Sub-agent finished — summary: {summary[:120]}"
    )
    return summary



# ---- Public tool function --------------------------------

@function_tool(name_override="run_subtask", description_override=RUN_SUBTASK_DOCS)
async def run_subtask(
    run_ctx: RunContextWrapper[CodeAgentContext],
    instruction: str,
    agent: Optional[str] = None,
    fork: bool = False,
    async_mode: bool = Field(default=False, alias="async"),
):
    agent_context = run_ctx.context

    # Master switch (conf.yaml `sub_agent.enabled`, default true): when the
    # feature is disabled the tool is already absent from the main agent's
    # tool list, but a call can still reach the tool object through an
    # inherited (fork) tool list built before the switch was turned off.
    if agent_context is not None and not getattr(agent_context, "subagent_enabled", True):
        logging.info("[run_subtask] Rejected: sub-agent feature disabled by conf.yaml")
        return (
            "The `run_subtask` tool is disabled by configuration "
            "(`sub_agent.enabled: false` in conf.yaml). "
            "Continue the task yourself using your other tools."
        )

    # Recursion guard: this tool is present in a fork sub-agent's schema
    # (needed for tool-list byte alignment), but must not actually execute
    # while running inside a sub-agent. Non-fork sub-agents never see this
    # tool at all (excluded from SubTaskAgent._build_default_tools), so this
    # branch is only reachable from a fork sub-agent.
    if is_blocked_for_subagent("run_subtask", agent_context):
        return rejection_message_for("run_subtask")

    # ---- User-defined agent resolution ----
    #
    # `agent` names a definition from `.agents/agents/*.md` (or one of the
    # compatibility roots). An unresolvable name is reported back to the model
    # as text — with the list of names that do exist — instead of raising, so
    # the parent agent can correct itself within the same turn.
    agent_definition: Optional[UserAgentDefinition] = None
    if agent:
        agent_definition = resolve_user_agent_definition(agent, agent_context)
        if agent_definition is None:
            logging.info(f"[run_subtask] Unknown agent '{agent}' requested")
            return unknown_agent_message(agent, agent_context)

    # ---- Recursive-mode extras: nesting-depth + concurrency cap ----
    #
    # Only consulted when sub_agent.allow_recursive_subagents is on
    # (agent_context.allow_recursive_subagents). When it's off, child_depth
    # stays at the pre-existing hardcoded value of 1 (meaningless — the
    # field is inert unless recursion is enabled) and no concurrency
    # bookkeeping happens at all, so this branch is a pure addition with zero
    # effect on the default path.
    recursive_enabled = bool(agent_context and agent_context.allow_recursive_subagents)
    child_depth = 1
    if recursive_enabled:
        parent_depth = getattr(agent_context, "subagent_depth", 0)
        decision = check_can_spawn(parent_depth, agent_context.root_session_id)
        if not decision.allowed:
            logging.info(f"[run_subtask][recursive] spawn rejected: {decision.reason}")
            return decision.reason
        child_depth = decision.child_depth
        # Reserve the slot immediately (before the run actually starts) so
        # concurrent tool calls within the same LLM turn (the SDK supports
        # parallel tool calls) can't all pass the cap check before any of
        # them registers — released in the finally blocks below regardless
        # of how the run ends.
        register_alive(agent_context.root_session_id)

    # `background: true` in an agent definition means every spawn of that agent
    # runs in the background, regardless of what the caller passed.
    if agent_definition is not None and agent_definition.background:
        if not async_mode:
            logging.info(
                f"[run_subtask] agent '{agent_definition.name}' forces background execution"
            )
        async_mode = True

    if async_mode:
        async def _run_and_release():
            try:
                return await run_subtask_impl(
                    instruction=instruction,
                    agent_context=agent_context,
                    fork=fork,
                    run_ctx=run_ctx,
                    child_depth=child_depth,
                    agent_definition=agent_definition,
                )
            finally:
                if recursive_enabled:
                    release_alive(agent_context.root_session_id)

        task_id = register_background_subtask(agent_context, _run_and_release)
        return (
            f"Sub-agent started in the background (task_id={task_id}). "
            "You will be notified with its summary once it completes — "
            "continue with other work in the meantime."
        )

    try:
        return await run_subtask_impl(
            instruction=instruction,
            agent_context=agent_context,
            fork=fork,
            run_ctx=run_ctx,
            child_depth=child_depth,
            agent_definition=agent_definition,
        )
    finally:
        if recursive_enabled:
            release_alive(agent_context.root_session_id)
