from __future__ import annotations

import json
from typing import Any

from agents.exceptions import UserError

from siada.support.chat_compat_items import to_chat_compatible_item


REPLAY_VERSION = 2
MISSING_SIGNATURE_BYPASS = "skip_thought_signature_validator"


def replay_data(item: Any) -> dict[str, Any] | None:
    provider_data = item.get("provider_data") if isinstance(item, dict) else getattr(item, "provider_data", None)
    if not isinstance(provider_data, dict) or "gemini" not in provider_data:
        return None
    metadata = provider_data["gemini"]
    if not isinstance(metadata, dict):
        raise UserError("Invalid Gemini replay metadata.")
    return metadata


def imported_tool_item(item: dict[str, Any]) -> dict[str, Any]:
    """Project foreign Responses tools without rewriting native Gemini items."""
    if item.get("type") in {
        "apply_patch_call", "apply_patch_call_output", "custom_tool_call", "custom_tool_call_output",
    } and replay_data(item) is None:
        return to_chat_compatible_item(item)
    return item


def encode_replay(payload: dict[str, Any]) -> dict[str, Any]:
    return {"version": REPLAY_VERSION, "replay": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}


def decode_replay(item: Any) -> dict[str, Any] | None:
    metadata = replay_data(item)
    if metadata is None:
        return None
    if type(metadata.get("version")) is not int or metadata["version"] not in {1, REPLAY_VERSION}:
        raise UserError("Unsupported Gemini replay version; use a compatible reader or start a new session.")
    if metadata["version"] == 1:
        return metadata
    payload = json.loads(metadata["replay"])
    if not isinstance(payload, dict):
        raise UserError("Invalid Gemini replay metadata.")
    return payload


def legacy_item_parts(item: dict[str, Any], contents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metadata = replay_data(item)
    records = []
    for content_index, content in enumerate(contents):
        for part_index, part in enumerate(content.get("parts", [])):
            if item.get("type") == "function_call":
                selected = metadata.get("part_position") == [content_index, part_index]
            elif item.get("type") == "reasoning":
                selected = part.get("thought") is True and "text" in part
            else:
                selected = not part.get("function_call") and not (part.get("thought") and "text" in part)
            if selected:
                records.append({"content_index": content_index, "part_index": part_index, "part": part})
    return records
