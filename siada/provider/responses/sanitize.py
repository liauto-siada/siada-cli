"""Sanitizers for the OpenAI Responses API protocol.

Pure, environment-agnostic helpers used by the Responses protocol layer
(``responses_model.py``). They enforce request/response shapes required by
the Responses API spec and by OpenAI-compatible proxies, regardless of which
transport (Li proxy / plain OpenAI endpoint) the request goes through.
"""
from __future__ import annotations

import os
from typing import Any

from agents.models.fake_id import FAKE_RESPONSES_ID
from openai.types.responses.response_reasoning_item import Summary as ReasoningSummary


_PLACEHOLDER_SUMMARY = [{"type": "summary_text", "text": " "}]


# Server-generated fields that the Responses API uses as pointers into its own
# response ``store``.  They are replayed **verbatim** by default: an item's
# ``id`` is the documented way for the server to resolve the stored response,
# and on ``reasoning`` items ``encrypted_content`` is the only carrier of the
# model's reasoning state in stateless (``store: false`` / ZDR) mode.
#
# Escape hatch: ``SIADA_RESPONSES_STRIP_ITEM_IDS=1`` restores the historical
# "self-contained payload" behaviour (strip ``id`` / ``status`` /
# ``encrypted_content``).  It is opt-in on purpose — stripping the ids also
# dropped ``encrypted_content``, which silently broke reasoning continuity
# instead of surfacing the gateway incompatibility.
#
# ``call_id`` is never stripped: it pairs ``function_call`` with
# ``function_call_output`` (and ``apply_patch_call`` with its output) and is not
# a store lookup id.
_SERVER_GENERATED_FIELDS: frozenset[str] = frozenset({
    "id",
    "encrypted_content",
    "status",
})


# Placeholder ``id`` values minted by the SDK's Chat Completions converters.
# ``agents.models.fake_id.FAKE_RESPONSES_ID`` (``__fake_id__``) fills the ``id``
# field of every item built from a Chat Completions response
# (``chatcmpl_converter`` / ``chatcmpl_stream_handler``) — i.e. every GLM /
# DeepSeek / Qwen turn on the li gateway.  It is NOT a store pointer: the
# Responses API validates the id prefix against the item type and rejects the
# whole request, e.g.
#   Invalid 'input[1].id': '__fake_id__'. Expected an ID that begins with 'rs'.
# A model switch mid-session (Chat Completions -> Responses protocol) replays
# exactly those items, so the field is dropped here.  Mirrors the SDK's own
# ``agents.models.openai_responses._clean_item_for_openai``, which deletes the
# same id before sending.  Kept as a set so future SDK placeholders can be
# added without touching the loop below.
_PLACEHOLDER_ITEM_IDS: frozenset[str] = frozenset({FAKE_RESPONSES_ID})


def _strip_server_item_ids() -> bool:
    """Return True when the store-id stripping escape hatch is enabled."""
    return os.environ.get("SIADA_RESPONSES_STRIP_ITEM_IDS", "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
    )

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
    does not match the one we sent.  Such failures are surfaced as-is instead
    of being masked by stripping the ids (see the escape hatch above): the
    ids are what lets the server resolve the stored response, and
    ``encrypted_content`` is what carries the reasoning state.

    So this function:

    * Replays items that came from ``response.output`` verbatim — ``message`` /
      ``function_call`` / ``function_call_output`` / ``reasoning`` and the
      native tool-call items — keeping ``id``, ``status`` and
      ``encrypted_content``.  ``call_id`` is obviously preserved: it is how a
      call and its output are paired.  The one exception is a placeholder
      ``id`` (see below), which is not a store pointer.
    * Drops ``provider_data`` from every dict item — it is a LiteLLM-only field
      that the OpenAI spec rejects with a 400 ``Unknown parameter``.
    * Drops placeholder ``id`` values (``__fake_id__``, minted by the SDK's
      Chat Completions converters) from every dict item.  They are never store
      pointers, and the Responses API validates the id prefix against the item
      type, so replaying one fails with
      ``Invalid 'input[1].id': '__fake_id__'. Expected an ID that begins with
      'rs'.`` — exactly what happened when a session started on a Chat
      Completions model (glm-5.3 via the li gateway) and then switched to a
      Responses model (gpt-5.6-luna).
    * For ``reasoning`` items, drops a stray ``content`` array (the Responses
      schema allows ``max_items: 0`` there) and fills an empty ``summary`` with
      a whitespace placeholder so the server does not reject the item and
      orphan the following assistant message.
    * Leaves plain user messages (``{"role": "user", "content": ...}``)
      and any non-dict items untouched.

    Setting ``SIADA_RESPONSES_STRIP_ITEM_IDS=1`` switches back to the old
    "every item must be self-contained" behaviour for emergencies; it is
    deliberately manual, because a silent fallback would hide gateway
    incompatibilities instead of surfacing them.
    """
    if isinstance(input, str):
        return input

    sanitized: list[Any] = []

    # Types that originate from ``response.output`` and are therefore replayed
    # as-is (keeping their store ``id`` and, for ``reasoning`` items, the
    # ``encrypted_content`` that carries the model's reasoning state).  The set
    # only decides which items get the ``reasoning`` normalisation below and, if
    # the escape hatch is on, the legacy store-id stripping.
    #
    # ``call_id`` keeps the call/output pairing intact (it is not a store id),
    # and it is never touched.
    output_origin_types = {
        "reasoning",
        "message",
        "function_call",
        "function_call_output",
        # apply_patch (native patch tool)
        "apply_patch_call",
        "apply_patch_call_output",
        # shell / computer / code-interpreter / image-generation
        "shell_call",
        "shell_call_output",
        "local_shell_call",
        "local_shell_call_output",
        "computer_call",
        "computer_call_output",
        "code_interpreter_call",
        "image_generation_call",
        # MCP + hosted tools
        "mcp_call",
        "mcp_list_tools",
        "mcp_approval_request",
        "mcp_approval_response",
        "web_search_call",
        "file_search_call",
        "custom_tool_call",
        "custom_tool_call_output",
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

        # Placeholder ids (see _PLACEHOLDER_ITEM_IDS) are never store pointers,
        # so they are dropped from every dict item regardless of its type: a
        # Chat Completions turn persisted with ``__fake_id__`` is rejected the
        # moment the session switches to a Responses model.
        if item.get("id") in _PLACEHOLDER_ITEM_IDS:
            item = {k: v for k, v in item.items() if k != "id"}

        # User-written messages are already self-contained ``{role, content}``
        # shapes — no server store ids to strip.
        if item_type not in output_origin_types:
            sanitized.append(item)
            continue

        # Verbatim replay is the default.  The escape hatch rebuilds the item
        # without the server-generated store fields for emergencies.
        if _strip_server_item_ids():
            cleaned = {
                k: v
                for k, v in item.items()
                if k not in _SERVER_GENERATED_FIELDS
            }
        else:
            cleaned = dict(item)

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
