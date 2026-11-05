"""End-to-end regression: oversized MCP tool outputs must be capped before the
model call.

Reproduces the siada production failure of 2026-09-15 (acp/agent logs):

    Turn execution error: BadRequestError: litellm.BadRequestError: OpenAIException
      - The input (2099088 tokens) is longer than the model's context length
        (1048576 tokens)
    Compaction failed, using uncompacted messages: Compaction failed:
      litellm.BadRequestError: MoonshotException - Exceeded limit on max bytes to
      request body : 6291456

An MCP tool returned ~7.58M chars in a single ``function_call_output``. Nothing
in the context filter chain capped it, so the request exceeded both hard limits
(gateway body limit + model context window) and every subsequent LLM call 400'd:
compaction cannot shrink a single oversized message (trimming is
message-granularity) and its own summarize request hits the same body limit.

These tests drive the REAL chain entrypoint (``context_capture_filter``) with
the real capture/transfer filters and assert that the oversized output is
replaced by a small placeholder + offload file BEFORE the model sees it, and
that the capped placeholder — not the raw payload — is what enters the task
message state.

Only two things are stubbed (both offline/test-only):
  * ``calculate_tokens`` — litellm's counter tries to fetch tiktoken BPE files
    over the network and hangs ~200s per call in this environment; replaced
    with a chars/4 estimate (production ratio was ~3.6 chars/token, so this is
    conservative).
  * the compaction summarize LLM call — no network in unit tests.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from siada.agent_hub.context_filter.compaction_strategy import CompactionStrategy
from siada.agent_hub.context_filter.tool_output_offload import (
    OFFLOAD_THRESHOLD_CHARS,
    ToolOutputOffloadFilter,
)
from siada.models.model_run_config import ModelRunConfig
from siada.session.task_message_state import TaskMessageState

# Hard limits from the production 400s.
GATEWAY_BODY_LIMIT_BYTES = 6_291_456  # "Exceeded limit ... request body : 6291456"
MODEL_CONTEXT_WINDOW = 1_048_576  # "context length (1048576 tokens)"
GIANT_MCP_OUTPUT_CHARS = 7_580_000  # the MCP output size that triggered the 400s

# NOTE: the package ``__init__`` re-exports a *function* named
# ``context_capture_filter`` that shadows the module attribute lookup, hence
# importlib for the module.
ccf_mod = importlib.import_module(
    "siada.agent_hub.context_filter.context_capture_filter"
)
atf_mod = importlib.import_module(
    "siada.agent_hub.context_filter.api_message_transfer_filter"
)
cs_mod = importlib.import_module("siada.agent_hub.context_filter.compaction_strategy")


def _fast_calculate_tokens(model_name, messages_or_text, *, tools=None):
    """Offline stand-in for ``utils.calculate_tokens`` (see module docstring)."""
    if isinstance(messages_or_text, str):
        return len(messages_or_text) // 4
    total = 0
    for item in messages_or_text:
        if isinstance(item, dict):
            for key in ("content", "output", "text"):
                value = item.get(key)
                if isinstance(value, str):
                    total += len(value)
                elif isinstance(value, list):
                    for block in value:
                        if isinstance(block, dict) and isinstance(
                            block.get("text"), str
                        ):
                            total += len(block["text"])
        elif isinstance(item, str):
            total += len(item)
    return total // 4


def _giant_output(size: int = GIANT_MCP_OUTPUT_CHARS) -> str:
    """Deterministic oversized MCP output with recognizable head and tail."""
    head = "<<<HEAD-MARKER>>>"
    tail = "<<<TAIL-MARKER>>>"
    return head + "x" * (size - len(head) - len(tail)) + tail


def _mcp_items(output: str) -> list:
    """A Responses-API item stream ending in one MCP function_call_output."""
    return [
        {"role": "user", "content": "分析这段哨兵日志并总结高风险事件"},
        {
            "type": "function_call",
            "call_id": "call_mcp_1",
            "name": "wo_kb_search",
            "arguments": "{}",
        },
        {"type": "function_call_output", "call_id": "call_mcp_1", "output": output},
    ]


def _body_bytes(items) -> int:
    return len(json.dumps(items, ensure_ascii=False).encode("utf-8"))


def _make_context(tmp_root: Path):
    ctx = MagicMock()
    ctx.root_dir = str(tmp_root)
    ctx.session_id = "test-mcp-oversized-output"
    ctx.auto_compact = True
    ctx.compaction_strategy_name = None
    ctx.im_mode = False
    ctx.task_message_state = TaskMessageState(task_id="test")
    ctx.session.state.task_message_state = ctx.task_message_state
    ctx.session.state.usage = None
    ctx.session.state.cache_status_state = {}
    ctx.session.session_id = ctx.session_id
    ctx.model_run_config = ModelRunConfig("lpai-glm-5.3")
    return ctx


async def _run_chain(items, tmp_root: Path):
    """Run the real filter chain over ``items``; returns (model input, context)."""
    ctx = _make_context(tmp_root)
    data = MagicMock()
    data.model_data.input = list(items)
    data.model_data.instructions = "You are Siada."
    data.agent = MagicMock()
    data.agent.tools = None
    data.context = ctx

    async def _fake_summarize(self, model_run_config, history_to_compact):
        return "SUMMARY: stubbed"

    with patch.object(
        CompactionStrategy, "call_llm_to_compact", _fake_summarize
    ), patch.object(
        atf_mod, "calculate_tokens", _fast_calculate_tokens
    ), patch.object(
        cs_mod, "calculate_tokens", _fast_calculate_tokens
    ), patch(
        "siada.services.memory.memory_update.get_memory_scheduler",
        lambda session_id: None,
    ):
        result = await ccf_mod.context_capture_filter(data)
    return result.input, ctx


@pytest.fixture
def offload_to_tmp(tmp_path, monkeypatch):
    """Redirect all siada temp/session dirs into the test's tmp_path."""
    monkeypatch.setattr(
        "siada.agent_hub.context_filter.tool_output_offload."
        "DirectoryUtils.get_project_temp_dir",
        staticmethod(lambda root: str(tmp_path)),
    )
    return tmp_path


def _find_tool_output(items) -> str:
    for item in items:
        if isinstance(item, dict) and item.get("type") == "function_call_output":
            return item.get("output")
    raise AssertionError("no function_call_output in result")


# ── the reproduction ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oversized_mcp_output_is_capped_before_model_call(
    offload_to_tmp, monkeypatch
):
    """7.58M-char MCP output must not reach the model verbatim.

    Before the fix this fails: the output survives the chain unchanged, the
    request body is 7,580,249 bytes (> 6,291,456 gateway limit) and ~1.9M
    tokens (> 1,048,576 context window) — exactly the two production 400s.
    """
    giant = _giant_output()
    final, _ = await _run_chain(_mcp_items(giant), offload_to_tmp)

    output = _find_tool_output(final)
    # 1. The raw payload is gone from the model-bound input.
    assert len(output) < OFFLOAD_THRESHOLD_CHARS
    assert len(output) < len(giant) / 10
    # 2. Head/tail previews are preserved inline, with reading guidance.
    assert "<<<HEAD-MARKER>>>" in output
    assert "<<<TAIL-MARKER>>>" in output
    assert f"{len(giant):,} chars" in output
    # 3. The full output is recoverable from disk, verbatim.
    offload_files = list(Path(offload_to_tmp).rglob("*.txt"))
    assert len(offload_files) == 1
    assert offload_files[0].read_text(encoding="utf-8") == giant
    assert str(offload_files[0]) in output
    # 4. Both hard limits that produced the production 400s are respected.
    body = _body_bytes(final)
    assert body < GATEWAY_BODY_LIMIT_BYTES, f"request body {body:,} bytes"
    tokens = _fast_calculate_tokens(None, final)
    assert tokens < MODEL_CONTEXT_WINDOW, f"request tokens {tokens:,}"


@pytest.mark.asyncio
async def test_capped_placeholder_is_what_enters_task_message_state(
    offload_to_tmp, monkeypatch
):
    """The placeholder (not the raw payload) must be captured into history.

    This is the placement contract: the offload filter has to run BEFORE
    MessageHistoryCaptureFilter, otherwise token counting / compaction keep
    seeing the oversized payload on every LLM call.
    """
    giant = _giant_output()
    _, ctx = await _run_chain(_mcp_items(giant), offload_to_tmp)

    captured = ctx.task_message_state.get_messages()
    captured_output = _find_tool_output(captured)
    assert len(captured_output) < OFFLOAD_THRESHOLD_CHARS
    assert giant not in captured_output


@pytest.mark.asyncio
async def test_normal_sized_tool_output_is_untouched(offload_to_tmp):
    """Ordinary tool outputs (the overwhelming majority) pass through as-is."""
    normal = "run_cmd: 42 tests passed in 1.23s"
    final, _ = await _run_chain(_mcp_items(normal), offload_to_tmp)

    assert _find_tool_output(final) == normal
    assert list(Path(offload_to_tmp).rglob("*.txt")) == []


# ── chain wiring ─────────────────────────────────────────────────────


def test_offload_filter_is_registered_first_in_chain():
    """It must be mounted FIRST, before MessageHistoryCaptureFilter."""
    with patch.object(ccf_mod, "_CONTEXT_FILTERS", None):
        filters = ccf_mod.get_context_filters()

    names = [type(f).__name__ for f in filters]
    assert "ToolOutputOffloadFilter" in names
    assert names.index("ToolOutputOffloadFilter") < names.index(
        "MessageHistoryCaptureFilter"
    )
    assert isinstance(filters[0], ToolOutputOffloadFilter)
