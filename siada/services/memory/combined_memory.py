"""Orchestrator that assembles ``combined_memory`` for the system prompt.

``combined_memory`` is a single string injected into every agent's system
prompt. It is **session-stable**: built once at session start (from
``SiadaRunner._build_agent_context``) and rebuilt only on context-compaction
events (from ``api_message_transfer_filter``). Per-turn ``get_system_prompt``
calls read ``context.combined_memory`` directly without touching this module,
so any work here runs at most a few times per session — never per turn.

The orchestrator's job is purely composition. The output layout (top to
bottom) is::

    rule_memory                    (workspace siada_rule.md hierarchy)
    siada.md                       (user-scoped workspace memory)
    Memory Layers — Common Rules   (only when stored memory is active)
    Inline Memory                  (MEMORY/USER snapshot blocks + memory tool guidance,
                                    all wrapped in a single ==== section)
    Session Search                 (search_memory tool guidance)
    Structured Fact Memory         (fact_store guidance + fact_count snapshot)

Each piece's text lives next to its owner (``memory_store.MEMORY_GUIDANCE``,
``memory_tool.SESSION_SEARCH_GUIDANCE``,
``holographic.provider.HOLOGRAPHIC_GUIDANCE_TEMPLATE``); this module just
stitches them together. That keeps the per-layer guidance text one edit
away from the layer it documents and lets the orchestrator stay layer-
agnostic.

Two small pieces of text **do** live here on purpose:

* ``_MEMORY_LAYERS_COMMON_RULES`` — the "follow the user when stored
  memory conflicts" rule used to be duplicated across each layer's
  guidance. It applies to all stored-memory layers below, so it's
  factored out into one shared block introduced by this orchestrator.
* The ``Inline Memory`` heading + outer ``====`` markers around the
  memory data blocks and ``MEMORY_GUIDANCE`` body — keeping the heading
  here means MEMORY/USER blocks (which are *data*) and the guidance
  text (which is *behavioural*) ship as a single visually-grouped
  section, instead of three loose ==== blocks the LLM has to mentally
  re-merge.

Why a new module rather than methods on ``SiadaRunner``?
``SiadaRunner`` is the agent lifecycle / RunConfig / MCP orchestrator —
shipping prompt-assembly text there bloats the runner with concerns it
should not own. Having a dedicated memory-layer module also makes it cheap
to add a fourth memory tier later (episodic, vector, etc.): a new constant
in its own module, plus one import + one append here.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


# Common rule shared across every stored-memory layer below this block.
# Used to live as a duplicated bullet inside ``MEMORY_GUIDANCE`` and
# ``HOLOGRAPHIC_GUIDANCE_TEMPLATE``; consolidated here so a future
# refinement (e.g. adding precedence between rule_memory and stored
# memory) lives in exactly one place.
#
# Intentionally placed *after* rule_memory and siada.md but *before* the
# stored-memory blocks: rule_memory and siada.md are explicit project /
# user directives, NOT auxiliary context — they are themselves
# authoritative, so this "follow the user" override doesn't apply to
# them.
_MEMORY_LAYERS_COMMON_RULES = """\
====
Memory Layers — Common Rules

The blocks below are auxiliary context drawn from prior sessions and
stored facts. When any of them conflicts with the user's current
instruction, follow the user — they are the authoritative source.
===="""


def _build_inline_memory_section(memory_store: object) -> Optional[str]:
    """Compose MEMORY/USER snapshot blocks + ``MEMORY_GUIDANCE`` into one section.

    The returned string is wrapped in a single pair of ``====`` boundaries
    with an ``Inline Memory`` heading at the top and the guidance body at
    the bottom. ``MEMORY_GUIDANCE`` is shipped here verbatim (without its
    own ``====`` wrapping, by contract) so the section reads as one
    cohesive unit:

        ====
        Inline Memory

        MEMORY (your personal notes)
        <entries...>

        USER PROFILE (who the user is)
        <entries...>

        <guidance body about how to use these blocks and the memory tool>
        ====

    Returns ``None`` when neither sub-flag yields any block AND the store
    is configured to ship no guidance — but in practice we always include
    the guidance whenever a ``MemoryStore`` exists, so this stays as a
    return value for symmetry with the caller's "if not None: append"
    pattern.
    """
    from siada.services.memory.memory_store import MEMORY_GUIDANCE

    inner_parts: list[str] = []
    memory_block = memory_store.format_for_system_prompt("memory")
    if memory_block:
        inner_parts.append(memory_block)
    user_block = memory_store.format_for_system_prompt("user")
    if user_block:
        inner_parts.append(user_block)
    # Always ship the guidance body so the LLM knows the ``memory`` tool
    # exists, even if the snapshot blocks are currently empty (fresh
    # install or both sub-flags disabled but ``memory.enabled=true``).
    inner_parts.append(MEMORY_GUIDANCE)

    body = "\n\n".join(inner_parts)
    return f"====\nInline Memory\n\n{body}\n===="


def build_combined_memory(
    workspace_path: Optional[str],
    memory_store: Optional[object],
    holographic_provider: Optional[object],
) -> Optional[str]:
    """Assemble the ``combined_memory`` snapshot.

    This function is called at session start and after every successful
    context compaction. It MUST NOT be called from per-turn paths (e.g.
    ``get_system_prompt``): it issues at most one DB query
    (``holographic_provider.fact_count()``) and a few file reads, both of
    which would scale linearly with turn count and break prompt-prefix
    caching if invoked per turn.

    Args:
        workspace_path: Active workspace dir. Used to load rule_memory and
            ``siada.md`` user memory. ``None`` skips workspace-scoped blocks.
        memory_store: An already-initialized ``MemoryStore`` whose snapshot
            was loaded via ``load_from_disk``. ``None`` skips MEMORY.md /
            USER.md blocks and the inline-memory guidance.
        holographic_provider: An initialized ``HolographicProvider``.
            ``None`` or not-ready skips the holographic guidance block.
            When provided, ``fact_count()`` is read once for the snapshot.

    Returns:
        The joined ``combined_memory`` string, or ``None`` when no source
        contributed.
    """
    parts: list[str] = []

    if workspace_path:
        # 1. rule_memory (project-level rules from siada_rule.md hierarchy)
        try:
            from siada.services.rule_memory import load_hierarchical_context
            rule_content, rule_count, _ = load_hierarchical_context(workspace_path)
            if rule_count > 0 and rule_content:
                parts.append(rule_content)
        except Exception as exc:
            logger.warning("Failed to load rule_memory: %s", exc)

        # 2. siada.md user-scoped memory
        try:
            from siada.services.siada_memory import load_siada_memory
            user_mem = load_siada_memory(workspace_path)
            if user_mem:
                parts.append(user_mem)
        except Exception as exc:
            logger.debug("Failed to load user memory: %s", exc)

    # 2.5. Common rules apply to every stored-memory layer below. Skip the
    # block entirely when none of them are configured — there's nothing
    # for the rule to govern, and the LLM doesn't need to read a rule
    # about non-existent layers.
    if memory_store is not None or holographic_provider is not None:
        parts.append(_MEMORY_LAYERS_COMMON_RULES)

    # 3. Inline Memory composite — MEMORY/USER blocks + memory-tool
    #    guidance share a single ``====`` section and one heading.
    if memory_store is not None:
        try:
            inline_section = _build_inline_memory_section(memory_store)
            if inline_section:
                parts.append(inline_section)
        except Exception as exc:
            logger.warning("Failed to format MemoryStore blocks: %s", exc)

        # 3b. session-search guidance — points the LLM at ``search_memory``
        #     for cross-session recall. Lives alongside the inline-memory
        #     section because both surfaces (inline memory + session FTS)
        #     share the ``MemoryStore`` data directory and lifecycle.
        try:
            from siada.tools.memory.memory_tool import SESSION_SEARCH_GUIDANCE
            parts.append(SESSION_SEARCH_GUIDANCE)
        except Exception as exc:
            logger.debug("Failed to load SESSION_SEARCH_GUIDANCE: %s", exc)

    # 4. Holographic guidance + fact_count snapshot. Single DB read here —
    #    must never be issued from per-turn ``get_system_prompt``.
    if holographic_provider is not None:
        try:
            from siada.services.memory.holographic.provider import (
                HOLOGRAPHIC_GUIDANCE_TEMPLATE,
            )

            is_ready = getattr(holographic_provider, "is_ready", None)
            if is_ready is None or is_ready():
                fact_count = holographic_provider.fact_count()
                parts.append(
                    HOLOGRAPHIC_GUIDANCE_TEMPLATE.format(fact_count=fact_count)
                )
        except Exception as exc:
            logger.debug("Failed to read holographic fact_count: %s", exc)
            # Still surface the tool to the LLM so a transient DB hiccup
            # doesn't hide ``fact_store`` from the system prompt.
            try:
                from siada.services.memory.holographic.provider import (
                    HOLOGRAPHIC_GUIDANCE_TEMPLATE,
                )
                parts.append(HOLOGRAPHIC_GUIDANCE_TEMPLATE.format(fact_count="?"))
            except Exception:
                pass

    return "\n\n".join(parts) if parts else None
