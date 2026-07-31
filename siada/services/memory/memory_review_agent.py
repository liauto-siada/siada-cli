"""
MemoryReviewAgent: Inter-session inline memory reviewer.

Triggered by ProactiveScheduler after 30-minute session silence (serialized after
MemoryAgent). Reviews the session content and updates MEMORY.md / USER.md via the
`memory` write tool. When holographic memory is enabled, also exposes
``fact_store`` so the review agent can persist structured atomic facts.
"""
import logging
from typing import TYPE_CHECKING, Optional

from siada.tools.memory.memory_write_tool import memory as memory_write_tool
from siada.tools.memory.fact_tools import fact_store as fact_store_tool

if TYPE_CHECKING:
    from agents.memory.session import SessionABC

logger = logging.getLogger(__name__)

MEMORY_REVIEW_SYSTEM_PROMPT = """\
You are a memory review assistant for a coding agent.

Your job is to review a session conversation and decide whether to update
the agent's persistent memory files.

You have one tool called `memory` with a `target` parameter:
- target="memory": Facts about the environment, tools, project conventions, and
  technical observations that will help the agent in future sessions.
- target="user": Facts about the user — their preferences, work style, communication
  patterns, and recurring corrections.

Current MEMORY.md content:
{memory_content}

Current USER.md content:
{user_content}

Guidelines:
- For `user`: Has the user revealed preferences, work habits, or made corrections
  that indicate how they want the agent to behave? Recurring patterns matter most.
- For `memory`: Are there stable facts about the environment, tools, or project
  that the agent would benefit from knowing in future sessions?
- Write entries as concise declarative facts.
- If nothing is worth saving, reply "Nothing to save." and stop.
- Do NOT record session-specific outcomes, task progress, or one-off steps.\
"""

# Extra block appended only when holographic memory is enabled, so the LLM
# knows it has a second tool and which one to pick.
HOLOGRAPHIC_REVIEW_HINT = """\

You also have `fact_store` for **structured atomic facts** with named
entities and a category. Prefer it over `memory` when the information has
clear named entities and will likely be queried by entity name later.

Decision rule:
- 1-2 sentence preference / habit / agent rule → `memory(target=...)`
- 1-2 sentence atomic fact with named entities → `fact_store(action="add", category=..., content=...)`

Don't write the same content to both — `memory(target="user"|"memory")`
writes are already mirrored to holographic automatically.

Suggested categories: user_pref / project / tool / decision / env / general\
"""


def _build_memory_review_agent(system_prompt: str, *, with_fact_store: bool):
    """Build and return the MemoryReviewAgent.

    ``with_fact_store`` toggles whether the holographic ``fact_store`` tool is
    exposed alongside the inline ``memory`` write tool.
    """
    from agents import Agent
    from siada.agent_hub.hooks.siada_agent_hooks import SiadaAgentHooks

    tools = [memory_write_tool]
    if with_fact_store:
        tools.append(fact_store_tool)

    return Agent(
        name="MemoryReviewAgent",
        instructions=system_prompt,
        tools=tools,
        hooks=SiadaAgentHooks(),
    )


async def review_and_update_inline_memory(
    session_content: str,
    *,
    session: "Optional[SessionABC]" = None,
) -> dict:
    """
    Review a session and decide whether to update MEMORY.md / USER.md.

    Called serially after analyze_and_update_memory() in _analyze_session_file().

    Args:
        session_content: Markdown rendering of the session conversation.
        session: Optional ``SessionABC`` instance forwarded to ``Runner.run``.
            When supplied (e.g. from the memory benchmark) the runner records
            every turn — agent reasoning and ``memory`` tool calls — back into
            this session, so callers can read out the full extraction trace
            via ``await session.get_items()``. Production callers
            (ProactiveScheduler) leave it ``None`` to keep behaviour unchanged.

    Returns:
        ``{"success": True}`` (or ``{"success": True, "skipped": ...}``) on
        success. When ``session`` is provided, the result also includes
        ``"items"``: the post-run conversation trace.
    """
    try:
        from siada.config.config_loader import load_conf
        conf = load_conf()
        mc = conf.memory_config
        if not mc.enabled:
            return {"success": True, "skipped": "memory disabled"}

        from siada.services.memory.memory_store import MemoryStore
        store = MemoryStore(
            memory_char_limit=mc.memory_char_limit,
            user_char_limit=mc.user_char_limit,
            memory_facts_enabled=mc.memory_facts_enabled,
            user_profile_enabled=mc.user_profile_enabled,
        )
        store.load_from_disk()

        # Format current memory blocks for the system prompt
        memory_content = store.format_for_system_prompt("memory") or "(empty)"
        user_content = store.format_for_system_prompt("user") or "(empty)"

        # Optionally spin up a HolographicProvider so the review agent can
        # write structured facts. We construct it locally (rather than reuse
        # the runner-cached one) since this code path runs in the proactive
        # scheduler, not inside an agent run.
        holographic_provider = None
        hc = getattr(conf, "holographic_config", None)
        if hc is not None and hc.enabled:
            try:
                from siada.services.memory.holographic.provider import HolographicProvider
                holographic_provider = HolographicProvider.from_config(hc)
                holographic_provider.initialize()
            except Exception as e:
                logger.debug("[memory-review] HolographicProvider init failed: %s", e)
                holographic_provider = None

        prompt_body = MEMORY_REVIEW_SYSTEM_PROMPT.format(
            memory_content=memory_content,
            user_content=user_content,
        )
        # When holographic memory is wired in for this run, append the
        # ``HOLOGRAPHIC_REVIEW_HINT`` so the LLM also picks up
        # ``fact_store`` for atomic-fact persistence; otherwise ship the
        # memory-only system prompt. The benchmark used to keep this
        # disabled to A/B-compare layers — that comparison is done now,
        # so the runtime branch is back.
        with_fact_store = holographic_provider is not None
        system_prompt = (
            prompt_body + HOLOGRAPHIC_REVIEW_HINT
            if with_fact_store
            else prompt_body
        )

        agent = _build_memory_review_agent(
            system_prompt, with_fact_store=with_fact_store,
        )

        from siada.foundation.code_agent_context import CodeAgentContext
        from pathlib import Path
        memory_dir = Path.home() / ".siada-cli" / "workspace" / "memory"
        context = CodeAgentContext(
            root_dir=str(memory_dir),
            memory_store=store,
            holographic_provider=holographic_provider,
        )

        from agents import Runner
        from siada.provider.fast_llm import build_fast_run_config

        # Sandwich structure: task instruction wraps both sides of the session
        # content to combat "lost in the middle" attention degradation. The
        # tail-side REMINDER mirrors the tools available in the system prompt
        # so the LLM doesn't forget about `fact_store` after a long transcript.
        if with_fact_store:
            reminder = (
                "## REMINDER: You are extracting memories from the session above.\n"
                "You have at most 10 turns total — be efficient and stop once "
                "all worthwhile facts are saved.\n"
                "Now call `memory` for preferences/habits or `fact_store` for "
                "atomic facts with named entities, or reply \"Nothing to save.\""
            )
        else:
            reminder = (
                "## REMINDER: You are extracting memories from the session above.\n"
                "You have at most 10 turns total — be efficient and stop once all "
                "worthwhile facts are saved.\n"
                "Now call `memory` to save durable facts, or reply \"Nothing to save.\""
            )

        user_message = (
            "## TASK: Please review this session and update memory if appropriate. "
            "Be concise and keep turns to a minimum.\n\n"
            "---BEGIN SESSION TRANSCRIPT---\n\n"
            f"{session_content}\n\n"
            "---END SESSION TRANSCRIPT---\n\n"
            f"{reminder}"
        )
        try:
            await Runner.run(
                agent,
                input=user_message,
                context=context,
                run_config=build_fast_run_config(),
                max_turns=10,
                session=session,
            )
        finally:
            # Always release the holographic SQLite connection.
            #
            # Until this finally was added, every call to
            # ``review_and_update_inline_memory`` leaked one open SQLite
            # connection on ``facts.db`` (the provider was created locally
            # but never closed). Two practical consequences:
            #
            # * fd accumulation on long benchmark runs — each fact left
            #   another live connection behind.
            # * the WAL was never checkpointed because at least one writer
            #   stayed open, so external snapshots of just ``facts.db``
            #   (without ``-wal`` / ``-shm``) saw an empty database.
            # * per-fact reset relied on Linux/macOS ``unlink`` semantics
            #   to "soft delete" the file under a still-open fd; on Windows
            #   that path raises ``PermissionError``.
            #
            # Closing here makes the lifetime explicit: provider lives
            # exactly as long as the review run.
            if holographic_provider is not None:
                try:
                    holographic_provider.shutdown()
                except Exception as exc:  # pragma: no cover — defensive
                    logger.debug(
                        "[memory-review] HolographicProvider shutdown failed: %s", exc
                    )

        return {"success": True}
    except Exception as e:
        logger.error("MemoryReviewAgent failed: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}
