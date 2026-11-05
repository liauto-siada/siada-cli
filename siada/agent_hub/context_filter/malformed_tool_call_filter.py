"""Repair malformed tool-call arguments before they enter context/history.

Some models (notably lpai-glm-5.3) occasionally stream a tool call whose
``arguments`` is truncated or otherwise not valid JSON. The SDK records the
raw string without validation, the tool execution layer fails to parse it
(``ModelBehaviorError``) and emits an error ``function_call_output``, and the
poisoned ``function_call`` item settles into history. On every subsequent
request the item is replayed verbatim (``chatcmpl_converter`` only falls back
to ``"{}"`` for empty strings, not for invalid ones), the gateway hard-rejects
it with ``Assistant tool call function.arguments must be valid JSON`` (400),
and litellm retries the same deterministic payload — a session-level deadlock.

This filter scans the FULL input list on every model call, repairs invalid
``arguments`` (best-effort JSON completion, falling back to ``"{}"``), and
synthesizes a placeholder output for dangling calls, so the request leaving
the client always carries valid JSON. The original malformed payload is
written to disk for forensics (same offload pattern as
``tool_output_offload.py``).

Placed first in the filter chain so ``MessageHistoryCaptureFilter`` captures
the repaired form into the task message state and the persisted session
history self-heals on the next call.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, TYPE_CHECKING

from siada.foundation.logging import logger
from siada.utils import DirectoryUtils

if TYPE_CHECKING:
    from agents.run import ModelInputData
    from siada.foundation.code_agent_context import CodeAgentContext

_SAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")

# Keep repair scoped to the existing lpai family and explicitly selected
# models. Do not change history replay for unrelated providers or models.
_LPAI_MODEL_PREFIX = "lpai-"
_ARGUMENT_REPAIR_MODELS = frozenset({"baidu-deepseek-v4.1-flash"})


def is_lpai_model(model_name: str | None) -> bool:
    """True only for lpai-family model names (e.g. lpai-glm-5.3)."""
    return bool(model_name) and model_name.lower().startswith(_LPAI_MODEL_PREFIX)


def should_repair_tool_call_arguments(model_name: str | None) -> bool:
    """Select models that need malformed tool arguments repaired on replay."""
    return is_lpai_model(model_name) or bool(
        model_name and model_name.lower() in _ARGUMENT_REPAIR_MODELS
    )


def _sanitize_name(value: str) -> str:
    """Make an arbitrary id safe for use as a file name component."""
    return _SAFE_NAME_CHARS.sub("_", value)[:80]


def _is_valid_json(text: Any) -> bool:
    """True only for a str that parses as JSON. Non-strings are malformed."""
    if not isinstance(text, str):
        return False
    try:
        json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return False
    return True


def _repair_arguments(raw: Any) -> tuple[str, str]:
    """Best-effort repair of a malformed arguments string.

    Returns ``(repaired_arguments, method)`` where method is
    ``"ensure_json"`` (truncated JSON completed) or ``"empty"`` (fallback).
    """
    if isinstance(raw, str) and raw.strip():
        try:
            from partial_json_parser import ensure_json

            completed = ensure_json(raw)
            if _is_valid_json(completed) and isinstance(
                json.loads(completed), dict
            ):
                return completed, "ensure_json"
        except Exception:  # noqa: BLE001 - any parser failure falls through
            pass
    return "{}", "empty"


def _write_payload(
    offload_dir: Path, call_id: str | None, tool_name: str, raw: str
) -> Path | None:
    """Write the original malformed payload to disk (idempotent per content)."""
    try:
        digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:8]
        name = _sanitize_name(call_id) if call_id else f"args_{digest}"
        path = offload_dir / f"{name}_{digest}.txt"
        header = (
            f"# malformed tool-call arguments\n"
            f"# tool={tool_name} call_id={call_id} original_chars={len(raw)}\n"
        )
        text = header + raw
        size = len(text.encode("utf-8", errors="replace"))
        if path.exists() and path.stat().st_size == size:
            return path
        offload_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path
    except OSError as e:
        logger.warning(f"[MalformedToolCall] failed to write offload file: {e}")
        return None


def _get_attr(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _is_function_call(item: Any) -> bool:
    return _get_attr(item, "type") == "function_call"


def sanitize_malformed_tool_calls(
    items: list, offload_dir: Path | None
) -> tuple[list, int]:
    """Repair function_call items whose arguments are not valid JSON.

    Also synthesizes a placeholder ``function_call_output`` for a repaired
    call that has no matching output (dangling call), keeping the
    call/output pairing the gateway requires.

    Args:
        items: model input items (Responses API shapes).
        offload_dir: directory for the raw payload evidence; when None the
            raw payload is not saved (placeholder says so).

    Returns:
        ``(new_items, repaired_call_ids)`` — the input list is never mutated;
        untouched items are returned by reference.
    """
    output_call_ids = {
        _get_attr(item, "call_id")
        for item in items
        if _get_attr(item, "type") == "function_call_output"
    }

    new_items: list = []
    repaired_call_ids: list[str] = []
    for item in items:
        if not _is_function_call(item):
            new_items.append(item)
            continue

        arguments = _get_attr(item, "arguments")
        if _is_valid_json(arguments):
            new_items.append(item)
            continue

        call_id = _get_attr(item, "call_id")
        tool_name = _get_attr(item, "name") or "unknown"
        raw = arguments if isinstance(arguments, str) else str(arguments)

        path = (
            _write_payload(offload_dir, call_id, tool_name, raw)
            if offload_dir is not None
            else None
        )
        repaired, method = _repair_arguments(arguments)

        # Copy semantics: never mutate the original item in place.
        if isinstance(item, dict):
            new_item = dict(item)
            new_item["arguments"] = repaired
        else:
            try:
                new_item = item.model_copy(update={"arguments": repaired})
            except Exception:  # noqa: BLE001 - unexpected shape; keep item
                new_item = item
        new_items.append(new_item)
        repaired_call_ids.append(str(call_id) if call_id else "")

        logger.debug(
            "[MalformedToolCall] repaired tool_call name=%s call_id=%s "
            "method=%s original_chars=%d raw_saved_to=%s",
            tool_name, call_id, method, len(raw),
            path if path is not None else "(not saved)",
        )

        if call_id and call_id not in output_call_ids:
            if path is not None:
                note = (
                    f"[Tool call dropped: model returned invalid JSON "
                    f"arguments. Raw arguments saved to: {path}]"
                )
            else:
                note = (
                    "[Tool call dropped: model returned invalid JSON "
                    "arguments. Raw arguments were NOT saved "
                    "(no writable directory).]"
                )
            new_items.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": note,
                }
            )

    return new_items, repaired_call_ids


def _resolve_offload_dir(context: "CodeAgentContext") -> Path | None:
    """Per-project offload dir: <siada tmp>/<project_hash>/tool_call_args/<session>."""
    root_dir = getattr(context, "root_dir", None)
    if not root_dir:
        return None
    session_id = getattr(context, "session_id", None) or "unknown"
    try:
        base = DirectoryUtils.get_project_temp_dir(root_dir)
        return Path(base) / "tool_call_args" / _sanitize_name(str(session_id))
    except Exception as e:  # noqa: BLE001 - never break the LLM call on dir setup
        logger.warning(f"[MalformedToolCall] failed to resolve offload dir: {e}")
        return None


class MalformedToolCallFilter:
    """Context filter: repair malformed function_call arguments in-place.

    Placed first in the filter chain so the repaired form is what
    ``MessageHistoryCaptureFilter`` captures and ``ApiMessageTransferFilter``
    compacts/persists — poisoned sessions self-heal on the next LLM call.
    """

    def __init__(self) -> None:
        # The filter chain works on a deepcopy, so the SDK's in-flight input
        # stays dirty and the same poisoned call is repaired on every request.
        # Log the first repair per call_id at WARNING, repeats at DEBUG.
        self._seen_call_ids: set[str] = set()

    async def filter(
        self, model_data: "ModelInputData", agent: Any, context: "CodeAgentContext"
    ) -> None:
        try:
            model_name = getattr(
                getattr(context, "model_run_config", None), "model_name", None
            )
            if not should_repair_tool_call_arguments(model_name):
                return
            items = model_data.input
            if not isinstance(items, list) or not items:
                return

            offload_dir = _resolve_offload_dir(context)
            new_items, repaired_ids = sanitize_malformed_tool_calls(items, offload_dir)
            if repaired_ids:
                model_data.input = new_items
                new_ids = set(repaired_ids) - self._seen_call_ids
                msg = "[MalformedToolCall] repaired %d malformed tool call(s)"
                if new_ids:
                    logger.warning(msg, len(repaired_ids))
                else:
                    logger.debug(msg, len(repaired_ids))
                self._seen_call_ids.update(repaired_ids)
        except Exception as e:  # noqa: BLE001 - never break the LLM call
            logger.warning(f"[MalformedToolCall] filter error, input untouched: {e}")
