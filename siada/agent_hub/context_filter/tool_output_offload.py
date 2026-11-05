"""Offload oversized tool outputs to disk before they enter context/history.

A single tool result (e.g. a ``browser_read`` DOM snapshot from an MCP
browser tool) can be millions of characters — several hundred thousand
tokens. Left unbounded, one such message can fill the context window on its
own and makes compaction fail ("No messages to keep after trimming"), because
trimming works at message granularity and cannot shrink a single oversized
message.

This filter runs before ``MessageHistoryCaptureFilter`` so the small
*offloaded* placeholder is what gets captured into the task message state and
persisted to the session file — the oversized payload never enters history at
all. The full payload is written to the project's siada temp dir and the
placeholder tells the model how to read it selectively.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, TYPE_CHECKING

from siada.foundation.logging import logger
from siada.utils import DirectoryUtils

if TYPE_CHECKING:
    from agents.run import ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext

# A tool output longer than this (in characters) is offloaded to disk.
# 50k chars ≈ 12-15k tokens — generous enough for ordinary command output,
# small enough that several such messages cannot fill the context window.
OFFLOAD_THRESHOLD_CHARS = 50_000

# How much of the original content stays inline as a preview.
PREVIEW_HEAD_CHARS = 8_000
PREVIEW_TAIL_CHARS = 4_000

# Content-block ``type`` values that carry plain text in a list-shaped output.
_TEXT_BLOCK_TYPES = frozenset({"text", "input_text", "output_text"})

_SAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def _sanitize_name(value: str) -> str:
    """Make an arbitrary id safe for use as a file name component."""
    return _SAFE_NAME_CHARS.sub("_", value)[:80]


def _is_function_call_output(item: Any) -> bool:
    if isinstance(item, dict):
        return item.get("type") == "function_call_output"
    return getattr(item, "type", None) == "function_call_output"


def _collect_text(output: Any) -> tuple[str, str] | tuple[None, None]:
    """Extract the full text of a tool output.

    Returns ``(text, shape)`` where shape is ``"str"`` or ``"list"``, or
    ``(None, None)`` when the output has no text we can offload.
    """
    if isinstance(output, str):
        return output, "str"
    if isinstance(output, list):
        parts: list[str] = []
        for block in output:
            text = _block_text(block)
            if text is not None:
                parts.append(text)
        if parts:
            return "\n".join(parts), "list"
    return None, None


def _block_text(block: Any) -> str | None:
    """Return the text of a content block, or None for non-text blocks."""
    if isinstance(block, dict):
        if block.get("type") in _TEXT_BLOCK_TYPES and isinstance(
            block.get("text"), str
        ):
            return block["text"]
        return None
    if getattr(block, "type", None) in _TEXT_BLOCK_TYPES:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            return text
    return None


def _first_text_block_type(output: list) -> str:
    """Type to reuse for the placeholder block, preserving the original shape."""
    for block in output:
        if isinstance(block, dict) and block.get("type") in _TEXT_BLOCK_TYPES:
            return block["type"]
        block_type = getattr(block, "type", None)
        if block_type in _TEXT_BLOCK_TYPES:
            return block_type
    return "input_text"


def _build_placeholder(full_text: str, path: Path | None) -> str:
    total = len(full_text)
    head = full_text[:PREVIEW_HEAD_CHARS]
    tail = full_text[-PREVIEW_TAIL_CHARS:] if total > PREVIEW_HEAD_CHARS else ""
    if path is not None:
        location = f"Full output saved to: {path}"
        guidance = (
            "To inspect the full content, read that file selectively — e.g. "
            "search keywords with regex_search_files, or view a line range via "
            f"run_cmd (sed -n '1,200p' \"{path}\")."
        )
    else:
        location = "Full output was NOT saved (no writable directory)."
        guidance = ""
    return (
        f"[Tool output too large: {total:,} chars — truncated]\n"
        f"{location}\n"
        f"{guidance}\n\n"
        f"--- BEGIN HEAD PREVIEW (first {PREVIEW_HEAD_CHARS:,} chars) ---\n"
        f"{head}\n"
        f"--- END HEAD PREVIEW ---\n\n"
        f"--- BEGIN TAIL PREVIEW (last {PREVIEW_TAIL_CHARS:,} chars) ---\n"
        f"{tail}\n"
        f"--- END TAIL PREVIEW ---"
    )


def _write_payload(offload_dir: Path, call_id: str | None, text: str) -> Path | None:
    """Write the full payload to disk (idempotent per identical content)."""
    try:
        digest = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:8]
        name = _sanitize_name(call_id) if call_id else f"output_{digest}"
        path = offload_dir / f"{name}_{digest}.txt"
        size = len(text.encode("utf-8", errors="replace"))
        if path.exists() and path.stat().st_size == size:
            return path
        offload_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
    except OSError as e:
        logger.warning(f"[ToolOutputOffload] failed to write offload file: {e}")
        return None


def _get_call_id(item: Any) -> str | None:
    if isinstance(item, dict):
        call_id = item.get("call_id")
    else:
        call_id = getattr(item, "call_id", None)
    return str(call_id) if call_id else None


def _replace_output(item: Any, new_output: Any) -> Any:
    """Return a copy of the function_call_output item with its output replaced."""
    if isinstance(item, dict):
        new_item = dict(item)
        new_item["output"] = new_output
        return new_item
    try:
        item.output = new_output
    except Exception:  # noqa: BLE001 - read-only attribute; leave item as-is
        pass
    return item


def _resolve_offload_dir(context: "CodeAgentContext") -> Path | None:
    """Per-project offload directory: <siada tmp>/<project_hash>/tool_outputs/<session>."""
    root_dir = getattr(context, "root_dir", None)
    if not root_dir:
        return None
    session_id = getattr(context, "session_id", None) or "unknown"
    try:
        base = DirectoryUtils.get_project_temp_dir(root_dir)
        return Path(base) / "tool_outputs" / _sanitize_name(str(session_id))
    except Exception as e:  # noqa: BLE001 - never break the LLM call on dir setup
        logger.warning(f"[ToolOutputOffload] failed to resolve offload dir: {e}")
        return None


def offload_oversized_tool_outputs(
    items: list, offload_dir: Path | None
) -> tuple[list, int]:
    """Offload oversized function_call_output payloads to ``offload_dir``.

    Args:
        items: model input items (Responses API shapes).
        offload_dir: directory to write payloads to; when None the payload is
            truncated inline (head+tail preview) without writing a file.

    Returns:
        ``(new_items, offload_count)`` — the input list is never mutated;
        unchanged items are returned by reference.
    """
    new_items: list = []
    offloaded = 0
    for item in items:
        if not _is_function_call_output(item):
            new_items.append(item)
            continue
        output = item.get("output") if isinstance(item, dict) else getattr(
            item, "output", None
        )
        full_text, shape = _collect_text(output)
        if full_text is None or len(full_text) <= OFFLOAD_THRESHOLD_CHARS:
            new_items.append(item)
            continue

        path = (
            _write_payload(offload_dir, _get_call_id(item), full_text)
            if offload_dir is not None
            else None
        )
        placeholder = _build_placeholder(full_text, path)
        if shape == "list":
            block_type = _first_text_block_type(output)
            kept_blocks = [b for b in output if _block_text(b) is None]
            new_output = [{"type": block_type, "text": placeholder}, *kept_blocks]
        else:
            new_output = placeholder
        new_items.append(_replace_output(item, new_output))
        offloaded += 1
    return new_items, offloaded


class ToolOutputOffloadFilter:
    """Context filter: offload oversized tool outputs before history capture.

    Placed first in the filter chain so ``MessageHistoryCaptureFilter``
    captures the small placeholder into the task message state (and thus the
    persisted session history) instead of the raw oversized payload.
    """

    async def filter(
        self, model_data: "ModelInputData", agent: Any, context: "CodeAgentContext"
    ) -> None:
        items = model_data.input
        if not isinstance(items, list) or not items:
            return

        try:
            offload_dir = _resolve_offload_dir(context)
            new_items, count = offload_oversized_tool_outputs(items, offload_dir)
        except Exception as e:  # noqa: BLE001 - never break the LLM call
            # Leaving the input untouched degrades to the pre-fix behaviour
            # (downstream compaction handles it as before); raising here would
            # abort the whole filter chain in ``context_capture_filter``.
            logger.warning(f"[ToolOutputOffload] offload pass failed: {e}")
            return

        if count:
            model_data.input = new_items
            logger.info(
                "[ToolOutputOffload] offloaded %d oversized tool output(s) to %s",
                count,
                offload_dir if offload_dir is not None else "(inline truncation)",
            )
