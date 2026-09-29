"""Tests for ``siada.provider.responses.sanitize.sanitize_input_reasoning_items``.

Policy under test: output-origin items are replayed **verbatim**.  An item's
``id`` is the server-side store pointer, and on ``reasoning`` items
``encrypted_content`` is the only carrier of the model's reasoning state, so
dropping either silently breaks reasoning continuity instead of surfacing the
gateway problem.  Only four normalisations remain:

* ``provider_data`` (LiteLLM-only) is removed from every item;
* the SDK's Chat Completions placeholder id (``__fake_id__``) is removed from
  every item — it is not a store pointer, and the Responses API rejects it
  (``Expected an ID that begins with 'rs'``) as soon as a session that started
  on a Chat Completions model (glm-5.3) switches to a Responses model
  (gpt-5.6-luna);
* a stray ``content`` array is removed from ``reasoning`` items (the Responses
  schema allows ``max_items: 0`` there);
* an empty ``reasoning.summary`` gets a whitespace placeholder so the item is
  not rejected and its paired message is not orphaned.

The legacy "self-contained payload" behaviour is still reachable through the
``SIADA_RESPONSES_STRIP_ITEM_IDS=1`` escape hatch.
"""

import pytest

from siada.provider.responses.sanitize import (
    _PLACEHOLDER_SUMMARY,
    sanitize_input_reasoning_items,
)

_PATCH_DIFF = "@@\n-# OpenAI Agents SDK\n+# OpenAI Agents SDK\n"


def _reasoning(item_id="rs_1", *, summary=None, extra=None):
    item = {
        "id": item_id,
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "thinking"}] if summary is None else summary,
    }
    if extra:
        item.update(extra)
    return item


def _patch_call(call_id: str = "call_1", item_id: str = "apc_1") -> dict:
    return {
        "id": item_id,
        "call_id": call_id,
        "type": "apply_patch_call",
        "status": "completed",
        "operation": {
            "type": "update_file",
            "path": "README.md",
            "diff": _PATCH_DIFF,
        },
    }


def _patch_output(call_id: str = "call_1") -> dict:
    return {
        "id": "apoc_1",
        "call_id": call_id,
        "type": "apply_patch_call_output",
        "status": "failed",
        "output": "ERROR: apply_patch failed for README.md: Invalid Context 3",
    }


def test_apply_patch_call_is_replayed_verbatim():
    (item,) = sanitize_input_reasoning_items([_patch_call()])

    assert item["id"] == "apc_1"
    assert item["status"] == "completed"
    assert item["call_id"] == "call_1"
    assert item["type"] == "apply_patch_call"
    assert item["operation"]["path"] == "README.md"


def test_apply_patch_call_output_is_replayed_verbatim():
    (item,) = sanitize_input_reasoning_items([_patch_output()])

    assert item["id"] == "apoc_1"
    assert item["status"] == "failed"
    assert item["call_id"] == "call_1"
    assert item["output"].startswith("ERROR: apply_patch failed")


def test_replayed_patch_turn_keeps_store_ids_and_reasoning_state():
    """The shape that previously 400'd: reasoning + message + patch call/output."""
    reasoning = _reasoning(
        "rs_0c997a3ba29e809f006aad09b219048194b9ae824849987057",
        summary=[],
        extra={"encrypted_content": "ENC_BLOB"},
    )
    message = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": "Updating the README."}],
    }

    sanitized = sanitize_input_reasoning_items(
        [reasoning, message, _patch_call(), _patch_output()]
    )

    assert [item["id"] for item in sanitized] == [
        "rs_0c997a3ba29e809f006aad09b219048194b9ae824849987057",
        "msg_1",
        "apc_1",
        "apoc_1",
    ]
    assert sanitized[0]["encrypted_content"] == "ENC_BLOB"
    assert sanitized[0]["summary"] == _PLACEHOLDER_SUMMARY
    assert sanitized[1]["content"][0]["text"] == "Updating the README."
    assert sanitized[2]["call_id"] == sanitized[3]["call_id"] == "call_1"


@pytest.mark.parametrize(
    "item_type",
    [
        "shell_call",
        "shell_call_output",
        "local_shell_call",
        "computer_call",
        "computer_call_output",
        "code_interpreter_call",
        "image_generation_call",
        "mcp_call",
        "web_search_call",
        "file_search_call",
        "custom_tool_call",
        "custom_tool_call_output",
    ],
)
def test_native_tool_items_are_replayed_verbatim(item_type):
    (item,) = sanitize_input_reasoning_items(
        [{"id": "store_1", "call_id": "call_x", "type": item_type, "status": "done"}]
    )

    assert item["id"] == "store_1"
    assert item["status"] == "done"
    assert item["call_id"] == "call_x"


def test_function_call_is_replayed_verbatim():
    (item,) = sanitize_input_reasoning_items(
        [
            {
                "id": "fc_1",
                "call_id": "call_9",
                "type": "function_call",
                "name": "edit_file",
                "arguments": "{}",
                "status": "completed",
            }
        ]
    )

    assert item["id"] == "fc_1"
    assert item["status"] == "completed"
    assert item["call_id"] == "call_9"
    assert item["name"] == "edit_file"


def test_reasoning_item_drops_stray_content_array():
    """``input[N].content`` on a reasoning item must stay empty (max_items: 0)."""
    (item,) = sanitize_input_reasoning_items(
        [_reasoning(extra={"content": [{"type": "reasoning_summary", "text": "x"}]})]
    )

    assert "content" not in item
    assert item["summary"][0]["text"] == "thinking"


def test_non_empty_summary_is_not_overwritten():
    (item,) = sanitize_input_reasoning_items(
        [_reasoning(summary=[{"type": "summary_text", "text": "real summary"}])]
    )

    assert item["summary"] == [{"type": "summary_text", "text": "real summary"}]


def test_user_messages_and_item_reference_are_untouched():
    user_message = {"role": "user", "content": "hi"}
    item_reference = {"type": "item_reference", "id": "rs_keep_me"}

    sanitized = sanitize_input_reasoning_items([user_message, item_reference])

    assert sanitized[0] == user_message
    assert sanitized[1] == item_reference


def test_non_dict_items_and_string_input_pass_through():
    assert sanitize_input_reasoning_items("just a prompt") == "just a prompt"
    assert sanitize_input_reasoning_items(["raw", 42]) == ["raw", 42]


def test_provider_specific_fields_are_stripped_everywhere():
    sanitized = sanitize_input_reasoning_items(
        [
            {"role": "user", "content": "hi", "provider_data": {"x": 1}},
            {**_patch_call(), "provider_data": {"y": 2}},
        ]
    )

    assert all("provider_data" not in item for item in sanitized)
    assert sanitized[1]["id"] == "apc_1"


# Items the SDK's Chat Completions converters mint for a GLM turn (see
# ``agents/models/chatcmpl_converter.py``): every item carries
# ``id="__fake_id__"``, and reasoning items also carry ``provider_data``.
def _chat_completions_turn():
    return [
        {"role": "user", "content": "hi"},
        {
            "id": "__fake_id__",
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "thinking"}],
            "provider_data": {"chat_completions_reasoning_field": "reasoning"},
        },
        {
            "id": "__fake_id__",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "done"}],
            "status": "completed",
        },
        {
            "id": "__fake_id__",
            "call_id": "call_1",
            "type": "function_call",
            "name": "edit_file",
            "arguments": "{}",
        },
    ]


def test_chat_completions_placeholder_ids_are_dropped_on_replay():
    """glm-5.3 -> gpt-5.6-luna model switch must not replay ``__fake_id__``.

    Regression test for: ``Invalid 'input[1].id': '__fake_id__'.
    Expected an ID that begins with 'rs'.``
    """
    sanitized = sanitize_input_reasoning_items(_chat_completions_turn())

    assert all("id" not in item for item in sanitized)
    # Everything else about those items survives: reasoning summary, assistant
    # text, and the call/output pairing.
    assert [item["type"] for item in sanitized[1:]] == [
        "reasoning",
        "message",
        "function_call",
    ]
    assert sanitized[1]["summary"][0]["text"] == "thinking"
    assert "provider_data" not in sanitized[1]
    assert sanitized[2]["content"][0]["text"] == "done"
    assert sanitized[3]["call_id"] == "call_1"
    assert sanitized[3]["name"] == "edit_file"


def test_placeholder_ids_are_dropped_but_real_store_ids_survive():
    sanitized = sanitize_input_reasoning_items(
        [
            _reasoning("__fake_id__"),
            _reasoning("rs_0c997a3ba29e809f006aad09b219048194b9ae824849987057"),
            {"id": "msg_1", "type": "message", "role": "assistant", "content": []},
            {
                "id": "fc_1",
                "call_id": "call_9",
                "type": "function_call",
                "name": "edit_file",
                "arguments": "{}",
            },
            # A placeholder id is meaningless on any item, not only on
            # output-origin ones.
            {"id": "__fake_id__", "role": "user", "content": "hi"},
        ]
    )

    assert "id" not in sanitized[0]
    assert sanitized[1]["id"].startswith("rs_")
    assert sanitized[2]["id"] == "msg_1"
    assert sanitized[3]["id"] == "fc_1"
    assert "id" not in sanitized[4]


def test_verbatim_replay_is_the_default(monkeypatch):
    monkeypatch.delenv("SIADA_RESPONSES_STRIP_ITEM_IDS", raising=False)

    (item,) = sanitize_input_reasoning_items(
        [_reasoning(extra={"encrypted_content": "ENC", "status": "completed"})]
    )

    assert item["id"] == "rs_1"
    assert item["status"] == "completed"
    assert item["encrypted_content"] == "ENC"


def test_escape_hatch_strips_store_ids(monkeypatch):
    monkeypatch.setenv("SIADA_RESPONSES_STRIP_ITEM_IDS", "1")
    reasoning = _reasoning(summary=[], extra={"encrypted_content": "ENC"})

    sanitized = sanitize_input_reasoning_items(
        [reasoning, {"id": "msg_1", "type": "message", "role": "assistant", "content": []},
         _patch_call(), _patch_output()]
    )

    assert all("id" not in item for item in sanitized)
    assert all("status" not in item for item in sanitized)
    assert "encrypted_content" not in sanitized[0]
    assert sanitized[0]["summary"] == _PLACEHOLDER_SUMMARY
    assert sanitized[2]["call_id"] == sanitized[3]["call_id"] == "call_1"
