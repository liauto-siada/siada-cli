"""Unit tests for ``build_combined_memory``.

The helper assembles the ``combined_memory`` block injected into every
agent's system prompt. The contract verified here:

1. Holographic guidance only appears when a ``HolographicProvider`` is
   passed; otherwise it must be absent (legacy installs without
   ``holographic.enabled`` should see zero behavior change).
2. The current ``fact_count`` snapshot is interpolated into the guidance
   string so the LLM has a sense of memory scale.
3. The helper issues exactly one ``fact_count()`` call per invocation —
   we never want it called from the per-turn ``get_system_prompt`` hot
   path. We assert that here so a refactor that accidentally calls it
   twice will fail loudly.
4. Failure inside the holographic provider is non-fatal: the helper
   degrades to a placeholder fact count so the LLM still learns the tool
   exists.
5. Returns ``None`` when no source contributes (empty workspace, no
   stores) so callers can short-circuit cleanly.
"""

from siada.services.memory.combined_memory import build_combined_memory
from siada.services.memory.holographic.provider import (
    HOLOGRAPHIC_GUIDANCE_TEMPLATE,
)
from siada.services.memory.memory_store import MEMORY_GUIDANCE
from siada.tools.memory.memory_tool import SESSION_SEARCH_GUIDANCE


# ---------------------------------------------------------------------- #
# Doubles
# ---------------------------------------------------------------------- #


class _StubMemoryStore:
    """Just enough surface for ``_build_combined_memory`` to render blocks."""

    def __init__(self, memory_block: str = "", user_block: str = ""):
        self._memory = memory_block
        self._user = user_block

    def format_for_system_prompt(self, target: str) -> str:
        if target == "memory":
            return self._memory
        if target == "user":
            return self._user
        return ""


class _StubHolographicProvider:
    """Spy that records each ``fact_count`` call so we can assert on it."""

    def __init__(self, count: int = 5, *, raise_on_count: bool = False):
        self.count = count
        self.fact_count_calls = 0
        self._raise_on_count = raise_on_count

    def is_ready(self) -> bool:
        return True

    def fact_count(self) -> int:
        self.fact_count_calls += 1
        if self._raise_on_count:
            raise RuntimeError("simulated DB failure")
        return self.count


# ---------------------------------------------------------------------- #
# Tests
# ---------------------------------------------------------------------- #


def test_returns_none_when_nothing_contributes():
    # Sanity: with no workspace and both stores absent, callers should
    # see ``None`` so the system prompt skips the empty section entirely.
    assert build_combined_memory(None, None, None) is None


def test_holographic_guidance_absent_when_provider_is_none():
    # Legacy install (``holographic.enabled: false``) must produce zero
    # holographic-related text in the prompt.
    out = build_combined_memory(
        None, _StubMemoryStore(memory_block="x"), None,
    )
    assert out is not None
    assert "Structured Fact Memory" not in out
    assert "fact_store" not in out
    # Inline memory guidance still ships when MemoryStore is present —
    # together with the session-search nudge that points at search_memory.
    assert MEMORY_GUIDANCE in out
    assert SESSION_SEARCH_GUIDANCE in out


def test_session_search_guidance_absent_when_memory_store_is_none():
    # When inline memory is disabled there is no MemoryStore to back
    # ``search_memory``'s session/ FTS index, so the nudge must not ship —
    # otherwise the LLM would be encouraged to call a tool that has
    # nothing to find.
    provider = _StubHolographicProvider(count=1)
    out = build_combined_memory(None, None, provider)
    assert out is not None
    assert SESSION_SEARCH_GUIDANCE not in out
    assert "search_memory" not in out


def test_session_search_guidance_follows_memory_guidance():
    # Order contract: MEMORY_GUIDANCE must come before
    # SESSION_SEARCH_GUIDANCE so the agent first sees the persistent
    # snapshot guidance, then learns there is also a recall tool.
    store = _StubMemoryStore(memory_block="MEMORY-BLOCK")
    out = build_combined_memory(None, store, None)
    assert out is not None
    pos_mg = out.find(MEMORY_GUIDANCE.strip())
    pos_ssg = out.find(SESSION_SEARCH_GUIDANCE.strip())
    assert -1 < pos_mg < pos_ssg


def test_holographic_guidance_appears_with_provider_and_count_snapshot():
    provider = _StubHolographicProvider(count=12)
    out = build_combined_memory(None, None, provider)
    assert out is not None
    assert "Structured Fact Memory" in out
    # The actual count must be interpolated — empty placeholder would
    # mean we silently lost the snapshot.
    assert "**12 facts**" in out
    assert provider.fact_count_calls == 1, (
        "fact_count must be called exactly once per build; "
        "any per-turn read would scale linearly with turns"
    )


def test_holographic_provider_failure_falls_back_to_question_mark():
    # If the DB read fails for any reason, we still want the LLM to
    # know the tool exists — so the guidance block is included with
    # ``{fact_count}`` substituted by ``?``. Better than disappearing.
    provider = _StubHolographicProvider(raise_on_count=True)
    out = build_combined_memory(None, None, provider)
    assert out is not None
    assert "Structured Fact Memory" in out
    assert "**? facts**" in out


def test_template_format_contract():
    # Lock the guidance text contract so future refactors don't quietly
    # drop the ``{fact_count}`` placeholder. Tests above assume both the
    # placeholder format and the surrounding marker line.
    rendered = HOLOGRAPHIC_GUIDANCE_TEMPLATE.format(fact_count=7)
    assert "**7 facts**" in rendered
    assert "fact_store" in rendered


def test_memory_store_blocks_are_included_in_order():
    store = _StubMemoryStore(
        memory_block="MEMORY-BLOCK", user_block="USER-BLOCK",
    )
    out = build_combined_memory(None, store, None)
    assert out is not None
    # Order matters: memory before user before guidance, mirroring the
    # historical layout so existing prompt-cache fingerprints stay
    # similar where possible.
    pos_memory = out.find("MEMORY-BLOCK")
    pos_user = out.find("USER-BLOCK")
    pos_guidance = out.find(MEMORY_GUIDANCE.strip())
    assert -1 < pos_memory < pos_user < pos_guidance


def test_full_stack_assembly_shape():
    # End-to-end shape with all three layers active.
    store = _StubMemoryStore(
        memory_block="MEMORY-BLOCK", user_block="USER-BLOCK",
    )
    provider = _StubHolographicProvider(count=3)
    out = build_combined_memory(None, store, provider)
    assert out is not None
    # All three guidance bodies present.
    assert "MEMORY-BLOCK" in out
    assert "USER-BLOCK" in out
    assert MEMORY_GUIDANCE in out
    assert "Structured Fact Memory" in out
    assert "**3 facts**" in out
    # The new shared "follow the user when stored memory conflicts" rule
    # should be inserted once between rule_memory/siada.md and the stored
    # memory layers (here: above the inline-memory section). Lock the
    # heading so future refactors can't silently drop it.
    assert "Memory Layers — Common Rules" in out
    pos_rules = out.find("Memory Layers — Common Rules")
    pos_inline = out.find("Inline Memory")
    assert -1 < pos_rules < pos_inline
