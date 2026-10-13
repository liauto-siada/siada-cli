"""Durable business state, separate from request budgets and live resources."""

from __future__ import annotations

import copy
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from siada.services.session_storage import SessionStorageError, recover_transaction, session_storage_lock, storage_transaction, write_json
from siada.support.usage_utils import deserialize_usage, serialize_usage


STATE_FILE = "runtime_state.json"
CONTEXT_FIELDS = (
    "todos", "todo_turns_since_write", "todo_turns_since_reminder",
    "hook_pending_input_updates", "pending_reminder_items",
    "pending_hallucination_reminder_items", "pending_repeated_tool_reminder_items",
)


def empty_state(session_id: str) -> dict:
    return {
        "format_version": 1, "session_id": session_id, "state_version": 0,
        "todos": [], "todo_turns_since_write": 0, "todo_turns_since_reminder": 0,
        "hook_pending_input_updates": {}, "pending_notifications": [],
        "pending_reminder_items": [], "pending_hallucination_reminder_items": [],
        "pending_repeated_tool_reminder_items": [], "delivered_notifications": [],
        "usage": None, "usage_records": {}, "request_counters": {},
    }


def notification_identity(text: str) -> str:
    """Notification producers embed task identities in their generated text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_state(data: Any, session_id: str) -> dict:
    from siada.tools.todo.models import TodoItem

    try:
        if (not isinstance(data, dict) or data.get("session_id") != session_id
                or type(data.get("format_version")) is not int or data["format_version"] != 1):
            raise ValueError("invalid identity or format")
        for name in ("state_version", "todo_turns_since_write", "todo_turns_since_reminder"):
            if type(data.get(name)) is not int or data[name] < 0:
                raise ValueError(f"invalid {name}")
        if not isinstance(data.get("todos"), list):
            raise ValueError("invalid todos")
        for item in data["todos"]:
            TodoItem.model_validate(item)
        for name in ("pending_notifications", "delivered_notifications"):
            if not isinstance(data.get(name), list) or not all(isinstance(item, str) for item in data[name]):
                raise ValueError(f"invalid {name}")
        for name in ("hook_pending_input_updates", "usage_records", "request_counters"):
            if not isinstance(data.get(name), dict):
                raise ValueError(f"invalid {name}")
        for name in CONTEXT_FIELDS[4:]:
            if not isinstance(data.get(name), list) or not all(isinstance(item, dict) for item in data[name]):
                raise ValueError(f"invalid {name}")
        usage = data.get("usage")
        if usage is not None and (not isinstance(usage, dict) or deserialize_usage(usage) is None):
            raise ValueError("invalid usage")
    except (ValueError, TypeError, KeyError) as error:
        raise SessionStorageError("Invalid structured session state") from error
    return copy.deepcopy(data)


def load_state(folder: Path, session_id: str) -> dict | None:
    with session_storage_lock(folder):
        recover_transaction(folder)
        path = folder / STATE_FILE
        if not path.exists():
            return None
        try:
            return validate_state(json.loads(path.read_bytes()), session_id)
        except (ValueError, OSError) as error:
            raise SessionStorageError("Cannot load structured session state") from error


def capture_context(context) -> dict:
    session = context.session
    from siada.services.file_session import FileSession

    store = session.state.openai_session
    state = (load_state(store.session_folder, session.session_id)
             if isinstance(store, FileSession) else None) or empty_state(session.session_id)
    for name in CONTEXT_FIELDS:
        value = getattr(context, name)
        state[name] = [item.model_dump() for item in value] if name == "todos" else copy.deepcopy(value)
    state["pending_notifications"] = list(context.hook_pending_contexts)
    state["goal"] = context.goal.model_dump() if context.goal is not None else None
    if state["usage"] is None:
        state["usage"] = serialize_usage(session.state.usage)
    return state


def save_context(context) -> None:
    """Persist at business boundaries; stale contexts cannot mutate a resumed session."""
    from siada.services.file_session import FileSession

    session = getattr(context, "session", None)
    store = session.state.openai_session if session is not None else None
    if not isinstance(store, FileSession):
        return
    if store.session_id != session.session_id or getattr(context, "bound_session_id", session.session_id) != session.session_id:
        raise SessionStorageError("Context no longer owns the current session")
    with storage_transaction(store.session_folder):
        current = load_state(store.session_folder, session.session_id) or empty_state(session.session_id)
        snapshot = capture_context(context)
        # Request budget overwrites SessionState.usage on legacy filters; actual
        # response usage is updated only by record_response below.
        snapshot.pop("usage")
        snapshot.pop("goal")
        for name in (*CONTEXT_FIELDS, "pending_notifications"):
            current[name] = snapshot[name]
        current["state_version"] += 1
        write_json(store.session_folder / STATE_FILE, validate_state(current, session.session_id))


def apply_state(context, data: dict) -> None:
    from siada.tools.todo.models import TodoItem

    data = validate_state(data, context.session.session_id)
    for name in CONTEXT_FIELDS:
        value = data[name]
        setattr(context, name, [TodoItem.model_validate(item) for item in value] if name == "todos" else copy.deepcopy(value))
    context.hook_pending_contexts = list(data["pending_notifications"])
    context.session.state.usage = deserialize_usage(data["usage"])


def record_response(context, response, *, identity: str | None = None) -> None:
    from agents.models.fake_id import FAKE_RESPONSES_ID
    from siada.services.file_session import FileSession

    session = getattr(context, "session", None)
    store = session.state.openai_session if session is not None else None
    if not isinstance(store, FileSession):
        return
    if context.bound_session_id != session.session_id or store.session_id != session.session_id:
        raise SessionStorageError("Response belongs to a replaced session")
    usage = serialize_usage(response.usage)
    if usage is None:
        raise SessionStorageError("Response usage could not be serialized")
    # Real provider response IDs identify a callback replay, not a logical retry.
    identity = identity or getattr(response, "response_id", None)
    if not identity or identity == FAKE_RESPONSES_ID:
        identity = getattr(response, "_siada_usage_identity", None) or uuid.uuid4().hex
        response._siada_usage_identity = identity
    with storage_transaction(store.session_folder):
        current = load_state(store.session_folder, session.session_id) or empty_state(session.session_id)
        records = current["usage_records"]
        if identity in records and records[identity] != usage:
            raise SessionStorageError("Response identity was reused with different usage")
        records[identity] = usage
        current["usage"] = usage
        current["state_version"] += 1
        write_json(store.session_folder / STATE_FILE, validate_state(current, session.session_id))


def commit_request_state(context, delivered: list[str], *, request_identity: str) -> None:
    """Run inside message admission's transaction before clearing live queues."""
    store = context.session.state.openai_session
    current = load_state(store.session_folder, store.session_id) or empty_state(store.session_id)
    snapshot = capture_context(context)
    for name in CONTEXT_FIELDS:
        current[name] = snapshot[name]
    current["pending_notifications"] = list(snapshot["pending_notifications"])
    for text in delivered:
        if text in current["pending_notifications"]:
            current["pending_notifications"].remove(text)
        identity = notification_identity(text)
        if identity not in current["delivered_notifications"]:
            current["delivered_notifications"].append(identity)
    for name in CONTEXT_FIELDS[4:]:
        current[name] = []
    current["request_counters"][request_identity] = {
        "todo_turns_since_write": context.todo_turns_since_write,
        "todo_turns_since_reminder": context.todo_turns_since_reminder,
    }
    current["state_version"] += 1
    write_json(store.session_folder / STATE_FILE, validate_state(current, store.session_id))


def restore_state(folder: Path, session_id: str, snapshot: dict) -> dict:
    """Restore business state without erasing actual usage or delivery receipts."""
    from siada.services.goal.models import Goal

    saved = validate_state(snapshot, session_id)
    if "goal" not in snapshot:
        raise SessionStorageError("Checkpoint has no structured goal state")
    goal = Goal.model_validate(snapshot["goal"]) if snapshot["goal"] is not None else None
    current = load_state(folder, session_id) or empty_state(session_id)
    saved["state_version"] = current["state_version"] + 1
    saved["usage_records"] = {**saved["usage_records"], **current["usage_records"]}
    saved["delivered_notifications"] = list(dict.fromkeys(
        saved["delivered_notifications"] + current["delivered_notifications"],
    ))
    saved["pending_notifications"] = [text for text in saved["pending_notifications"]
                                      if notification_identity(text) not in saved["delivered_notifications"]]
    saved["request_counters"] = {**saved["request_counters"], **current["request_counters"]}
    write_json(folder / STATE_FILE, saved)
    if goal is None:
        (folder / "goal.json").unlink(missing_ok=True)
    else:
        write_json(folder / "goal.json", goal.model_dump())
    return saved


def stage_notification(context, text: str) -> None:
    context.hook_pending_contexts.append(text)
    save_context(context)
