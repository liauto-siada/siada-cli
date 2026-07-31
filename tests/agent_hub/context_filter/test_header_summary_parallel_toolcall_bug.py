"""
Reproduce the parallel-tool_call splitting bug in
SummarizeWithHeaderCompaction.compact().

The Responses API requires every function_call_output (fco) in the input
list to be paired with a function_call (fc) that has the same call_id.
When the model uses parallel_tool_calls, a single assistant turn produces
N fc messages followed by N fco messages, e.g.:

    user, asst_reason, asst_msg, fc_A, fc_B, fc_C, fco_A, fco_B, fco_C

The current `compact()` implementation may split the message list inside
this parallel group: fc_A/fc_B/fc_C land in `history_to_compress` (and get
collapsed into a free-form summary that loses the call_id structure),
while some fco_* land in `history_to_keep`. The final compacted output
will contain orphan fco entries → server returns:

    No tool call found for function call output with call_id call_xxx

This test fails (or is xfailed) until the strategy aligns split points to
tool-call group boundaries.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from siada.agent_hub.context_filter.header_summary_compaction_strategy import (
    SummarizeWithHeaderCompaction,
)


# ── Message factories (same shape as the existing test file) ────────────

def _user_msg(text="hi"):
    return {"role": "user", "content": text, "_type": "user"}


def _assistant_fc(call_id):
    return {
        "type": "function_call",
        "call_id": call_id,
        "name": "test",
        "arguments": "{}",
        "_type": "assistant",
    }


def _reasoning_msg():
    return {"type": "reasoning", "id": "__r__", "_type": "assistant"}


def _output_msg(text="ok"):
    return {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
        "_type": "assistant",
    }


def _tool_result_msg(call_id, output="ok"):
    return {"call_id": call_id, "output": output, "_type": "tool_result"}


# ── Patch Converter so plain dicts are recognized ───────────────────────

@pytest.fixture(autouse=True)
def _patch_converter():
    def _maybe_user(msg):
        return msg if isinstance(msg, dict) and msg.get("_type") == "user" else None

    def _maybe_input(_):
        return None

    def _maybe_fc(msg):
        return msg if isinstance(msg, dict) and msg.get("_type") == "assistant" else None

    def _none(_):
        return None

    def _maybe_fco(msg):
        return msg if isinstance(msg, dict) and msg.get("_type") == "tool_result" else None

    with patch.multiple(
        "siada.agent_hub.context_filter.compaction_strategy.Converter",
        maybe_easy_input_message=_maybe_user,
        maybe_input_message=_maybe_input,
        maybe_function_tool_call=_maybe_fc,
        maybe_file_search_call=_none,
        maybe_reasoning_message=_none,
        maybe_response_output_message=_none,
        maybe_function_tool_call_output=_maybe_fco,
    ):
        yield


# ── Helpers ─────────────────────────────────────────────────────────────

def _has_orphan_fco(messages: list) -> tuple[bool, str | None]:
    """Scan messages and report the first orphan fco (no preceding fc with same call_id)."""
    fc_ids: set[str] = set()
    for m in messages:
        if m.get("_type") == "assistant" and m.get("type") == "function_call":
            cid = m.get("call_id")
            if cid:
                fc_ids.add(cid)
        if m.get("_type") == "tool_result":
            cid = m.get("call_id")
            if cid and cid not in fc_ids:
                return True, cid
    return False, None


def _make_context(context_window: int = 200_000):
    """Mock ModelRunConfig with the bare minimum used by compact()."""
    cfg = MagicMock()
    cfg.context_window = context_window
    cfg.model_name = "gpt-4o-mini"
    cfg.provider = "openai_agents"
    return cfg


# ── The reproducer ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compact_breaks_parallel_tool_call_group_into_orphan_fco():
    """
    Given a conversation that ends with a parallel tool_call group of size 3,
    compact() should NOT produce orphan function_call_output entries in the
    final messages.

    Repro recipe (mirrors the real 400 from siada_cli.log on 2026-05-19):
      - Long history of paired fc/fco turns to push split point near the end.
      - Final turn = 3 fc + 3 fco (parallel_tool_calls=True).
      - Mock LLM summarization so we focus purely on the splitting logic.
    """
    strategy = SummarizeWithHeaderCompaction()

    # Build a long history of normal user → assistant fc → fco turns.
    messages: list = [_user_msg("<task>分析当前项目</task>")]
    for i in range(8):
        messages.extend([
            _assistant_fc(f"call_seq_{i}"),
            _tool_result_msg(f"call_seq_{i}", output=f"seq result {i} " + "x" * 200),
        ])
        messages.append(_user_msg(f"继续 step {i}"))

    # The last turn: model emits 3 parallel function_calls and 3 outputs.
    parallel_ids = ["call_IcSiy2yr1AZ", "call_Ckim7cUQe", "call_NtUAD0b3"]
    messages.extend([
        _reasoning_msg(),
        _output_msg("我并行读三个文件"),
        _assistant_fc(parallel_ids[0]),
        _assistant_fc(parallel_ids[1]),
        _assistant_fc(parallel_ids[2]),
        _tool_result_msg(parallel_ids[0], output="A " + "y" * 4000),
        _tool_result_msg(parallel_ids[1], output="B " + "y" * 4000),
        _tool_result_msg(parallel_ids[2], output="C " + "y" * 4000),
    ])

    context = _make_context()

    # 1) Mock LLM so call_llm_to_compact returns a plain text summary.
    # 2) Mock _count_tokens so the keep-budget fallback (which would call
    #    _trim_kept_history → _repair_tool_pairs and accidentally fix the
    #    orphan) does NOT trigger. We want to expose the raw split bug.
    with patch.object(
        SummarizeWithHeaderCompaction, "call_llm_to_compact",
        new=AsyncMock(return_value="<context>summary</context>"),
    ), patch.object(
        SummarizeWithHeaderCompaction, "_count_tokens", return_value=100,
    ):
        result = (await strategy.compact(context, messages, fixed_overhead_tokens=0)).messages

    has_orphan, orphan_id = _has_orphan_fco(result)

    # The current buggy implementation produces orphan fco entries in the
    # parallel-tool_call group → the assertion below fails, reproducing the
    # 400 from the live log:
    #   "No tool call found for function call output with call_id call_..."
    assert not has_orphan, (
        f"Found orphan function_call_output with call_id={orphan_id!r} in compacted "
        f"messages. Responses API will reject this with HTTP 400 "
        f"'No tool call found for function call output'.\n"
        f"Final messages summary:\n"
        + "\n".join(
            f"  {i:02d} type={(m.get('_type') or '?'):>11} "
            f"fc_id={(m.get('call_id') or '-'):>30} "
            f"role={m.get('role')!r}"
            for i, m in enumerate(result)
        )
    )


@pytest.mark.asyncio
async def test_compact_split_lands_inside_parallel_tool_call_group():
    """Stricter version: pin the split index so it deterministically lands
    inside the parallel tool-call group, demonstrating the snap-forward
    `break-after-function_response` bug.

    Sequence (last 6 items):
       fc_A, fc_B, fc_C, fco_A, fco_B, fco_C
    With find_index_after_fraction patched to return idx(fco_A), the snap
    loop advances 1 step then breaks (because messages[idx-1] is fco_A),
    producing:
       compress = [..., fc_A, fc_B, fc_C, fco_A]   ← summarized → call_ids lost
       keep    = [fco_B, fco_C]                    ← orphans
    """
    strategy = SummarizeWithHeaderCompaction()

    parallel_ids = ["call_IcSiy2yr1AZ", "call_Ckim7cUQe", "call_NtUAD0b3"]
    head = [
        _user_msg("<task>hello</task>"),
        _output_msg("ack"),                 # gives the header pair some shape
    ]
    parallel_block = [
        _assistant_fc(parallel_ids[0]),
        _assistant_fc(parallel_ids[1]),
        _assistant_fc(parallel_ids[2]),
        _tool_result_msg(parallel_ids[0]),  # fco_A
        _tool_result_msg(parallel_ids[1]),  # fco_B
        _tool_result_msg(parallel_ids[2]),  # fco_C
    ]
    messages = head + parallel_block

    fco_a_index = head.__len__() + 3  # idx of fco_A

    context = _make_context()

    with patch.object(
        SummarizeWithHeaderCompaction, "find_index_after_fraction",
        return_value=fco_a_index,
    ), patch.object(
        SummarizeWithHeaderCompaction, "call_llm_to_compact",
        new=AsyncMock(return_value="<context>summary</context>"),
    ), patch.object(
        SummarizeWithHeaderCompaction, "_count_tokens", return_value=100,
    ):
        result = (await strategy.compact(context, messages, fixed_overhead_tokens=0)).messages

    has_orphan, orphan_id = _has_orphan_fco(result)
    assert not has_orphan, (
        f"Split landed inside parallel tool-call group: orphan fco call_id={orphan_id!r}. "
        f"Result roles/types: "
        + ", ".join(f"{m.get('_type')}({m.get('call_id') or ''})" for m in result)
    )
