"""Independent, isolated goal-verification LLM call — BTW-style cache-friendly fork.

Historically this ran a bespoke tool-call-aware transcript formatter into a
throwaway ``Agent(...)`` with no tools, no memory, and a separate fast model.
That was cheap per-token but discarded the main conversation's provider-side
prompt-cache prefix on every single verification call — the verifier request
looked nothing like the main turn's request, so caches (e.g. Anthropic
``cache_control``) never hit.

This module now mirrors the ``/btw`` side-question design (see
``siada/services/side_question.py`` and
``design_docs/siada-btw-side-question-design.md``): it reuses the SAME main
Agent instance, the SAME materialized tool list (local + MCP, same order),
and the RAW, unfiltered message history the main turn just used — appending
only a short verification request at the end. Keeping the outgoing
``tools -> system -> messages`` prefix identical to what the main turn sent
lets the provider's cache still hit on the verifier call instead of paying
full price every turn.

Isolation from the main conversation is preserved the same way ``/btw``
preserves it: every tool is DENIED via a ``ToolInputGuardrail``
(``reject_content``) rather than removed — removing tools/instructions would
change the cache key. No ``session=`` kwarg is passed to ``Runner.run``, so
nothing from this call is ever persisted back into the main session.

Judgment power stays 100% with this isolated call; the main agent has no
create_goal/update_goal tool and cannot self-declare completion.

NOTE on output_type: the forked agent below deliberately does NOT set
``output_type=GoalVerdict`` on the common path. A structured ``output_type``
folds a JSON schema / tool definition into the outgoing request, which
changes the request shape the provider's prompt cache keys off of — busting
the exact cache prefix this whole module exists to preserve. Instead,
``build_verifier_request_message`` (see prompts.py) asks the model to
answer with a plain JSON object in its final text response, and
``_parse_goal_verdict`` below parses that text back into a ``GoalVerdict``
after the run completes. Only if that parse fails do we fall back to
``_retry_with_structured_output``, which re-issues ONE more call with
``output_type=GoalVerdict`` set — sacrificing the cache prefix on that rare
retry only, never on the common path.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from agents import RunContextWrapper, RunHooks, Runner
from agents.exceptions import MaxTurnsExceeded, ModelBehaviorError
from agents.tool import FunctionTool
from agents.tool_guardrails import (
    ToolGuardrailFunctionOutput,
    ToolInputGuardrail,
    ToolInputGuardrailData,
)

from siada.foundation.logging import logger
from siada.foundation.tools.json_util import get_json_content
from siada.services.goal.models import GoalVerdict
from siada.services.goal.prompts import build_verifier_request_message

if TYPE_CHECKING:
    from siada.foundation.code_agent_context import CodeAgentContext
    from siada.services.file_session import FileSession
    from siada.services.goal.models import Goal


def elapsed_seconds_since(created_at: str) -> int:
    """Seconds between *created_at* (Goal.created_at, ISO-8601 'Z'-suffixed)
    and now. Falls back to 0 on any parse error rather than raising — this
    only feeds informational text in the verifier request.
    """
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return max(0, int((datetime.now(timezone.utc) - created).total_seconds()))
    except Exception:
        return 0


def tokens_used_for(context: "CodeAgentContext") -> int:
    """Best-effort total session token usage, mirroring the same
    ``session.state.usage.total_tokens`` read already used by the
    token-usage status line (ConversationTurn._build_context_usage_message)
    and ApiMessageTransferFilter._do_full_refresh.
    """
    try:
        usage = context.session.state.usage
        return getattr(usage, "total_tokens", 0) or 0
    except Exception:
        return 0


async def build_verifier_input(
    file_session: "FileSession", goal: "Goal", context: "CodeAgentContext"
) -> list:
    """Assemble the fork input: the full effective session history, verbatim,
    plus one verification request appended at the end.

    Uses ``FileSession.get_effective_messages()``, which splices the
    compacted ``api_messages.json`` snapshot with the ``api_history.json``
    delta tail — exactly the view the main model itself last saw (plus the
    turn that just completed). By the time this runs (after
    ``turn.execute()`` has returned), the current turn's assistant response
    is already durable in ``api_history.json`` — session persistence happens
    synchronously inside ``Runner.run_streamed()`` before control returns to
    the caller — so the effective view already includes it.

    Deliberately does NOT reformat, filter, or truncate any message (no more
    ``format_transcript_for_verifier``): the verifier needs to see exactly
    what the main model saw — including tool calls/outputs and reasoning —
    to judge completion, and reusing the raw items keeps this request
    as close as possible to the main thread's last call up to the appended
    verification message (the Goal state line — tokens/time — necessarily
    varies call to call, so this request is no longer byte-identical the
    way the old <system-reminder>-only version was).
    """
    items = await file_session.get_effective_messages()
    message = build_verifier_request_message(
        goal.objective,
        status=goal.status,
        elapsed_seconds=elapsed_seconds_since(goal.created_at),
    )
    return list(items) + [{"role": "user", "content": message}]


# ── verifier tool deny guardrail ────────────────────────────────────────────
# Same technique as side_question._wrap_tools_with_deny: keep every tool's
# JSON schema in the request so the prompt-cache prefix (tools -> system ->
# messages) stays byte-identical to the main thread, but reject any tool the
# model tries to call BEFORE it executes (zero side effects). Removing tools
# or forcing tool_choice="none" would mutate the cache key and bust the
# cache — that was the original problem with the old implementation (which
# went further and used a completely different system prompt too).
_VERIFIER_TOOL_DENY_MESSAGE = (
    "Goal verification is read-only and cannot call tools. Answer directly "
    "from the existing conversation context with your structured verdict."
)


def _wrap_tools_with_deny(tools: list) -> list:
    """Return a NEW tool list where every FunctionTool carries a deny guardrail.

    The original list and its tool objects are NEVER mutated — the cached
    main agent shares them, so mutating would corrupt the main conversation's
    tools. Non-FunctionTool entries pass through unchanged.
    """

    def _reject(data: ToolInputGuardrailData) -> ToolGuardrailFunctionOutput:
        return ToolGuardrailFunctionOutput.reject_content(
            message=_VERIFIER_TOOL_DENY_MESSAGE
        )

    deny = ToolInputGuardrail(guardrail_function=_reject, name="goal_verifier_deny_tools")

    wrapped = []
    for t in tools:
        if isinstance(t, FunctionTool):
            existing = list(t.tool_input_guardrails or [])
            wrapped.append(
                dataclasses.replace(t, tool_input_guardrails=existing + [deny])
            )
        else:
            wrapped.append(t)
    return wrapped


# Process-level monotonic counter so each verifier fork gets a unique session
# id suffix within the process, mirroring side_question._next_btw_seq.
_verifier_seq_lock = threading.Lock()
_verifier_seq = 0


def _next_verifier_seq() -> int:
    global _verifier_seq
    with _verifier_seq_lock:
        n = _verifier_seq
        _verifier_seq += 1
        return n


def _parse_goal_verdict(raw_text: str) -> GoalVerdict:
    """Parse the verifier's raw text reply into a ``GoalVerdict``.

    The forked agent deliberately does NOT set ``output_type=GoalVerdict``
    on the common path (see the module docstring above and the comment at
    the ``forked_agent = copy.copy(agent)`` site below): a structured
    ``output_type`` folds a JSON schema / tool definition into the outgoing
    request, which changes the request shape the provider's prompt cache
    keys off of — busting the exact cache prefix this whole module exists
    to preserve. Instead, ``build_verifier_request_message`` asks the model
    to answer with a plain JSON object as its final text response, and this
    function turns that text back into the same ``GoalVerdict`` shape the
    rest of the codebase (Controller, tests) already expects.
 
    Tries, in order:
      1. ``json.loads`` directly on the stripped text — the common case,
         since the model was asked to return only the JSON object.
      2. ``get_json_content`` (siada/foundation/tools/json_util.py), which
         additionally strips a ```json ... ``` / ``` ... ``` fence the
         model may have wrapped the object in.
      3. A best-effort extraction of the first ``{`` .. last ``}`` span, for
         a model that added stray prose before/after the JSON object.

    Raises ``ValueError`` if no valid JSON object can be recovered — the
    caller falls back to ``_retry_with_structured_output`` rather than
    letting it propagate.
    """
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("empty verifier response")

    parsed = None
    for attempt in (
        lambda: json.loads(text),
        lambda: get_json_content(text),
        lambda: json.loads(text[text.index("{"): text.rindex("}") + 1]),
    ):
        try:
            candidate = attempt()
        except Exception:
            continue
        if isinstance(candidate, dict):
            parsed = candidate
            break

    if parsed is None:
        raise ValueError(f"could not parse a JSON object out of: {text[:200]!r}")

    return GoalVerdict.model_validate(parsed)


async def _retry_with_structured_output(
    forked_agent,
    fork_input: list,
    fork_ctx,
    run_config,
    run_hooks: RunHooks,
    llm_config,
) -> GoalVerdict:
    """One-shot fallback when the plain-text JSON verdict couldn't be parsed.

    Sets ``output_type=GoalVerdict`` on the SAME forked agent/tool list and
    re-issues exactly one more isolated call so the SDK enforces/coerces a
    structured response instead of free-form text. This intentionally
    sacrifices the exact ``tools -> system -> messages`` cache prefix this
    module otherwise preserves (adding ``output_type`` changes the request
    shape — see the module docstring) — but only on this rare fallback path,
    never on the common one, so the cache benefit is preserved for the
    overwhelming majority of verifier calls.
    """
    forked_agent.output_type = GoalVerdict

    from siada.foundation.context import context_var_scope, LLM_CONFIG

    try:
        with context_var_scope(LLM_CONFIG, llm_config):
            result = await Runner.run(
                forked_agent,
                input=fork_input,
                context=fork_ctx,
                run_config=run_config,
                hooks=run_hooks,
                max_turns=1,
                session=None,  # isolated — nothing persisted to the main session
            )
    except MaxTurnsExceeded:
        return GoalVerdict(
            passed=False,
            reason=(
                "Goal verification attempted a tool call instead of returning "
                "a verdict on the structured-output retry; will retry next turn."
            ),
            systemError=True,
        )
    except ModelBehaviorError as e:
        return GoalVerdict(
            passed=False,
            reason=(
                f"Goal verification model behavior error on structured-output "
                f"retry ({e}); will retry next turn."
            ),
            systemError=True,
        )
    except Exception as e:
        logger.error(
            "[goal-verifier] structured-output retry failed: %s", e, exc_info=True,
        )
        return GoalVerdict(
            passed=False,
            reason=f"Goal verification structured-output retry failed ({e}); will retry next turn.",
            systemError=True,
        )

    output = result.final_output
    if isinstance(output, GoalVerdict):
        return output
    try:
        return GoalVerdict.model_validate(output)
    except Exception as e:
        logger.warning(
            "[goal-verifier] structured-output retry returned an unexpected "
            "shape (%r): %r", e, output,
        )
        return GoalVerdict(
            passed=False,
            reason=(
                "Verifier returned an unparsable response even with "
                "structured output; treating as not yet met."
            ),
            systemError=True,
        )


class _VerifierReadonlySession:
    """Read-only stand-in for RunningSession, mirroring
    side_question._BtwReadonlySession: exposes only ``siada_config`` and a
    unique ``session_id`` so ``CodeAgentContext.model_run_config`` /
    ``.session_id`` resolve correctly, without giving the fork access to the
    real session's mutable state (task_message_state, checkpoint_tracker,
    openai_session).
    """

    def __init__(self, real_session):
        self.siada_config = real_session.siada_config
        self.session_id = f"{real_session.session_id}-goalverify-{_next_verifier_seq()}"


async def verify_goal_with_context(
    context: "CodeAgentContext", fork_input: list
) -> GoalVerdict:
    """Run the isolated verifier call inside a BTW-style fork of the main
    agent, and return its structured verdict.

    Args:
        context: The LIVE main ``CodeAgentContext`` for this workspace (the
            caller looks this up, e.g. via ``SiadaRunner._context_cache``).
            Supplies the agent name (via ``context.session``) and every
            system-prompt-relevant field the fork needs to reproduce the
            main thread's request shape.
        fork_input: Full message list to send — see ``build_verifier_input``.

    On any failure (LLM error, malformed output, missing session, a tool
    call attempt, etc.) returns a ``passed=false`` verdict rather than
    raising — a verifier hiccup should force another turn (safe default),
    never silently mark a goal complete or crash the turn loop.
    """
    try:
        real_session = context.session
        if real_session is None:
            raise ValueError("verify_goal_with_context requires context.session")

        from siada.agent_hub.hooks.siada_basic_agent_hooks import SiadaBasicAgentHooks
        from siada.foundation.code_agent_context import CodeAgentContext
        from siada.services.siada_runner import SiadaRunner
        from siada.services.sub_agent_run_config import build_sub_agent_run_config

        agent_name = real_session.siada_config.agent_name
        agent = await SiadaRunner.get_agent(agent_name)

        stub_session = _VerifierReadonlySession(real_session)


        # model_construct() bypasses Pydantic validation — same rationale as
        # side_question._run_async: stub_session isn't a RunningSession
        # instance, and unknown/newer fields on the running process must not
        # raise. holographic_provider / memory_store are cleared to avoid
        # side effects (prefetch, fact_count, memory scheduler) from this
        # read-only call.
        fork_ctx = CodeAgentContext.model_construct(
            root_dir=context.root_dir,
            interactive_mode=getattr(context, "interactive_mode", False),
            combined_memory=context.combined_memory,
            preferred_language=getattr(context, "preferred_language", None),
            pre_plan=getattr(context, "pre_plan", False),
            siadaignore_controller=getattr(context, "siadaignore_controller", None),
            holographic_provider=None,
            memory_store=None,
            # max_turns=1: a verdict is a single, no-tool response. The deny
            # guardrail uses reject_content (it does NOT raise), so it never
            # aborts the run by itself. If the model still tries a tool, it
            # cannot be recovered into a structured verdict within a single
            # turn and the run raises MaxTurnsExceeded — handled below.
            max_turns=1,
            session=stub_session,
        )

        forked_agent = copy.copy(agent)
        forked_agent.name = "GoalVerifier"
        forked_agent.hooks = SiadaBasicAgentHooks()
        # Deliberately do NOT set forked_agent.output_type = GoalVerdict here
        # (unlike the original implementation): a structured output_type
        # folds a JSON schema / tool definition into the outgoing request,
        # which changes the request shape the provider's prompt cache keys
        # off of — busting the exact cache prefix (tools -> system ->
        # messages) this whole module exists to preserve. Instead,
        # build_verifier_request_message() asks the model to answer with a
        # plain JSON object in its final text response, and
        # _parse_goal_verdict() below parses that text back into a
        # GoalVerdict after the run completes. If that fails,
        # _retry_with_structured_output() below sets output_type and retries
        # once, sacrificing the cache prefix only on that rare fallback.

        # SiadaRunner._agent_cache does stale-while-revalidate refresh: every
        # cache-hit get_agent() call fires a background task that eventually
        # REPLACES the cached instance with a brand new agent object whose
        # ``tools`` is still just the bare constructor default (see
        # CodeGenAgent.__init__ -> _get_base_tools()) — web_search/web_fetch/
        # Lark tools are only added by configure_tools_for_context(), which
        # the MAIN thread calls at the top of every run()/run_streamed(), but
        # which this verifier path historically skipped (relying on the
        # now-proven-false assumption that ``agent`` here is still the exact
        # object the main turn just configured). Re-run it here on
        # ``forked_agent`` — the private copy.copy() above, NOT the shared
        # ``agent`` still sitting in SiadaRunner._agent_cache — so this never
        # mutates the cached singleton (which other concurrent callers, e.g.
        # a different session sharing this agent_name, may be relying on).
        # copy.copy() is shallow, so forked_agent.tools currently ALIASES
        # agent.tools; configure_tools_for_context() only ever REBINDS
        # ``self.tools`` to a brand new list (see CodeGenAgent.
        # configure_tools_for_context), it never mutates the list object in
        # place, so calling it on forked_agent breaks that alias cleanly
        # without touching agent.tools.
        if hasattr(forked_agent, "configure_tools_for_context"):
            try:
                forked_agent.configure_tools_for_context(context)
            except Exception as e:
                logger.warning(
                    "[goal-verifier] configure_tools_for_context failed (%r); "
                    "continuing with whatever tools this forked agent "
                    "already has (may miss cache this turn)", e,
                )

        # Materialize the FULL tool list (MCP + local, same order the main
        # thread sends them) so the cache prefix is byte-identical. Reads
        # from ``forked_agent`` (just reconfigured above), not the shared
        # cached ``agent``, for the same "never touch the singleton" reason.
        # On any failure, fall back to local-only tools.
        #
        # IMPORTANT: wraps the REAL main ``context`` here, not ``fork_ctx``.
        # ``get_all_tools`` uses the wrapped context for (a) each
        # ``FunctionTool.is_enabled(run_context, agent)`` check and (b) MCP
        # tool listing/filtering — both of which decide WHICH tools end up
        # in the request. ``fork_ctx`` is a stripped-down stub (several
        # fields cleared/defaulted, e.g. memory_store=None), so using it here
        # could silently compute a different enabled-tool set than the main
        # thread just sent, busting the exact cache prefix this module
        # exists to preserve.
        #
        # This does NOT mutate the shared ``context`` object: RunContextWrapper
        # only wraps ``context`` by reference in its own brand-new dataclass
        # instance (fresh ``usage``/``_approvals``/``turn_input``/``tool_input``
        # fields, unrelated to the wrapper the main turn's Runner.run created) —
        # nothing here writes back onto ``context`` itself. The only
        # get_all_tools side effects are (a) MCP tool-list caching, which lives
        # on the MCPServer object, not on context, and (b) is_enabled checks,
        # which for every tool in this codebase are plain booleans that never
        # read/write context. So this call is read-only w.r.t. ``context``.
        try:
            all_tools = await forked_agent.get_all_tools(RunContextWrapper(context))
        except Exception as e:
            logger.warning(
                "[goal-verifier] get_all_tools failed (%r); falling back to "
                "local tools only (MCP users may miss cache this turn)", e,
            )
            all_tools = list(forked_agent.tools)

        # MCP tools are now materialized into all_tools — clear mcp_servers so
        # the SDK doesn't try to (re)connect them from this call.
        forked_agent.mcp_servers = []
        forked_agent.tools = _wrap_tools_with_deny(all_tools)

        run_config = build_sub_agent_run_config(fork_ctx)
        run_hooks = RunHooks()

        # should_enable_parallel_tool_calls_in_prompt() (tool_use.py), which
        # decides whether the rendered TOOL USE section uses parallel-call or
        # sequential ("one tool per message") wording, reads the LLM_CONFIG
        # contextvar directly rather than run_context.context — it ignores
        # fork_ctx entirely. Contextvars set by a parent asyncio Task are not
        # guaranteed visible here (same pitfall documented on
        # set_context_var_inplace / side_question.run_side_question's "must
        # re-set in the fork thread" comment), so without re-seeding it the
        # forked agent can render a DIFFERENT TOOL USE/RULES branch than the
        # main turn just did — busting the exact cache prefix this module
        # exists to preserve. context_var_scope restores the prior value on
        # exit so nothing leaks into unrelated work on this task/thread.
        from siada.foundation.context import context_var_scope, LLM_CONFIG

        llm_config = getattr(real_session.siada_config, "llm_config", None)
        with context_var_scope(LLM_CONFIG, llm_config):
            result = await Runner.run(
                forked_agent,
                input=fork_input,
                context=fork_ctx,
                run_config=run_config,
                hooks=run_hooks,
                max_turns=1,
                session=None,  # isolated — nothing persisted to the main session
            )

        # result.final_output is now plain text (no output_type set — see
        # the module docstring / comment above), so parse it into the
        # GoalVerdict shape ourselves rather than relying on the SDK's
        # structured-output coercion.
        raw_output = result.final_output
        text = raw_output if isinstance(raw_output, str) else str(raw_output or "")
        try:
            return _parse_goal_verdict(text)
        except Exception as e:
            logger.warning(
                "[goal-verifier] failed to parse verdict JSON from model "
                "output (%r); raw=%r; retrying once with output_type=GoalVerdict",
                e, text[:200],
            )
            return await _retry_with_structured_output(
                forked_agent, fork_input, fork_ctx, run_config, run_hooks, llm_config,
            )

    except MaxTurnsExceeded:
        # The deny guardrail never raises; reaching here means the model
        # spent its single turn trying to call a tool instead of returning a
        # verdict. Fail safe: force another main-agent turn. systemError=True
        # so turn_hooks.maybe_run_goal_verifier applies the much smaller
        # GOAL_MAX_CONSECUTIVE_SYSTEM_ERRORS budget instead of the generous
        # one reserved for genuine "not yet achieved" judgments.
        return GoalVerdict(
            passed=False,
            reason=(
                "Goal verification attempted a tool call instead of "
                "returning a verdict; will retry next turn."
            ),
            systemError=True,
        )
    except ModelBehaviorError as e:
        return GoalVerdict(
            passed=False,
            reason=f"Goal verification model behavior error ({e}); will retry next turn.",
            systemError=True,
        )
    except Exception as e:
        logger.error(f"[goal-verifier] verify_goal_with_context failed: {e}", exc_info=True)
        return GoalVerdict(
            passed=False,
            reason=f"Goal verification failed due to an internal error ({e}); will retry next turn.",
            systemError=True,
        )


async def run_goal_verification(
    file_session: "FileSession", goal: "Goal", context: "CodeAgentContext"
) -> GoalVerdict:
    """Compose ``build_verifier_input()`` + ``verify_goal_with_context()`` as
    a single coroutine, so callers need exactly one ``asyncio.run()`` call
    site.
    """
    fork_input = await build_verifier_input(file_session, goal, context)
    return await verify_goal_with_context(context, fork_input)
