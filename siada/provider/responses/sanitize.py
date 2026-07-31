"""Sanitizers for the OpenAI Responses API protocol.

Pure, environment-agnostic helpers used by the Responses protocol layer
(``responses_model.py``). They enforce request/response shapes required by
the Responses API spec and by OpenAI-compatible proxies, regardless of which
transport (Li proxy / plain OpenAI endpoint) the request goes through.
"""
from __future__ import annotations

from typing import Any

from openai.types.responses.response_reasoning_item import Summary as ReasoningSummary


_PLACEHOLDER_SUMMARY = [{"type": "summary_text", "text": " "}]


# Server-generated fields that the Responses API uses as pointers into its own
# response ``store``. Any of these on an *input* item — including fields our
# session layer faithfully round-trips from a previous ``response.completed``
# event — causes the server to go looking for the original response and
# return 400 / 404 when it is not found (common on a multi-node proxy cluster
# or on a different route). Strip them all so every input item is fully
# self-contained, exactly like ``convertToOpenAIResponsesInput`` does in
# siada-plugin.
#
# NOTE: ``call_id`` is intentionally **kept** on ``function_call`` and
# ``function_call_output`` because it is how the two sides are paired, not a
# store lookup id.
_SERVER_GENERATED_FIELDS: frozenset[str] = frozenset({
    "id",
    "encrypted_content",
    "status",
})

# Fields that are provider-specific (e.g. LiteLLM's ``provider_data``) and
# must be stripped from **every** input item when calling the OpenAI Responses
# API directly. These fields are not part of the OpenAI spec and will cause a
# 400 "Unknown parameter" error if sent to the upstream model.
# This commonly happens when the user switches from a LiteLLM-backed provider
# (which may attach ``provider_data`` to history items) to the Responses
# protocol and the session history is replayed.
_PROVIDER_SPECIFIC_FIELDS: frozenset[str] = frozenset({
    "provider_data",
})


def sanitize_input_reasoning_items(
    input: str | list[Any],
) -> str | list[Any]:
    """Sanitize *every* input item for Responses API compatibility.

    Historically only ``reasoning`` items were sanitized (hence the name), but
    the server actually validates **all** replayed output-origin items the
    same way: any ``id`` on a ``message``, ``function_call``, ``reasoning``
    (``msg_*`` / ``fc_*`` / ``rs_*``) is treated as a pointer into its own
    response ``store``. If the id was minted by a different route or stored
    on a different proxy node, the server returns errors like:

    - ``Item with id 'rs_...' not found``
    - ``Item 'msg_...' of type 'message' was provided without its required
      'reasoning' item 'rs_...'``

    The second error is especially misleading: it does not mean the
    reasoning item is missing from the payload (it usually is present), it
    means the server resolved ``msg_*`` via store lookup, found the stored
    message linked to a stored reasoning id, and that stored reasoning id
    does not match the one we sent. The fix is not to pair them differently
    but to stop sending the store ids altogether.

    So this function:

    * Removes every ``_SERVER_GENERATED_FIELDS`` key from dict items that
      look like they came from ``response.output``:
      ``message`` / ``function_call`` / ``function_call_output`` /
      ``reasoning``.  ``call_id`` is preserved because it is how
      function_call and function_call_output are linked — it is not a store
      id.
    * For ``reasoning`` items, additionally fills an empty ``summary`` with
      a whitespace placeholder so the server does not reject the item and
      the following assistant message does not get orphaned.
    * Leaves plain user messages (``{"role": "user", "content": ...}``)
      and any non-dict items untouched.

    See ``siada-plugin/src/core/api/transform/openai-response-format.ts::
    convertToOpenAIResponsesInput`` for the mirror implementation used by
    the VSCode plugin — it builds its input items from scratch and never
    carries server store ids forward, which is the behavior we emulate here.
    """
    if isinstance(input, str):
        return input

    sanitized: list[Any] = []

    # Types that originate from ``response.output`` and therefore carry
    # server store ids we need to strip.
    output_origin_types = {
        "reasoning",
        "message",
        "function_call",
        "function_call_output",
    }

    for item in input:
        if not isinstance(item, dict):
            sanitized.append(item)
            continue

        item_type = item.get("type")

        # Strip provider-specific fields (e.g. LiteLLM's ``provider_data``)
        # from ALL dict items — these are not part of the OpenAI spec and will
        # cause a 400 "Unknown parameter" error if sent upstream. This is the
        # most common cause of failure when switching from a LiteLLM-backed
        # provider to the Responses protocol and replaying session history.
        if _PROVIDER_SPECIFIC_FIELDS.intersection(item):
            item = {k: v for k, v in item.items() if k not in _PROVIDER_SPECIFIC_FIELDS}

        # User-written messages are already self-contained ``{role, content}``
        # shapes — no server store ids to strip.
        if item_type not in output_origin_types:
            sanitized.append(item)
            continue

        cleaned = {
            k: v
            for k, v in item.items()
            if k not in _SERVER_GENERATED_FIELDS
        }

        if item_type == "reasoning":
            # Reasoning items in the Responses API schema do NOT have a
            # ``content`` field (max_items: 0). LiteLLM / li-provider
            # serialisation sometimes attaches a ``content`` array to these
            # items (e.g. ``[{"type": "reasoning_summary", "text": "..."}]``).
            # Sending that triggers:
            #   "Invalid 'input[N].content': array too long.
            #    Expected an array with maximum length 0, but got an array
            #    with length 1 instead."
            cleaned.pop("content", None)

            # Placeholder so the item passes server validation and the paired
            # message is not orphaned. Short-answer turns often have no
            # reasoning_summary_text.delta at all, which would leave
            # ``summary: []`` here; server would then complain about the item
            # being "incomplete".
            summary = cleaned.get("summary")
            has_summary = (
                bool(summary) if not isinstance(summary, list) else len(summary) > 0
            )
            if not has_summary:
                cleaned["summary"] = _PLACEHOLDER_SUMMARY

        sanitized.append(cleaned)

    return sanitized


def sanitize_schema_for_openai(schema: Any) -> Any:
    """Recursively sanitize JSON Schema for OpenAI Responses function tools."""
    if isinstance(schema, list):
        return [sanitize_schema_for_openai(item) for item in schema]

    if not isinstance(schema, dict):
        return schema

    result = {}
    for key, value in schema.items():
        if key == "additionalProperties" and isinstance(value, dict):
            if not value:
                # `{}` means arbitrary values; dropping it avoids OpenAI schema rejection.
                continue
            if "type" not in value:
                value = dict(value, type="object")
            result[key] = sanitize_schema_for_openai(value)
        else:
            result[key] = sanitize_schema_for_openai(value)

    return result


def sanitize_responses_tools_for_openai(converted_tools: list[Any]) -> list[Any]:
    """Sanitize Responses API tool schemas to satisfy OpenAI strict validation."""
    sanitized: list[Any] = []
    for tool in converted_tools:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            sanitized.append(tool)
            continue

        new_tool = dict(tool)
        params = new_tool.get("parameters")
        if isinstance(params, dict):
            new_tool["parameters"] = sanitize_schema_for_openai(params)

        # MCP tool schemas often contain free-form dicts and are not strict-compatible.
        new_tool.pop("strict", None)
        sanitized.append(new_tool)

    return sanitized


def ensure_reasoning_summary_nonempty(output_items: list[Any]) -> None:
    """Final safety net: ensure every reasoning item has a non-empty summary.

    Used on the non-streaming path and as a final check at the end of streaming.
    If the upstream returns ``summary: []`` for a reasoning item and we have no
    delta text to patch in, we at least put a whitespace placeholder so
    downstream code (``sanitize_input_reasoning_items`` on the next turn and
    the session persistence layer) never sees an empty list. An empty summary
    would otherwise cause either:
      - paired assistant messages to be dropped on replay, or
      - the upstream to reject the request with
        "Item 'rs_...' of type 'reasoning' was provided without its required
        following item".
    """
    if not output_items:
        return
    for item in output_items:
        if getattr(item, "type", None) != "reasoning":
            continue
        summary = getattr(item, "summary", None)
        has_summary = bool(summary) and (
            not isinstance(summary, list) or len(summary) > 0
        )
        if has_summary:
            continue
        try:
            item.summary = [ReasoningSummary(type="summary_text", text=" ")]
        except Exception:
            # Best-effort only; if the item is not mutable we silently skip —
            # the sanitizer on the next turn will still add a placeholder.
            pass
