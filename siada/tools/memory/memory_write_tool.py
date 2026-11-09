"""
memory_write_tool: LLM-callable tool for writing to MEMORY.md and USER.md.

Two-layer design:
- memory_impl: pure business logic, no framework dependency, directly testable
- memory: @function_tool wrapper, extracts store from context and delegates
"""
import json
from typing import Literal, Optional

from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext

MEMORY_DOCS = """
    Save durable information to persistent memory that survives across sessions.
    Memory is injected into future sessions, so keep it compact and focused on
    facts that will still matter later.

    WHEN TO SAVE (do this proactively, don't wait to be asked):
    - User corrects you or says 'remember this' / 'don't do that again'
    - User shares a preference, habit, or personal detail (name, role, coding style)
    - You discover something about the environment (OS, installed tools, project structure)
    - You learn a convention, API quirk, or workflow specific to this user's setup
    - You identify a stable fact that will be useful again in future sessions

    PRIORITY: User preferences and corrections > environment facts > procedural knowledge.
    The most valuable memory prevents the user from having to repeat themselves.

    Do NOT save task progress, session outcomes, completed-work logs, or temporary
    TODO state to memory; use smart_search_memory to recall those from past transcripts.

    TWO TARGETS:
    - 'user': who the user is — name, role, preferences, communication style, pet peeves
    - 'memory': your notes — environment facts, project conventions, tool quirks, lessons learned

    ACTIONS: add (new entry), replace (update existing — old_text identifies it),
             remove (delete — old_text identifies it).
    Each `add` call saves ONE atomic fact. For multiple facts, call `add` separately.

    SKIP: trivial/obvious info, things easily re-discovered, raw data dumps,
    and temporary task state.

    Write memories as declarative facts, not instructions to yourself.
    'User prefers concise responses' ✓  —  'Always respond concisely' ✗
"""

def memory_impl(
    store,
    action: str,
    target: str,
    content: Optional[str],
    old_text: Optional[str],
    *,
    holographic_provider=None,
) -> str:
    """Business logic layer — validate args, dispatch to store, return JSON string.

    When ``holographic_provider`` is supplied and the call is a successful
    ``add``, the same content is mirrored into the holographic fact_store with
    a category derived from ``target`` (``user`` → ``user_pref``, ``memory`` →
    ``general``). The mirror is best-effort: failures are logged but never
    surface to the LLM, and ``replace`` / ``remove`` are *not* mirrored
    (markdown is the source of truth for those edits).
    """
    if store is None:
        return json.dumps({"success": False, "error": "Memory disabled for this agent"})

    if action == "add":
        if not content:
            return json.dumps({"success": False, "error": "content is required for action 'add'"})
        result = store.add(target, content)
    elif action == "replace":
        if not old_text:
            return json.dumps({"success": False, "error": "old_text is required for action 'replace'"})
        if not content:
            return json.dumps({"success": False, "error": "content is required for action 'replace'"})
        result = store.replace(target, old_text, content)
    elif action == "remove":
        if not old_text:
            return json.dumps({"success": False, "error": "old_text is required for action 'remove'"})
        result = store.remove(target, old_text)
    else:
        return json.dumps({"success": False, "error": f"Unknown action '{action}'. Use add, replace, or remove."})

    # Mirror successful adds into the holographic store so structured queries
    # see them too. See design_docs/siada-holographic-memory-introduction.md §7.2.
    if (
        holographic_provider is not None
        and action == "add"
        and isinstance(result, dict)
        and result.get("success")
    ):
        try:
            holographic_provider.on_memory_write(action, target, content)
        except Exception:
            # Provider already swallows its own errors but defend in depth.
            pass

    return json.dumps(result)


@function_tool(
    name_override="memory", description_override=MEMORY_DOCS
)
async def memory(
    context: RunContextWrapper[CodeAgentContext],
    action: Literal["add", "replace", "remove"],
    target: Literal["memory", "user"],
    content: Optional[str] = None,
    old_text: Optional[str] = None,
) -> str:
    ctx = context.context
    return memory_impl(
        ctx.memory_store,
        action,
        target,
        content,
        old_text,
        holographic_provider=getattr(ctx, "holographic_provider", None),
    )
