"""Unit tests for ToolOutputOffloadFilter / offload_oversized_tool_outputs."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from siada.agent_hub.context_filter.tool_output_offload import (
    OFFLOAD_THRESHOLD_CHARS,
    PREVIEW_HEAD_CHARS,
    PREVIEW_TAIL_CHARS,
    ToolOutputOffloadFilter,
    offload_oversized_tool_outputs,
)


def _fco_str(call_id: str, output: str) -> dict:
    return {"type": "function_call_output", "call_id": call_id, "output": output}


def _fco_list(call_id: str, blocks: list) -> dict:
    return {"type": "function_call_output", "call_id": call_id, "output": blocks}


def _big_text(n: int = OFFLOAD_THRESHOLD_CHARS + 10_000) -> str:
    return "x" * n


# ── str-shaped output ────────────────────────────────────────────────


def test_small_output_untouched(tmp_path: Path):
    items = [_fco_str("c1", "small result")]
    new_items, count = offload_oversized_tool_outputs(items, tmp_path)
    assert count == 0
    assert new_items[0] is items[0]  # returned by reference, no copy
    assert list(tmp_path.iterdir()) == []


def test_oversized_str_output_offloaded(tmp_path: Path):
    text = _big_text()
    items = [_fco_str("call_1", text)]
    new_items, count = offload_oversized_tool_outputs(items, tmp_path)

    assert count == 1
    assert new_items[0] is not items[0]  # replaced, original untouched
    assert items[0]["output"] == text

    placeholder = new_items[0]["output"]
    assert isinstance(placeholder, str)
    assert "truncated" in placeholder
    assert f"{len(text):,}" in placeholder
    assert "HEAD PREVIEW" in placeholder
    assert "TAIL PREVIEW" in placeholder
    # placeholder is much smaller than the original
    assert len(placeholder) < PREVIEW_HEAD_CHARS + PREVIEW_TAIL_CHARS + 2_000

    # full payload written to disk, referenced in the placeholder
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("call_1_")
    assert files[0].read_text(encoding="utf-8") == text
    assert str(files[0]) in placeholder


def test_head_and_tail_preview_content(tmp_path: Path):
    middle_len = OFFLOAD_THRESHOLD_CHARS - PREVIEW_HEAD_CHARS - PREVIEW_TAIL_CHARS + 1
    text = "A" * PREVIEW_HEAD_CHARS + "M" * middle_len + "Z" * PREVIEW_TAIL_CHARS
    items = [_fco_str("c", text)]
    new_items, count = offload_oversized_tool_outputs(items, tmp_path)
    assert count == 1
    placeholder = new_items[0]["output"]
    assert "A" * 100 in placeholder  # head kept
    assert "Z" * 100 in placeholder  # tail kept
    assert "M" * middle_len not in placeholder  # middle dropped


def test_idempotent_rewrite_skipped(tmp_path: Path):
    text = _big_text()
    items = [_fco_str("call_1", text)]
    offload_oversized_tool_outputs(items, tmp_path)
    path = next(tmp_path.iterdir())
    mtime = path.stat().st_mtime_ns
    # Second pass with the same content must not rewrite the file
    offload_oversized_tool_outputs(items, tmp_path)
    assert path.stat().st_mtime_ns == mtime


# ── list-shaped output (MCP content blocks) ──────────────────────────


def test_oversized_list_output_preserves_images(tmp_path: Path):
    text = _big_text()
    blocks = [
        {"type": "input_text", "text": text},
        {"type": "input_image", "image_url": "data:image/png;base64,AAAA"},
    ]
    items = [_fco_list("call_2", blocks)]
    new_items, count = offload_oversized_tool_outputs(items, tmp_path)

    assert count == 1
    new_output = new_items[0]["output"]
    assert isinstance(new_output, list)
    # placeholder keeps the original block type, image preserved
    assert new_output[0]["type"] == "input_text"
    assert "truncated" in new_output[0]["text"]
    assert new_output[1] == blocks[1]
    assert next(tmp_path.iterdir()).read_text(encoding="utf-8") == text


def test_list_output_multiple_text_blocks(tmp_path: Path):
    blocks = [
        {"type": "text", "text": "a" * 30_000},
        {"type": "text", "text": "b" * 30_000},
    ]
    items = [_fco_list("c3", blocks)]
    new_items, count = offload_oversized_tool_outputs(items, tmp_path)
    assert count == 1
    payload = next(tmp_path.iterdir()).read_text(encoding="utf-8")
    assert payload == "a" * 30_000 + "\n" + "b" * 30_000


# ── non-tool items and edge cases ────────────────────────────────────


def test_non_tool_items_pass_through(tmp_path: Path):
    items = [
        {"role": "user", "content": _big_text()},  # big user msg: not our job
        {"type": "function_call", "call_id": "c", "name": "t", "arguments": "{}"},
        _fco_str("c", "ok"),
    ]
    new_items, count = offload_oversized_tool_outputs(items, tmp_path)
    assert count == 0
    assert new_items == items
    assert list(tmp_path.iterdir()) == []


def test_no_call_id_still_offloads(tmp_path: Path):
    items = [{"type": "function_call_output", "output": _big_text()}]
    new_items, count = offload_oversized_tool_outputs(items, tmp_path)
    assert count == 1
    files = list(tmp_path.iterdir())
    assert len(files) == 1
    assert files[0].name.startswith("output_")


def test_inline_truncation_when_no_dir():
    items = [_fco_str("c1", _big_text())]
    new_items, count = offload_oversized_tool_outputs(items, None)
    assert count == 1
    placeholder = new_items[0]["output"]
    assert "truncated" in placeholder
    assert "NOT saved" in placeholder


def test_call_id_sanitized_for_filename(tmp_path: Path):
    items = [_fco_str("call/with:bad chars", _big_text())]
    new_items, count = offload_oversized_tool_outputs(items, tmp_path)
    assert count == 1
    name = next(tmp_path.iterdir()).name
    assert "/" not in name and ":" not in name


def test_object_shaped_item(tmp_path: Path):
    item = SimpleNamespace(
        type="function_call_output", call_id="obj1", output=_big_text()
    )
    new_items, count = offload_oversized_tool_outputs([item], tmp_path)
    assert count == 1
    assert "truncated" in new_items[0].output


# ── filter class ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_replaces_model_input(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "siada.agent_hub.context_filter.tool_output_offload.DirectoryUtils.get_project_temp_dir",
        staticmethod(lambda root: str(tmp_path)),
    )
    text = _big_text()
    model_data = SimpleNamespace(input=[_fco_str("fc1", text)])
    context = SimpleNamespace(root_dir="/any", session_id="sess1")

    await ToolOutputOffloadFilter().filter(model_data, agent=None, context=context)

    assert "truncated" in model_data.input[0]["output"]
    written = list(tmp_path.rglob("*.txt"))
    assert len(written) == 1
    assert written[0].read_text(encoding="utf-8") == text
    assert "sess1" in str(written[0])


@pytest.mark.asyncio
async def test_filter_noop_on_small_inputs(tmp_path: Path):
    model_data = SimpleNamespace(input=[_fco_str("fc1", "ok")])
    context = SimpleNamespace(root_dir=None, session_id=None)
    await ToolOutputOffloadFilter().filter(model_data, agent=None, context=context)
    assert model_data.input[0]["output"] == "ok"


@pytest.mark.asyncio
async def test_filter_handles_non_list_input():
    model_data = SimpleNamespace(input="just a string")
    context = SimpleNamespace(root_dir=None, session_id=None)
    await ToolOutputOffloadFilter().filter(model_data, agent=None, context=context)
    assert model_data.input == "just a string"


@pytest.mark.asyncio
async def test_filter_falls_back_to_inline_truncation_without_root_dir():
    model_data = SimpleNamespace(input=[_fco_str("fc1", _big_text())])
    context = SimpleNamespace(root_dir=None, session_id="s")
    await ToolOutputOffloadFilter().filter(model_data, agent=None, context=context)
    assert "NOT saved" in model_data.input[0]["output"]
