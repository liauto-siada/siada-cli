"""Sentinel markers for distinguishing injected blocks from user content.

Why a marker layer?
-------------------
Several places along the user-input pipeline silently prepend / append
synthesized content to the user-role message before handing it to the LLM:

* ``CodeGenAgent._inject_holographic_prefetch`` — relevant facts pulled from
  the holographic memory store, prepended as a markdown block.
* ``LarkAgentExecutor._build_user_input`` — Feishu/Lark IM context blocks:
  the quoted/replied-message body (head) and conversation metadata + mention
  hints (tail). Both are "untrusted metadata" injected so the LLM understands
  the IM context, not authored by the user.

All of these end up persisted inline as part of the user message in
``api_history.json``, where downstream consumers want to *distinguish* the
injection from the user's actual text:

* Frontend renderer — chat bubble should show the user's real message only.
* Memory review (``MemoryReviewAgent``) — must not extract "user
  preferences" from a block that *we* injected.

To support that without inventing a structured-content list (which would
force every LLM provider in the chain to round-trip a custom type), we wrap
each injection with HTML-style sentinel comments. The markers are inert
text from the LLM's perspective — they just sit inside the user message —
and trivially detectable / strippable from any consumer.

Three marker pairs are defined, one per injection family:

* ``HOLOGRAPHIC_PREFETCH:BEGIN/END`` — holographic facts block.
* ``IM_CONTEXT_INJECTION:BEGIN/END`` — Feishu/Lark IM context blocks
  (quoted reply, conversation info, mention hints).
* ``BENCHMARK_HINT:BEGIN/END`` — anything wrapped in this pair is kept
  in the user message that ships to the LLM but is **stripped before
  the prefetch query is built** (see
  ``CodeGenAgent._inject_holographic_prefetch``). Used by the memory
  benchmark to keep its "use search_memory / fact_store" hint and
  "write the answer to <tmp_path>" instruction out of the embedding
  query — without that, prefetch would surface facts about the tools
  / temp paths instead of facts about the user's question.

Generic helpers (``strip_block_between`` / ``strip_all_injection_blocks``)
operate on any marker pair, so adding a fourth injection family later is
just one tuple.
"""

from __future__ import annotations

import re
from typing import List, Tuple

# ── Marker pairs ──────────────────────────────────────────────────────

# Holographic memory facts injected before the user message.
HOLOGRAPHIC_PREFETCH_BEGIN = "<!--HOLOGRAPHIC_PREFETCH:BEGIN-->"
HOLOGRAPHIC_PREFETCH_END = "<!--HOLOGRAPHIC_PREFETCH:END-->"

# Feishu/Lark IM context blocks (quoted reply body, conversation metadata,
# mention hints). Same shape as holographic, different namespace so logs /
# greps stay unambiguous.
IM_CONTEXT_INJECTION_BEGIN = "<!--IM_CONTEXT_INJECTION:BEGIN-->"
IM_CONTEXT_INJECTION_END = "<!--IM_CONTEXT_INJECTION:END-->"

# Benchmark / harness hints that the LLM should still see in the user
# message but the holographic prefetch must NOT use when building its
# embedding query (e.g. "use search_memory / fact_store" steering, or
# "write the answer to /tmp/abc.txt" file-output instructions). Without
# stripping these, prefetch would surface facts about the tools / paths
# rather than the user's actual question.
#
# Stripped from the prefetch query in ``CodeGenAgent._inject_holographic_prefetch``;
# the wrapped block itself stays in ``user_input`` so the LLM keeps reading it.
BENCHMARK_HINT_BEGIN = "<!--BENCHMARK_HINT:BEGIN-->"
BENCHMARK_HINT_END = "<!--BENCHMARK_HINT:END-->"

# All known injection sentinel pairs. ``strip_all_injection_blocks`` walks
# this list, so adding a new marker family is one append away.
#
# ``BENCHMARK_HINT`` is intentionally NOT included here: those blocks are
# meant to remain in the user message (the LLM should see them); only the
# prefetch path strips them via ``strip_benchmark_hint_block`` directly.
_ALL_INJECTION_SENTINELS: tuple[tuple[str, str], ...] = (
    (HOLOGRAPHIC_PREFETCH_BEGIN, HOLOGRAPHIC_PREFETCH_END),
    (IM_CONTEXT_INJECTION_BEGIN, IM_CONTEXT_INJECTION_END),
)


# ── Generic primitives ────────────────────────────────────────────────

def _build_block_regex(begin: str, end: str) -> re.Pattern[str]:
    """Compile a regex matching a sentinel-wrapped block plus trailing space."""
    return re.compile(
        re.escape(begin)
        + r"\s*(?P<body>.*?)\s*"
        + re.escape(end)
        + r"\s*",
        re.DOTALL,
    )


def wrap_block(content: str, begin: str, end: str) -> str:
    """Wrap ``content`` between sentinels, ending in two newlines.

    Returns an empty string if ``content`` is empty / whitespace-only, so
    callers can simply concatenate without checking emptiness first.
    """
    body = (content or "").strip()
    if not body:
        return ""
    return f"{begin}\n{body}\n{end}\n\n"


def strip_block_between(text: str, begin: str, end: str) -> str:
    """Remove every sentinel-wrapped block (between ``begin`` / ``end``) from text."""
    if not isinstance(text, str) or not text or begin not in text:
        return text
    cleaned = _build_block_regex(begin, end).sub("", text)
    return cleaned.lstrip("\n")


def split_blocks_between(
    text: str, begin: str, end: str,
) -> Tuple[List[str], str]:
    """Split ``text`` into ``(block_bodies, remaining_text)`` for one marker pair."""
    if not isinstance(text, str) or not text or begin not in text:
        return [], text
    pattern = _build_block_regex(begin, end)
    blocks = [m.group("body").strip() for m in pattern.finditer(text)]
    cleaned = pattern.sub("", text).lstrip("\n")
    return blocks, cleaned


def strip_all_injection_blocks(text: str) -> str:
    """Strip every known injection block (holographic + IM context).

    Useful for downstream consumers that don't care which family the
    injection belongs to — they just want the user's actual text.
    """
    if not isinstance(text, str) or not text:
        return text
    cleaned = text
    for begin, end in _ALL_INJECTION_SENTINELS:
        if begin in cleaned:
            cleaned = strip_block_between(cleaned, begin, end)
    return cleaned


def has_any_injection_block(text: str) -> bool:
    """Whether ``text`` contains at least one known injection block."""
    if not isinstance(text, str) or not text:
        return False
    return any(b in text for b, _ in _ALL_INJECTION_SENTINELS)


# ── Holographic-prefetch convenience wrappers ─────────────────────────
# Kept as thin wrappers over the generics so existing call sites stay
# concise and the intent reads at the call site.

def wrap_prefetch_block(prefix: str) -> str:
    """Wrap a holographic-prefetch facts block."""
    return wrap_block(prefix, HOLOGRAPHIC_PREFETCH_BEGIN, HOLOGRAPHIC_PREFETCH_END)


def has_prefetch_block(text: str) -> bool:
    """Whether ``text`` contains at least one wrapped holographic-prefetch block."""
    if not isinstance(text, str) or not text:
        return False
    return (
        HOLOGRAPHIC_PREFETCH_BEGIN in text
        and HOLOGRAPHIC_PREFETCH_END in text
    )


def strip_prefetch_block(text: str) -> str:
    """Remove every holographic-prefetch wrapped block from ``text``."""
    return strip_block_between(text, HOLOGRAPHIC_PREFETCH_BEGIN, HOLOGRAPHIC_PREFETCH_END)


def split_prefetch_blocks(text: str) -> Tuple[List[str], str]:
    """Split ``text`` into prefetch block bodies + cleaned remainder."""
    return split_blocks_between(text, HOLOGRAPHIC_PREFETCH_BEGIN, HOLOGRAPHIC_PREFETCH_END)


# ── IM-context convenience wrappers ───────────────────────────────────

def wrap_im_context_block(content: str) -> str:
    """Wrap a Feishu/Lark IM context block (quoted reply / metadata / hints)."""
    return wrap_block(content, IM_CONTEXT_INJECTION_BEGIN, IM_CONTEXT_INJECTION_END)


def strip_im_context_block(text: str) -> str:
    """Remove every IM-context wrapped block from ``text``."""
    return strip_block_between(text, IM_CONTEXT_INJECTION_BEGIN, IM_CONTEXT_INJECTION_END)


# ── Benchmark-hint convenience wrappers ───────────────────────────────
# Used to keep benchmark / harness instructions visible to the LLM but
# excluded from the holographic-prefetch query.

def wrap_benchmark_hint_block(content: str) -> str:
    """Wrap content the LLM should see but prefetch should ignore."""
    return wrap_block(content, BENCHMARK_HINT_BEGIN, BENCHMARK_HINT_END)


def strip_benchmark_hint_block(text: str) -> str:
    """Remove every benchmark-hint wrapped block (sentinels included).

    Called by the prefetch path immediately before the embedding query
    is constructed. Operates only on the in-flight query string — the
    user-facing ``user_input`` keeps the wrapped block intact so the
    LLM still reads it.
    """
    return strip_block_between(text, BENCHMARK_HINT_BEGIN, BENCHMARK_HINT_END)
