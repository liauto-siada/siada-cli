"""Verification: MCP result parsing, page observation, and fixed postconditions.

Design doc §5 — evidence and acceptance:

- Browser tools are parsed with MCP ``isError`` / ``structuredContent`` / explicit
  JSON ``ok`` fields. Page text such as ``## Error`` or ``error_`` is *never*
  treated as a failure signal, and ``isError=False`` only proves the tool call
  itself succeeded — not that the business task succeeded.
- Reading a page follows `browser_read`'s pagination metadata (chrome-acp text
  format ``- Content: showing chars 0–50000 of N`` plus ``## Page Content``,
  or structuredContent ``url/text/content/totalChars``). A read that fails,
  jumps to a different URL, or makes no forward progress is incomplete.
- Only the fixed whitelist of postconditions is evaluated: ``url_equals``,
  ``text_present``, ``text_absent``, each with a non-empty value. No arbitrary
  scripts are executed and no conditions means ``unknown`` — never success.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from typing import Any

from siada.services.browser_skill import models

logger = logging.getLogger(__name__)

# chrome-acp `browser_read` slice size (chars) used by the real MCP handler.
READ_LIMIT = 50000
# Safety cap for the follow-pagination loop; hitting it means incomplete.
_MAX_PAGES = 1000

_META_MARKER = "## Page Content"
# Real chrome-acp line: "- Content: showing chars 0–50000 of 123456" (en dash).
_CONTENT_LINE_RE = re.compile(
    r"Content:\s+showing\s+chars\s+(\d+)\s*[\u2013-]\s*(\d+)\s+of\s+(\d+)",
    re.IGNORECASE,
)
_URL_HEADER_RE = re.compile(r"-\s*URL:\s*(\S+)")

_ALLOWED_KINDS = frozenset({"url_equals", "text_present", "text_absent"})


# ---------------------------------------------------------------------------
# MCP result parsing
# ---------------------------------------------------------------------------

def _content_to_text(content: Any) -> str:
    """Join MCP content blocks (dicts/objects/strings) into one text string."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, (list, tuple)):
        parts: list[str] = []
        for block in content:
            if block is None:
                continue
            if isinstance(block, str):
                parts.append(block)
                continue
            text = getattr(block, "text", None)
            if isinstance(text, str):
                parts.append(text)
                continue
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "".join(parts)
    text = getattr(content, "text", None)
    if isinstance(text, str):
        return text
    if isinstance(content, dict) and isinstance(content.get("text"), str):
        return content["text"]
    return ""


def _explicit_ok(structured: Any, plain: Any = None) -> bool | None:
    """Return an explicit success/failure bool if the result carries one.

    Priority: ``structuredContent.ok``, ``structuredContent.json.ok``, then the
    top-level ``ok`` / ``json.ok``. Only JSON-native booleans count.
    """
    if isinstance(structured, dict):
        value = structured.get("ok")
        if isinstance(value, bool):
            return value
        nested = structured.get("json")
        if isinstance(nested, dict):
            value = nested.get("ok")
            if isinstance(value, bool):
                return value
    if isinstance(plain, dict):
        value = plain.get("ok")
        if isinstance(value, bool):
            return value
        nested = plain.get("json")
        if isinstance(nested, dict):
            value = nested.get("ok")
            if isinstance(value, bool):
                return value
    return None


def parse_tool_result(result: Any) -> dict:
    """Parse tool transport status, never business-task success, without truncation."""
    if isinstance(result, str):
        text, plain = result, {}
    elif isinstance(result, (list, tuple)):
        text, plain = _content_to_text(result), {}
    elif isinstance(result, dict):
        plain = result
        text = _content_to_text(result.get("content")) or result.get("text", "")
    else:
        plain = {key: getattr(result, key, None)
                 for key in ("isError", "structuredContent", "ok", "text")}
        text = _content_to_text(getattr(result, "content", None)) or plain.get("text", "")
    if not isinstance(text, str):
        text = ""
    try:
        decoded = json.loads(text)
    except (ValueError, TypeError):
        decoded = {}
    if not isinstance(decoded, dict):
        decoded = {}
    structured = plain.get("structuredContent")
    data = structured if isinstance(structured, dict) else decoded
    if not data and ("url" in plain or isinstance(plain.get("ok"), bool)):
        data = plain
    explicit = _explicit_ok(structured, decoded or plain)
    is_error = plain.get("isError")
    if is_error is True:
        ok = False
    elif explicit is not None:
        ok = explicit
    elif is_error is False:
        ok = True
    else:
        ok = None
    return {"ok": ok, "text": text, "data": data if isinstance(data, dict) else {}}


def _full_error(exc: BaseException) -> str:
    """Render an exception including its cause chain (full detail, not
    truncated to a single line)."""
    parts = [f"{type(exc).__name__}: {exc}" if str(exc) else f"{type(exc).__name__}"]
    cause = exc.__cause__ or exc.__context__
    if cause is not None and cause is not exc:
        parts.append(
            f"caused by {type(cause).__name__}: {cause}" if str(cause)
            else f"caused by {type(cause).__name__}"
        )
    return " | ".join(parts)


def _tool_name(tool: Any) -> str | None:
    name = tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)
    if isinstance(name, str):
        return name
    if isinstance(tool, str):
        return tool
    return None


async def _server_tools(server: Any) -> list:
    """Tools exposed by one server: ``cached_tools`` when available, otherwise
    a single awaited ``list_tools()`` call (the OpenAI Agents SDK returns
    ``None`` until tools have been listed or when caching is disabled)."""
    cached = None
    try:
        cached = server.cached_tools
    except Exception:  # noqa: BLE001 — test doubles may lack the attribute
        cached = None
    if cached is not None:
        return cached if isinstance(cached, (list, tuple)) else []
    try:
        listed = server.list_tools()
        if inspect.isawaitable(listed):
            listed = await listed
        return listed if isinstance(listed, (list, tuple)) else []
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "list_tools failed for %r: %s",
            getattr(server, "name", server),
            _full_error(exc),
        )
        return []


async def call_browser_tool(servers: Any, name: str, arguments: dict) -> dict:
    """Call ``name`` once on the first server that provably exposes it.

    The tool list comes from ``cached_tools`` (or an awaited ``list_tools()``
    when the cache is ``None``), so unknown servers are never probed by
    brute-force ``call_tool`` attempts. A single call failure on a server that
    does expose the tool returns ``ok=False`` with the full error preserved.
    """
    if servers is None:
        servers = []
    elif not isinstance(servers, (list, tuple)):
        # A single SimpleNamespace/sdk server object is accepted for tests.
        servers = [servers]
    for server in servers:
        tools = await _server_tools(server)
        if not any(_tool_name(tool) == name for tool in tools):
            continue
        try:
            result = await server.call_tool(name, arguments)
        except Exception as exc:  # noqa: BLE001
            parsed = {"ok": False, "text": "", "data": {}, "error": _full_error(exc)}
        else:
            parsed = parse_tool_result(result)
        parsed["tool"] = name
        return parsed
    return {
        "ok": False,
        "text": "",
        "data": {},
        "error": f"no MCP server exposes tool {name!r}",
        "tool": name,
    }


# ---------------------------------------------------------------------------
# Page observation (browser_read with pagination)
# ---------------------------------------------------------------------------

def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _page_url_from_text(text: str) -> str:
    """Exact ``- URL: ...`` header from the Page Info metadata section only —
    a fake ``- URL:`` line inside the page body is never trusted."""
    meta = text.split(_META_MARKER, 1)[0]
    for line in meta.splitlines():
        match = _URL_HEADER_RE.match(line.strip())
        if match:
            return match.group(1).strip()
    return ""


def _page_body_and_marker(text: str) -> tuple[str, int | None, int | None]:
    """Split chrome-acp read text into (body, end, total).

    The body is everything after the ``## Page Content`` header (metadata
    stripped); ``end``/``total`` come from the ``- Content: showing chars
    START–END of TOTAL`` line in the metadata section. Either may be missing.
    """
    idx = text.find(_META_MARKER)
    if idx >= 0:
        meta = text[:idx]
        body = text[idx + len(_META_MARKER):].lstrip("\r\n")
    else:
        meta = text
        body = text
    match = _CONTENT_LINE_RE.search(meta)
    if not match:
        return body, None, None
    return body, int(match.group(2)), int(match.group(3))


def _parse_read_result(result: dict, requested_offset: int) -> dict:
    """Parse one browser_read result into ``{url, body, end, total, structured}``."""
    text = result.get("text") or ""
    data = result.get("data")
    structured = data if isinstance(data, dict) and data else {}
    url = ""
    body = ""
    end: int | None = None
    total: int | None = None

    if structured:
        sc_url = structured.get("url")
        if isinstance(sc_url, str):
            url = sc_url.strip()
        content = structured.get("content")
        if not isinstance(content, str):
            content = structured.get("text")
        if isinstance(content, str):
            body = content
        total = _as_int(structured.get("totalChars"))
        if total is not None:
            end = requested_offset + len(body)
    else:
        url = _page_url_from_text(text)
        body, end, total = _page_body_and_marker(text)
    return {"url": url, "body": body, "end": end, "total": total, "structured": structured}


async def observe_page(servers: Any, tab_id: int) -> dict:
    """Read the full page via paginated ``browser_read``.

    Returns ``{url, text, data, ok, incomplete}`` where ``text`` is the
    accumulated page body (metadata stripped) and ``incomplete`` is True when
    any read failed, the page URL changed mid-read, there was no forward
    progress, or the pagination boundary could not be confirmed — completeness
    is never inferred from the absence of markers.
    """
    offset = 0
    chunks: list[str] = []
    observed_url = ""
    structured: dict = {}

    def snapshot(*, ok: bool | None, incomplete: bool) -> dict:
        return {
            "url": observed_url,
            "text": "".join(chunks),
            "data": structured,
            "ok": ok,
            "incomplete": incomplete,
        }

    for _ in range(_MAX_PAGES):
        result = await call_browser_tool(
            servers, "browser_read",
            {"tabId": tab_id, "offset": offset, "limit": READ_LIMIT},
        )
        if result.get("ok") is False:
            logger.debug("browser_read failed at offset=%d: %s", offset, result.get("error"))
            return snapshot(ok=False, incomplete=True)

        page = _parse_read_result(result, offset)
        url = page["url"]
        if not observed_url and url:
            observed_url = url
            structured = page["structured"]
        elif observed_url and url and url != observed_url:
            logger.debug("page URL changed while reading tab %s", tab_id)
            return snapshot(ok=True, incomplete=True)

        if page["body"]:
            chunks.append(page["body"])

        end, total = page["end"], page["total"]
        if end is None or total is None:
            logger.debug("browser_read pagination boundary missing at offset=%d", offset)
            return snapshot(ok=True, incomplete=True)
        if end >= total:
            return snapshot(ok=True, incomplete=False)
        if end <= offset:
            logger.debug("browser_read made no forward progress at offset=%d", offset)
            return snapshot(ok=True, incomplete=True)
        offset = end

    logger.warning("browser_read pagination exceeded %d pages", _MAX_PAGES)
    return snapshot(ok=True, incomplete=True)


# ---------------------------------------------------------------------------
# Fixed postcondition evaluation
# ---------------------------------------------------------------------------

def _validate_condition(condition: Any) -> str | None:
    """Return an error description, or None when the condition is valid."""
    if not isinstance(condition, dict):
        return "condition must be a dict"
    kind = condition.get("kind")
    if kind not in _ALLOWED_KINDS:
        return f"unsupported condition kind {kind!r} (expected url_equals|text_present|text_absent)"
    value = condition.get("value")
    if not isinstance(value, str) or not value.strip():
        return f"condition {kind!r} requires a non-empty string value"
    if kind == "url_equals" and not (
        value.startswith("http://") or value.startswith("https://")
    ):
        return "url_equals value must start with http:// or https://"
    return None


def _verification_result(status: str, reason: str) -> models.VerificationResult:
    return models.VerificationResult(status=status, reason=reason)


def evaluate_conditions(
    conditions: list[dict],
    observation: dict,
) -> models.VerificationResult:
    """Evaluate fixed postconditions against one page observation (three-state).

    - Empty or invalid criteria, a failed observation, or an incomplete
      observation → ``unknown`` (never ``success``).
    - Complete observation with every condition satisfied → ``success``.
    - Complete observation with any condition clearly unmet → ``failure``.
    """
    if not isinstance(conditions, list) or not conditions:
        return _verification_result("unknown", "no acceptance conditions were provided")
    for condition in conditions:
        error = _validate_condition(condition)
        if error is not None:
            return _verification_result("unknown", f"invalid condition: {error}")

    if not isinstance(observation, dict):
        return _verification_result("unknown", "observation is missing")
    if observation.get("ok") is False:
        return _verification_result("unknown", "observation failed")
    if observation.get("incomplete") is not False:
        return _verification_result("unknown", "observation is incomplete")

    url = observation.get("url") or ""
    text = observation.get("text") or ""
    unmet: list[str] = []
    for condition in conditions:
        kind = condition["kind"]
        value = condition["value"]
        if kind == "url_equals":
            satisfied = url.strip() == value.strip()
        elif kind == "text_present":
            satisfied = value in text
        else:  # text_absent
            satisfied = value not in text
        if not satisfied:
            unmet.append(f"{kind}={value!r}")

    if not unmet:
        return _verification_result(
            "success",
            f"all {len(conditions)} condition(s) satisfied",
        )
    return _verification_result(
        "failure",
        "condition not met: " + "; ".join(unmet),
    )


# ---------------------------------------------------------------------------
# Convenience entry point
# ---------------------------------------------------------------------------

def _empty_observation() -> dict:
    return {"url": "", "text": "", "data": {}, "ok": None, "incomplete": True}


async def verify_conditions(
    servers: Any,
    tab_id: int,
    conditions: list[dict],
) -> tuple[models.VerificationResult, dict]:
    """Observe the page and evaluate conditions; the main executor may also
    call :func:`observe_page` / :func:`evaluate_conditions` directly.

    Without (valid) acceptance conditions the result is conservatively
    ``unknown`` and the page is not read at all.
    """
    if not isinstance(conditions, list) or not conditions:
        reason = "no acceptance conditions were provided"
        return _verification_result("unknown", reason), _empty_observation()
    for condition in conditions:
        error = _validate_condition(condition)
        if error is not None:
            reason = f"invalid condition: {error}"
            return _verification_result("unknown", reason), _empty_observation()

    observation = await observe_page(servers, tab_id)
    return evaluate_conditions(conditions, observation), observation