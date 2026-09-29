"""Trajectory event helpers shared by the atomizer, classifier, and matcher.

Events are plain dicts matching chrome-acp's ``TrajectoryEvent`` schema
(see packages/shared/src/acp/types.ts in the chrome-acp repo):

    {"ts": int, "type": "navigation", "url": str, "title": str, "tabId"?: int}
    {"ts": int, "type": "action", "url": str, "title": str, "tabId"?: int,
     "action": {"kind": "click"|"input"|"select"|"keydown"|"scroll",
                "target"?: {...}, "value"?: str, "key"?: str,
                "scrollX"?: int, "scrollY"?: int},
     "response"?: str}
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from .models import ReplayStep

_SECRET_KEY = re.compile(
    r"(?:password|passwd|pwd|secret|api[_-]?key|(?:access|refresh|id)[_-]?token|"
    r"authorization|cookie|auth_session|^token$)", re.IGNORECASE
)
_REDACTED = "[REDACTED]"


def registered_domain(url: str) -> str:
    """Best-effort registrable domain (host without the scheme/port)."""
    if not url:
        return ""
    try:
        host = urlparse(url).netloc or url
    except ValueError:
        return ""
    host = host.split("@")[-1]  # strip userinfo
    host = host.split(":")[0]  # strip port
    return host.lower()


def slugify(name: str) -> str:
    """kebab-case, filesystem-safe capacity name."""
    slug = name.lower().replace("_", "-").replace(" ", "-")
    return re.sub(r"[^a-z0-9\-]", "", slug) or "unknown"


def sanitize_text(text: str) -> str:
    """Redact recognizable credentials without shortening the surrounding evidence."""
    text = re.sub(r"(?i)(https?://)[^/@\s]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    return re.sub(
        r"(?i)((?:password|passwd|secret|api[_-]?key|(?:access|refresh|id)[_-]?token|"
        r"auth_session|token|cookie|authorization)[\"']?\s*[:=]\s*)"
        r"(?:\"[^\"]*\"|'[^']*'|[^\s&,;}]+)",
        lambda match: match.group(1) + _REDACTED,
        text,
    )


def _credential_values(value):
    if isinstance(value, dict):
        if value.get("kind") in ("input", "select") and _SECRET_KEY.search(
            json.dumps(value.get("target") or {}, ensure_ascii=False)
        ):
            if isinstance(value.get("value"), str) and value["value"]:
                yield value["value"]
        for key, item in value.items():
            if _SECRET_KEY.search(str(key)) and isinstance(item, str) and item:
                yield item
            yield from _credential_values(item)
    elif isinstance(value, list):
        for item in value:
            yield from _credential_values(item)


def _sanitize_value(value, secrets):
    if isinstance(value, dict):
        return {
            key: item if key in ("event_id", "call_id", "tool_call_id") else (
                _REDACTED if _SECRET_KEY.search(str(key)) else _sanitize_value(item, secrets)
            ) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_value(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, _REDACTED)
        return sanitize_text(value)
    return value


def sanitize_events(events: list[dict]) -> list[dict]:
    """Redact nested credentials and their echoes without mutating evidence IDs."""
    secrets = sorted(set(_credential_values(events)) - {_REDACTED}, key=len, reverse=True)
    return _sanitize_value(events, secrets)


def _describe_action(event: dict) -> str:
    action = event.get("action") or {}
    target = action.get("target") or {}
    label = target.get("text") or target.get("ariaLabel") or target.get("tag") or ""
    parts = [action.get("kind", "?")]
    if label:
        parts.append(f'"{label.strip()}"')
    if action.get("value") is not None:
        parts.append(f"= {action['value']!r}")
    line = " ".join(parts)
    if event.get("response"):
        line += f"  -> {event['response']}"
    return line


def summarize_events(events: list[dict]) -> str:
    """Render every event; evidence limits are handled by lossless batching."""
    lines = []
    for event in sanitize_events(events):
        if event.get("type") == "navigation":
            lines.append(f"navigate -> {event.get('url', '')}")
        elif event.get("type") == "action":
            lines.append(_describe_action(event))
        else:
            lines.append(json.dumps(event, ensure_ascii=False))
    return "\n".join(lines)


def evidence_chunks(events: list[dict], max_chars: int = 16000) -> list[list[dict]]:
    """Batch complete evidence, splitting long serialized events with stable IDs."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    chunks = []
    current = []
    size = 0
    for event in events:
        encoded = json.dumps(event, ensure_ascii=False)
        pieces = [encoded[i:i + max_chars] for i in range(0, len(encoded), max_chars)]
        for index, piece in enumerate(pieces):
            item = event if len(pieces) == 1 else {
                "event_id": event["event_id"], "part": index + 1,
                "parts": len(pieces), "evidence": piece,
            }
            if current and size + len(piece) > max_chars:
                chunks.append(current)
                current, size = [], 0
            current.append(item)
            size += len(piece)
    if current:
        chunks.append(current)
    return chunks


_REPLAY_ACTION_KINDS = ("click", "input", "select", "keydown", "scroll")


def _event_to_replay_step(event: dict) -> ReplayStep | None:
    """Convert one evidence event into a deterministic ReplayStep.

    Accepts human/trajectory action + navigation events and the agent's own
    ``browser_replay`` tool inputs (whose ``input`` already IS a step).
    ``browser_execute`` scripts are not deterministically replayable and are
    skipped.
    """
    if event.get("type") == "navigation":
        url = event.get("url")
        return ReplayStep(kind="navigate", url=url) if isinstance(url, str) else None
    if event.get("type") == "tool" and event.get("name") == "browser_replay":
        step = event.get("input")
        if isinstance(step, dict) and step.get("kind") in _REPLAY_ACTION_KINDS:
            return ReplayStep(
                kind=step["kind"], target=step.get("target"), value=step.get("value"),
                key=step.get("key"), scrollX=step.get("scrollX"), scrollY=step.get("scrollY"),
            )
        return None
    if event.get("type") == "action":
        action = event.get("action") or {}
        if action.get("kind") in _REPLAY_ACTION_KINDS:
            return ReplayStep(
                kind=action["kind"], target=action.get("target"), value=action.get("value"),
                key=action.get("key"), scrollX=action.get("scrollX"), scrollY=action.get("scrollY"),
            )
    return None


def build_replay_steps(events: list[dict]) -> list[ReplayStep]:
    """Time-ordered replay steps from a merged evidence stream."""
    return [step for event in events if (step := _event_to_replay_step(event)) is not None]
