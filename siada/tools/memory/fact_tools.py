"""LLM-callable tools backed by the holographic memory provider.

Two tools live here:

- ``fact_store(action, ...)``  — dispatch to provider for 9 actions
  (add / search / probe / related / reason / contradict / update / remove / list)
- ``fact_feedback(fact_id, action, comment?)`` — record helpful / unhelpful / correct

Both tools follow siada's two-layer pattern (``*_impl`` for testability,
``@function_tool`` for the runtime). When holographic memory is disabled
(``context.holographic_provider`` is ``None``), they return a JSON
``{"success": false, "error": "..."}`` instead of raising.
"""

import json
from typing import List, Literal, Optional

from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext


FACT_STORE_DOCS = """
Save and query structured atomic facts with entities and trust scoring.
Facts persist in SQLite + HRR vectors and survive across sessions.
Complements (not replaces) the inline `memory` tool.

WHEN TO ADD A FACT:
- The information has clear named entities (person / project / tool / decision)
- It is one atomic statement, not a long narrative
- It will likely be queried later by entity name (e.g. "what about Phoenix?")

WHEN NOT TO ADD A FACT:
- Use `memory` instead for: short user preferences, agent rules, things that
  must always be in the system prompt
- Skip entirely for: full session summaries, tutorial-length explanations
  (those land in experience/events files via the review pipeline automatically)

ACTIONS:
- add(content, category, tags?)        — create a new fact
- search(query, limit?)                — keyword + structural search (most common)
- probe(entity, category?)             — facts where this entity is the subject
- related(entity)                      — facts structurally linked to entity
- reason(entities=[…])                 — multi-entity AND query
- contradict(threshold?)               — find conflicting fact pairs
- update(fact_id, content?, category?, trust_delta?) — modify a fact
- remove(fact_id)                      — hard delete
- list(category?, min_trust?, limit?)  — list facts (default sorted by trust)

CATEGORIES (recommended): user_pref / project / tool / decision / env / general

TIPS:
- Quote named entities for higher recall: 'Phoenix uses "Postgres 14"'
- Keep content under ~500 characters; one fact per call
- After using a fact in your answer, call fact_feedback(fact_id, "helpful")
  so the trust score rises.
""".strip()


def fact_store_impl(
    provider,
    *,
    action: str,
    content: Optional[str] = None,
    fact_id: Optional[int] = None,
    entity: Optional[str] = None,
    entities: Optional[List[str]] = None,
    query: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 10,
    min_trust: Optional[float] = None,
    trust_delta: Optional[float] = None,
    threshold: Optional[float] = None,
) -> str:
    """Pure dispatcher; provider handles all errors and returns a JSON string."""
    if provider is None:
        return json.dumps({
            "success": False,
            "error": "Holographic memory is disabled for this agent",
        })
    args = {
        "action": action,
        "content": content,
        "fact_id": fact_id,
        "entity": entity,
        "entities": entities,
        "query": query,
        "category": category,
        "tags": tags,
        "limit": limit,
        "min_trust": min_trust,
        "trust_delta": trust_delta,
        "threshold": threshold,
    }
    # Drop Nones so provider sees only what was supplied; this keeps default
    # handling inside the provider rather than spread across two places.
    args = {k: v for k, v in args.items() if v is not None}
    return provider.handle_tool_call("fact_store", args)


@function_tool(name_override="fact_store", description_override=FACT_STORE_DOCS)
async def fact_store(
    context: RunContextWrapper[CodeAgentContext],
    action: Literal[
        "add", "search", "probe", "related",
        "reason", "contradict", "update", "remove", "list",
    ],
    content: Optional[str] = None,
    fact_id: Optional[int] = None,
    entity: Optional[str] = None,
    entities: Optional[List[str]] = None,
    query: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 10,
    min_trust: Optional[float] = None,
    trust_delta: Optional[float] = None,
    threshold: Optional[float] = None,
) -> str:
    """Tool entry point — extracts the provider from context and delegates."""
    return fact_store_impl(
        context.context.holographic_provider,
        action=action,
        content=content,
        fact_id=fact_id,
        entity=entity,
        entities=entities,
        query=query,
        category=category,
        tags=tags,
        limit=limit,
        min_trust=min_trust,
        trust_delta=trust_delta,
        threshold=threshold,
    )


FACT_FEEDBACK_DOCS = """
Record feedback on a holographic memory fact to update its trust score.

Use this after referencing a fact in your answer:
- helpful   : the fact contributed correctly to your reply (trust += 0.05)
- unhelpful : the fact misled you or was wrong         (trust -= 0.10)
- correct   : the user explicitly confirmed the fact   (trust += 0.10)

The asymmetric step makes wrong facts sink twice as fast as good ones rise.
Trust below 0.3 hides the fact from default search/prefetch (soft-delete).
""".strip()


def fact_feedback_impl(
    provider,
    *,
    fact_id: int,
    action: str,
    comment: Optional[str] = None,
) -> str:
    if provider is None:
        return json.dumps({
            "success": False,
            "error": "Holographic memory is disabled for this agent",
        })
    return provider.handle_tool_call("fact_feedback", {
        "fact_id": fact_id,
        "action": action,
        "comment": comment,
    })


@function_tool(name_override="fact_feedback", description_override=FACT_FEEDBACK_DOCS)
async def fact_feedback(
    context: RunContextWrapper[CodeAgentContext],
    fact_id: int,
    action: Literal["helpful", "unhelpful", "correct"],
    comment: Optional[str] = None,
) -> str:
    return fact_feedback_impl(
        context.context.holographic_provider,
        fact_id=fact_id,
        action=action,
        comment=comment,
    )
