"""Cross-protocol replay helpers for Responses-only item shapes.

Session history carries a few item shapes that the native Responses protocol
accepts but the ChatCompletions converter cannot parse.  Replaying such
history through a chat-completions model (model switch mid-session, a forked
sub-agent on another model, the compaction summarization call, token
counting) therefore raised ``UserError`` and broke the request:

1. Native ``apply_patch`` items (``apply_patch_call`` /
   ``apply_patch_call_output``) -- no ChatCompletions representation at all.
2. Id-less assistant output messages, i.e.
   ``{"type": "message", "role": "assistant", "content": [{"type":
   "output_text", ...}]}`` without an ``id`` -- the shape produced by the
   compaction acknowledgment messages.  The SDK's
   ``maybe_response_output_message`` requires an ``id`` (the real Responses
   API always mints one), so these items fall into the EasyInputMessage
   branch, whose content parser rejects ``output_text`` parts.

``to_chat_compatible_items`` rewrites those shapes into lossless,
chat-completions-safe proxies (``function_call`` named ``apply_patch`` plus a
matching ``function_call_output``; a plain assistant text message) so any
ChatCompletions consumer can carry them.  Session history itself is never
rewritten: callers apply this only at the protocol boundary (wire conversion
/ token counting), keeping storage on the native protocol.
"""
from __future__ import annotations

import json
from typing import Any

NATIVE_PATCH_CALL = "apply_patch_call"
NATIVE_PATCH_CALL_OUTPUT = "apply_patch_call_output"

_NATIVE_PATCH_TYPES = frozenset({NATIVE_PATCH_CALL, NATIVE_PATCH_CALL_OUTPUT})

# Tool name used by the function-call proxy. Kept identical to the native tool
# name so transcripts stay recognizable, and so the shape matches the payload
# the Agents SDK parses for its own ``function_call``-named-``apply_patch``
# fallback (``{"operation": ...}`` / ``{"operations": ...}``).
PROXY_TOOL_NAME = "apply_patch"


def item_type_of(item: Any) -> str | None:
    """Return the Responses ``type`` field of a dict/object item, if any."""
    value = item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
    return value if isinstance(value, str) else None


def _read_field(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _jsonable(value: Any) -> Any:
    """Best-effort conversion of pydantic models into JSON-compatible data."""
    if hasattr(value, "model_dump"):
        try:
            return value.model_dump(exclude_unset=True)
        except Exception:
            return str(value)
    return value


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _output_text_parts(item: Any) -> list[str]:
    """Collect the texts of an item's ``output_text`` content parts."""
    content = _read_field(item, "content")
    if not isinstance(content, list):
        return []
    texts: list[str] = []
    for part in content:
        if _read_field(part, "type") != "output_text":
            continue
        text = _read_field(part, "text")
        if isinstance(text, str):
            texts.append(text)
    return texts


def _needs_easy_input_rewrite(item: Any) -> bool:
    """Whether an assistant message item would break the converter.

    ``Converter.maybe_response_output_message`` requires ``{"id", "content"}``
    on a ``type == "message"`` item; without an ``id`` the item is claimed by
    the EasyInputMessage branch instead, where ``output_text`` content parts
    are invalid ("Unknown content: ...").
    """
    if item_type_of(item) != "message":
        return False
    if _read_field(item, "role") != "assistant":
        return False
    if _read_field(item, "id"):
        return False
    return bool(_output_text_parts(item))


def to_chat_compatible_item(item: Any) -> Any:
    """Return a ChatCompletions-shaped proxy for a Responses-only item shape.

    Handles both replayed shapes (native apply_patch items, id-less assistant
    output messages).  Anything else is returned unchanged (same object), so
    callers can use this per item without disturbing the rest of the history.

    For apply_patch items, ``call_id`` is preserved in both directions -- it
    is the pairing key, not a store id -- while output-only metadata (``id`` /
    ``status`` / ``caller`` / ``created_by``) is intentionally dropped.
    """
    item_type = item_type_of(item)

    if item_type in _NATIVE_PATCH_TYPES:
        call_id = _read_field(item, "call_id") or _read_field(item, "id") or ""

        if item_type == NATIVE_PATCH_CALL:
            payload: dict[str, Any] = {}
            operation = _read_field(item, "operation")
            if operation is not None:
                payload["operation"] = _jsonable(operation)
            operations = _read_field(item, "operations")
            if operations is not None:
                payload["operations"] = _jsonable(operations)
            return {
                "type": "function_call",
                "call_id": call_id,
                "name": PROXY_TOOL_NAME,
                "arguments": _dump_json(payload),
            }

        output = _read_field(item, "output", "")
        if not isinstance(output, str):
            output = _dump_json(_jsonable(output))
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": output,
        }

    if _needs_easy_input_rewrite(item):
        # ``type`` is kept so downstream classifiers keep seeing an assistant
        # message; the SDK joins output_text segments with newlines, and a
        # string-content assistant message is a valid EasyInputMessage for both
        # the converter and the Responses input schema.
        return {
            "type": "message",
            "role": "assistant",
            "content": "\n".join(_output_text_parts(item)),
        }

    return item


def to_chat_compatible_items(items: Any) -> Any:
    """Rewrite Responses-only item shapes in ``items`` for chat-completions use.

    Accepts any value.  Non-list inputs, and lists without any item that needs
    rewriting, are returned unchanged (same object) so the common path costs a
    single scan and never copies.  The input list is never mutated; a new list
    is returned whenever anything actually needed rewriting.
    """
    if not isinstance(items, list) or not items:
        return items

    if not any(
        item_type_of(item) in _NATIVE_PATCH_TYPES or _needs_easy_input_rewrite(item)
        for item in items
    ):
        return items

    return [to_chat_compatible_item(item) for item in items]