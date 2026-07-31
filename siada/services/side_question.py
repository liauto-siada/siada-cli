"""/btw side question — lightweight read-only fork of the main agent.

Entry point: run_side_question(session, question) -> str

Design doc: design_docs/siada-btw-side-question-design.md
"""
from __future__ import annotations

import copy
import threading
from typing import TYPE_CHECKING

from siada.foundation.logging import logger

if TYPE_CHECKING:
    from siada.foundation.code_agent_context import CodeAgentContext

# Process-level monotonic counter for /btw session ids. Starts at 0 and keeps
# incrementing for the lifetime of the process. Guarded by a lock because each
# /btw runs in its own thread (see run_side_question).
_btw_seq_lock = threading.Lock()
_btw_seq = 0


def _next_btw_seq() -> int:
    """Return the next process-level /btw sequence number (0, 1, 2, ...)."""
    global _btw_seq
    with _btw_seq_lock:
        n = _btw_seq
        _btw_seq += 1
        return n


_BTW_REMINDER = """\
<system-reminder>This is a one-shot side question.

CONTEXT
- You are a transient agent spawned just to answer this question.
- The main agent is NOT interrupted; it continues independently.
- You share the conversation context, but do not refer to "what you were doing".

CONSTRAINTS
- You have NO tools available; do not attempt tool calls.
- This is a single response — there will be no follow-up turn.
- Use only what you can infer from the existing conversation context.
- Never say "let me check / let me look / I'll investigate" — there is no next turn.
</system-reminder>

"""


# ── btw tool deny guardrail ───────────────────────────────────────────────────
# Mirror Claude Code's `canUseTool: deny`: keep every tool's JSON schema in the
# request so the prompt-cache prefix (tools -> system -> messages) stays
# byte-identical to the main thread, but reject any tool the model tries to call
# BEFORE it executes (zero side effects).  Overriding `tool_choice` or dropping
# tools would mutate the Anthropic cache key and bust the cache — that was the
# original root cause of /btw never hitting the cache.
_BTW_TOOL_DENY_MESSAGE = (
    "Side questions cannot use tools. Answer directly from the existing "
    "conversation context in a single response."
)


def _wrap_tools_with_deny(tools: list) -> list:
    """Return a NEW tool list where every FunctionTool carries a deny guardrail.

    The original list and its tool objects are NEVER mutated — the cached main
    agent shares them, so mutating would corrupt the main conversation's tools.
    Non-FunctionTool entries pass through unchanged.
    """
    import dataclasses

    from agents.tool import FunctionTool
    from agents.tool_guardrails import (
        ToolGuardrailFunctionOutput,
        ToolInputGuardrail,
        ToolInputGuardrailData,
    )

    def _reject(data: "ToolInputGuardrailData") -> "ToolGuardrailFunctionOutput":
        # reject_content: don't run the tool, hand a message back to the model.
        return ToolGuardrailFunctionOutput.reject_content(message=_BTW_TOOL_DENY_MESSAGE)

    deny = ToolInputGuardrail(guardrail_function=_reject, name="btw_deny_tools")

    wrapped = []
    for t in tools:
        if isinstance(t, FunctionTool):
            existing = list(t.tool_input_guardrails or [])
            wrapped.append(
                dataclasses.replace(t, tool_input_guardrails=existing + [deny])
            )
        else:
            # Non-FunctionTool entries (rare) pass through unchanged.
            wrapped.append(t)
    return wrapped



class _BtwReadonlySession:
    """
    主 session 的只读替身，仅暴露 siada_config 供 system_prompt 和 build_sub_agent_run_config 读取。

    故意不暴露：state、task_message_state、checkpoint_tracker、openai_session。
    任何下游代码若尝试访问这些字段都会立即 AttributeError，而非静默损坏主 session。
    """

    def __init__(self, real_session):
        self.siada_config = real_session.siada_config
        # Append a process-level, ever-incrementing suffix (0, 1, 2, ...) so each
        # /btw fork gets a unique session id within the process.
        self.session_id = f"{real_session.session_id}-btw-{_next_btw_seq()}"



# Mirrors TurnPruneSummaryCompaction.token_threshold_ratio: the fraction of the
# context window above which the snapshot is considered "large". Used only for
# observability here — we log when exceeded but still keep the history intact.
_BTW_TOKEN_THRESHOLD_RATIO: float = 0.9


def _strip_in_progress_assistant(items: list) -> list:
    """Strip a trailing *in-progress* assistant message to avoid API 400.

    /btw can run CONCURRENTLY while the main agent is mid-turn, so the snapshot
    (especially the get_messages() fallback) may end with an assistant message
    the main thread is still streaming. Feeding an ``in_progress`` item back as
    input is rejected by the Responses API (400), so we drop it.

    We strip ONLY ``status == "in_progress"``. Terminal statuses (``"completed"``
    / ``"incomplete"``) are valid to send back. Crucially we do NOT strip when
    ``status`` is missing/None: a completed final assistant answer is often
    serialized without a status, and dropping it would needlessly discard the
    most recent (and most relevant) context for the side question.
    """
    if not items:
        return items
    last = items[-1]
    if (
        isinstance(last, dict)
        and last.get("role") == "assistant"
        and last.get("status") == "in_progress"
    ):
        return items[:-1]
    return items



def _btw_boundary_indices(items: list) -> list:
    """Indices safe to start a kept suffix at (won't split a tool call/result).

    The ONLY safe cut points are user messages. Each user message starts a fresh
    turn, so the suffix beginning at one contains only complete turns: every
    function_call inside it has its matching function_call_output later in the
    same turn, and vice versa — no orphan tool call/result.

    We deliberately do NOT treat "right after a function_call_output" as a
    boundary. With PARALLEL tool calls a single turn emits several
    function_call_output items in a row; cutting between them would leave the
    later outputs without their preceding function_call (which sits before the
    cut) → orphan tool_result → API 400. (The main compaction path can use that
    boundary only because it summarizes the dropped portion AND repairs orphans
    afterward; here we drop outright and never repair, so we must avoid it.)

    Detection uses CompactionStrategy.is_user_message, which delegates to the
    agents SDK ``Converter.maybe_*`` helpers — the same authoritative item parse
    the main compaction path uses (handles dict and typed-object items alike).
    """
    from siada.agent_hub.context_filter.compaction_strategy import CompactionStrategy

    return [i for i, m in enumerate(items) if CompactionStrategy.is_user_message(m)]




def _keep_recent_within_budget(items: list, model_name: str, budget: int) -> list:
    """Keep the most recent messages whose token count fits within *budget*.

    Trims from the front, snapping the cut to a safe boundary (a user message,
    i.e. a turn start) so a tool call is never separated from its output (see
    _btw_boundary_indices). Picks the smallest boundary whose suffix still fits
    the budget — i.e. retains as much recent context as possible.
    """

    from siada.agent_hub.context_filter.utils import calculate_tokens

    boundaries = _btw_boundary_indices(items)
    if not boundaries:
        return items

    for b in boundaries:
        if calculate_tokens(model_name, items[b:]) <= budget:
            return items[b:]

    # Even the most-recent boundary suffix exceeds the budget — keep that
    # minimal suffix anyway (cannot trim further without splitting a turn).
    return items[boundaries[-1]:]


def _prepare_btw_snapshot(items: list, context: "CodeAgentContext") -> list:
    """
    Prepare the main-agent message snapshot for the btw one-shot fork.

    Steps:
      1. Strip the trailing in-progress assistant message (avoid API 400).
      2. Token-count the snapshot and compare against
         _BTW_TOKEN_THRESHOLD_RATIO of the context window.
         - Below threshold: keep the history byte-identical to what the main
           thread last sent → maximizes the Anthropic prompt-cache hit rate.
         - At/above threshold: trim from the front to the most recent messages
           that fit the token budget (snapped to safe turn boundaries so tool
           call/result pairs stay intact). This loses some cache benefit but is
           required to keep the oversized snapshot within the context window.

    Pure, synchronous, zero LLM calls — safe to call from the btw thread.
    """
    from siada.agent_hub.context_filter.utils import calculate_tokens

    if not items:
        return items

    # Step 1 always runs (prevent API 400 regardless of size)
    items = _strip_in_progress_assistant(list(items))

    # Threshold comparison
    model_name = context.model_run_config.model_name
    context_window = context.model_run_config.context_window
    threshold = int(context_window * _BTW_TOKEN_THRESHOLD_RATIO)
    token_count = calculate_tokens(model_name, items)

    if token_count < threshold:
        logger.info(
            "[btw] snapshot within threshold (%d / %d tokens), keeping intact",
            token_count, threshold,
        )
        return items

    # Over threshold: keep only the most recent messages that fit the budget.
    trimmed = _keep_recent_within_budget(items, model_name, threshold)
    logger.warning(
        "[btw] snapshot exceeds threshold (%d >= %d tokens); trimmed to recent "
        "%d/%d messages (context_window=%d, ratio=%.1f)",
        token_count, threshold, len(trimmed), len(items),
        context_window, _BTW_TOKEN_THRESHOLD_RATIO,
    )
    return trimmed





def _btw_answer_from_failed_run(run_data) -> str:
    """Build a /btw answer from a run that ended in MaxTurnsExceeded.

    With max_turns=1, a model that tries to call a tool (instead of answering
    directly) cannot turn the deny-rejection into a text answer, so the run
    raises MaxTurnsExceeded. The partial output is carried on
    ``run_data.new_items``:

    - If the model also produced text in that turn, prefer returning that text.
    - Otherwise (tool call only — situation B), return a hint that names the
      tool the model attempted, asking the user to rephrase or use main chat.
    """
    from agents.items import ItemHelpers, ToolCallItem

    new_items = list(getattr(run_data, "new_items", None) or [])

    # Prefer any text the model emitted (covers the rare "text + tool_use" case).
    text = ItemHelpers.text_message_outputs(new_items).strip()
    if text:
        return text

    # Situation B: tool call only — name the tool the model tried to call.
    tool_name = None
    for item in new_items:
        if isinstance(item, ToolCallItem):
            tool_name = item.tool_name or tool_name

    label = tool_name or "a tool"
    return (
        f"(The model tried to call {label} instead of answering directly. "
        "Try rephrasing or ask in the main conversation.)"
    )


async def _run_async(
    snapshot_messages: list,

    stub_session: _BtwReadonlySession,
    workspace: str,
    agent_name: str,
    question: str,
) -> str:
    import time

    from agents import Runner, RunHooks
    from agents.exceptions import MaxTurnsExceeded, ModelBehaviorError

    from siada.agent_hub.hooks.siada_basic_agent_hooks import SiadaBasicAgentHooks
    from siada.foundation.code_agent_context import CodeAgentContext
    from siada.services.siada_runner import SiadaRunner
    from siada.services.sub_agent_run_config import build_sub_agent_run_config

    t0 = time.perf_counter()

    # 1. 取主 Agent 实例（命中 _agent_cache，已含 MCP tools）
    agent = await SiadaRunner.get_agent(agent_name)

    # 2. 取主 CodeAgentContext（命中 _context_cache，只读，复刻 system prompt 依赖字段）
    parent_ctx = await SiadaRunner.get_context(agent, stub_session, workspace)

    # 3. Build fork_ctx: copy read-only fields needed for system_prompt, block all
    #    side-effect channels (memory scheduler, holographic prefetch, etc.).
    #
    #    model_construct() is used instead of the normal constructor to bypass
    #    Pydantic type validation.  Two issues make the constructor unsuitable:
    #      1. CodeAgentContext.session is typed as Optional[RunningSession], but
    #         _BtwReadonlySession is a plain class (not a dataclass), so Pydantic
    #         rejects it with a dataclass_type validation error.
    #      2. When the running process predates a newly-added field (e.g.
    #         holographic_provider), passing it via the constructor raises
    #         ValidationError; model_construct silently ignores unknown fields.
    #    model_construct() calls default_factory for fields that are not supplied,
    #    so hook_pending_contexts / hook_pending_input_updates etc. are initialised
    #    correctly without being listed here explicitly.
    fork_ctx = CodeAgentContext.model_construct(
        root_dir=parent_ctx.root_dir,
        interactive_mode=getattr(parent_ctx, "interactive_mode", False),
        combined_memory=parent_ctx.combined_memory,
        preferred_language=getattr(parent_ctx, "preferred_language", None),
        pre_plan=getattr(parent_ctx, "pre_plan", False),
        siadaignore_controller=getattr(parent_ctx, "siadaignore_controller", None),
        holographic_provider=None,   # don't trigger prefetch / fact_count
        memory_store=None,           # don't trigger memory scheduler
        # max_turns=1: a /btw answer is a single, no-tool response. The deny
        # guardrail uses reject_content (it does NOT raise), so it never aborts
        # the run by itself. If the model still tries a tool, it cannot be
        # recovered into a text answer within a single turn and the run raises
        # MaxTurnsExceeded — we catch that below and salvage whatever the model
        # produced. The strong <system-reminder> keeps the normal case to one turn.
        max_turns=1,
        session=stub_session,        # read-only stub — no .state / .checkpoint_tracker
    )


    # 4. clone agent. Keep the SAME tool schemas as the main thread so the
    #    Anthropic prompt-cache prefix (tools -> system -> messages) is
    #    byte-identical, but attach a deny guardrail so any tool the model tries
    #    is rejected BEFORE execution (zero side effects). This mirrors Claude
    #    Code's `canUseTool: deny` — DO NOT clear tools or set tool_choice="none",
    #    both mutate the Anthropic cache key and bust the cache.
    #    不用 dataclasses.replace（见 siada_agent.py 注释，子类 __init__ 冲突）
    from agents import RunContextWrapper

    forked_agent = copy.copy(agent)
    forked_agent.name = "btw-fork"
    forked_agent.hooks = SiadaBasicAgentHooks()

    # Materialize the FULL tool list (MCP tools + local tools, in the SAME order
    # the main thread sends them — Agent.get_all_tools returns [*mcp_tools,
    # *local]) so the cache prefix is byte-identical and the prompt cache hits
    # even when MCP servers are configured.
    #
    # Calling get_all_tools from the btw thread's private loop is safe: siada
    # creates every MCP server with cache_tools_list=True and the main
    # conversation has already populated the cache, so MCPServer.list_tools
    # returns the cached _tools_list WITHOUT awaiting the main-loop-bound network
    # session (the cache-hit path in agents/mcp/server.py has no await / no lock).
    # On any failure (e.g. cold cache) fall back to local-only tools — rare,
    # accepts a partial cache miss for MCP users that turn, but never crashes.
    #
    # IMPORTANT: wraps ``parent_ctx`` (the cached, LIVE main CodeAgentContext
    # for this workspace — see SiadaRunner._context_cache / get_context above),
    # NOT ``fork_ctx``. get_all_tools uses the wrapped context for (a) each
    # FunctionTool.is_enabled(run_context, agent) check and (b) MCP tool
    # listing/filtering — both decide WHICH tools end up in the request.
    # fork_ctx is a stripped-down stub (several fields cleared/defaulted, e.g.
    # memory_store=None), so using it here could silently compute a different
    # enabled-tool set than the main thread just sent, busting the exact cache
    # prefix this fork exists to preserve.
    #
    # This does NOT mutate parent_ctx: RunContextWrapper only wraps it by
    # reference in its own brand-new dataclass instance (fresh usage/
    # _approvals/turn_input/tool_input fields, unrelated to the wrapper the
    # main turn's Runner.run created) — nothing here writes back onto
    # parent_ctx itself. The only get_all_tools side effects are (a) MCP
    # tool-list caching, which lives on the MCPServer object, not on context,
    # and (b) is_enabled checks, which for every tool in this codebase are
    # plain booleans that never read/write context. So this call is read-only
    # w.r.t. parent_ctx.
    try:
        all_tools = await agent.get_all_tools(RunContextWrapper(parent_ctx))
    except Exception as e:
        logger.warning(
            "[btw] get_all_tools failed (%r); falling back to local tools only "
            "(MCP users may miss cache this turn)", e,
        )
        all_tools = list(agent.tools)

    # MCP tools are now materialized into all_tools, so clear mcp_servers: the SDK
    # must NOT try to (re)connect them from this loop, and get_all_tools at run
    # time returns exactly our pre-built list ([] mcp + our tools).
    forked_agent.mcp_servers = []
    # Attach a deny guardrail to EVERY FunctionTool (local AND MCP — both are
    # FunctionTools after materialization). Keeps schemas byte-identical (cache
    # hit) AND hard-blocks execution of any tool, MCP included.
    # Build a fresh list — never mutate the cached main agent's shared tools.
    forked_agent.tools = _wrap_tools_with_deny(all_tools)


    # 5. 拼 fork input：裁剪后的历史前缀（prompt cache 关键）+ /btw user 消息
    prefix = _prepare_btw_snapshot(snapshot_messages, fork_ctx)
    fork_input = list(prefix) + [
        {"role": "user", "content": _BTW_REMINDER + question}
    ]

    # 6. RunConfig（build_sub_agent_run_config 不含 context_capture_filter）。
    #    NOTE: do NOT override tool_choice. Keeping model_settings byte-identical
    #    to the main thread (tool_choice stays "auto") preserves the Anthropic
    #    prompt-cache key. Tool execution is blocked by the per-tool deny
    #    guardrail attached in step 4, not by tool_choice. Overriding tool_choice
    #    here was the root cause of /btw cache misses.
    run_config = build_sub_agent_run_config(fork_ctx)


    # 7. RunHooks() for Runner.run (run-level); agent-level hooks already set
    #    on forked_agent.hooks above.
    run_hooks = RunHooks()

    try:
        result = await Runner.run(
            forked_agent,
            input=fork_input,
            context=fork_ctx,
            run_config=run_config,
            hooks=run_hooks,
            # max_turns=1 to match fork_ctx: a /btw answer is a single, no-tool
            # response. A tool attempt cannot be recovered within the budget and
            # raises MaxTurnsExceeded — handled just below (see fork_ctx comment).
            max_turns=1,
            session=None,   # ★ 不写 openai_session / FileSession
        )

        answer = (result.final_output or "").strip()
        if not answer:
            answer = "(model returned an empty response)"

    except MaxTurnsExceeded as e:
        # The deny guardrail never raises; reaching here means the model spent
        # its single turn trying to call a tool instead of answering. Salvage
        # whatever the model produced before the limit was hit (carried on
        # e.run_data.new_items): prefer any text it emitted, otherwise return a
        # hint naming the tool it tried to call.
        answer = _btw_answer_from_failed_run(getattr(e, "run_data", None))
    except ModelBehaviorError as e:
        answer = f"(model behavior error: {e})"

    except Exception as e:
        logger.warning("[btw] fork failed: %r", e)
        answer = f"(side question failed: {e})"

    elapsed = time.perf_counter() - t0
    logger.info(
        "[btw] done  q_len=%d  ans_len=%d  elapsed=%.2fs  prefix_msgs=%d",
        len(question), len(answer), elapsed, len(prefix),
    )
    return answer


def run_side_question(session, question: str) -> str:
    """
    同步入口，在独立 thread + event loop 中运行副 Agent，返回回答字符串。

    所有对主 session 可变字段的读取在主线程完成（快照），
    fork 线程不再访问主 session，避免并发竞态。
    """
    # 主线程快照（避免从 fork 线程访问主 session 的可变字段）
    llm_config   = session.siada_config.llm_config
    workspace    = session.siada_config.workspace
    agent_name   = session.siada_config.agent_name
    stub_session = _BtwReadonlySession(session)

    # _real_messages 优先（与上轮 LLM 调用 byte-for-byte 一致，最大化 cache 命中）
    # fallback 到 _message_history（更细粒度的 capture，即使还未完成一次完整 LLM 往返）
    snapshot = list(session.task_message_state.get_real_messages() or [])
    if not snapshot:
        snapshot = list(session.task_message_state.get_messages() or [])

    box: list = [None]
    err: list = [None]

    def _runner():
        import asyncio
        from siada.foundation.context import set_context_var, LLM_CONFIG, set_session_id

        loop = asyncio.new_event_loop()
        try:
            # contextvar 不跨线程继承，必须在 fork 线程重新 set
            set_context_var(LLM_CONFIG, llm_config)
            set_session_id(stub_session.session_id)

            box[0] = loop.run_until_complete(
                _run_async(snapshot, stub_session, workspace, agent_name, question)
            )
        except BaseException as e:
            err[0] = e
        finally:
            loop.close()

    t = threading.Thread(target=_runner, daemon=True, name="btw-runner")
    t.start()
    t.join(timeout=60)

    if t.is_alive():
        logger.warning("[btw] timed out after 60s, question=%r", question[:80])
        return "(side question timed out; the main agent is unaffected)"

    if err[0]:
        raise err[0]

    return box[0]
