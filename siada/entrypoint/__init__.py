"""
Siada Hub 命令行工具入口点
"""
from siada.foundation.logging import logger


_TOKEN_REFRESH_REGISTERED = False
_CURRENT_PROVIDER: str = ""


def set_current_provider(provider: str) -> None:
    """Set the current active provider. Called from model_setup after provider is resolved."""
    global _CURRENT_PROVIDER
    _CURRENT_PROVIDER = provider or ""


def _normalize_empty_assistant_content(messages) -> None:
    """Normalize empty text content on assistant messages to None, in place, so
    litellm never has a reason to invoke its Anthropic empty-text placeholder.

    Two shapes need handling, both of which legitimately arise from
    ``agents.models.chatcmpl_converter.Converter.items_to_messages()`` (see
    ``siada/internal/provider/li/li_provider.py::LiModel._fetch_response``):

    1. ``content`` is an empty/whitespace-only string — the common case for a
       pure tool-call assistant turn (no text output), or a message item whose
       only ``output_text`` block was itself empty (e.g. an interrupted stream,
       or a text block emitted alongside a tool call with no text).
    2. ``content`` is a list of content blocks — e.g. when
       ``preserve_thinking_blocks`` wraps the string content into
       ``[<thinking blocks>, {"type": "text", "text": ...}]`` for Claude
       extended-thinking calls — that contains an empty/whitespace-only
       ``{"type": "text", "text": ""}`` block alongside otherwise-valid blocks
       (thinking blocks, tool_use, etc.). This shape is NOT caught by a plain
       ``isinstance(content, str)`` check, which is exactly how the empty text
       previously slipped past this function and reached litellm's own
       sanitizer.

    If content is left empty in either shape, litellm's Anthropic request
    transform (`_sanitize_empty_text_content`) rewrites it into a placeholder
    text block (e.g. "[System: Empty message content sanitised to satisfy
    protocol]") every time this message is sent/replayed, which then leaks into
    persisted/rendered output — the model itself sees this placeholder as part
    of its own conversation history and can echo it back verbatim on the next
    turn, which is what actually renders in the UI. Dropping the empty text
    entirely — instead of letting litellm inject its own placeholder — makes
    litellm skip adding any text block, matching Claude's own native response
    shape (thinking/tool_use blocks only).

    Setting ``content`` to ``None`` is only safe when the message still has
    ``tool_calls``: per the OpenAI chat-completions schema, an assistant turn
    is valid with ``content=None`` as long as ``tool_calls`` is non-empty
    (that's the normal "pure tool-call, no text" shape). When there is no
    text AND no tool call, the message carries no information at all -- e.g.
    a stream interrupted mid-turn before any text or tool call was emitted.
    Some OpenAI-compatible providers (observed with Moonshot/Kimi) reject
    such a message outright with "the message ... must not be empty",
    regardless of whether ``content`` is ``""`` or ``None``. There is no
    valid non-empty placeholder we can safely inject without risking the
    model echoing it back (the very problem this function exists to avoid
    for Anthropic), so in that case we drop the message from the history
    entirely instead of leaving a still-invalid empty/None placeholder.
    """
    if not messages:
        return

    indices_to_drop: list[int] = []

    for idx, m in enumerate(messages):
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue

        content = m.get("content")
        has_tool_calls = bool(m.get("tool_calls"))

        # content already None/missing: valid only when tool_calls are
        # present (pure tool-call turn); otherwise the message carries no
        # information and must be dropped, same as the empty-string case.
        if content is None:
            if not has_tool_calls:
                indices_to_drop.append(idx)
            continue

        if isinstance(content, str):
            if not content.strip():
                if has_tool_calls:
                    m["content"] = None
                else:
                    indices_to_drop.append(idx)
            continue

        if isinstance(content, list):
            cleaned = [
                block
                for block in content
                if not (
                    isinstance(block, dict)
                    and block.get("type") == "text"
                    and not (block.get("text") or "").strip()
                )
            ]
            if len(cleaned) != len(content):
                if cleaned:
                    m["content"] = cleaned
                elif has_tool_calls:
                    m["content"] = None
                else:
                    indices_to_drop.append(idx)

    # Remove genuinely-empty assistant turns (no text, no tool_calls) in
    # place, highest index first so earlier indices stay valid.
    for idx in reversed(indices_to_drop):
        del messages[idx]



def _configure_litellm():
    """Configure LiteLLM global logging settings to suppress debug logs"""
    try:
        import litellm

        # Configure litellm global properties
        litellm.set_verbose = False
        litellm.turn_off_message_logging = True
        litellm.suppress_debug_info = True
        litellm.drop_params = True
        litellm.num_retries = 3

        # Try to disable internal debug logging
        try:
            litellm._logging._disable_debugging()
        except Exception:
            pass  # Ignore if method doesn't exist

        # Disable message logging and tracing
        litellm.turn_off_message_logging = True
        litellm.success_callback = []
        litellm.failure_callback = []

        # Register token-refresh callback that fires before every deployment
        # call (including retries), ensuring each attempt gets a fresh token.
        _register_token_refresh_callback()

        logger.debug(" logging configuration completed")

    except ImportError:
        logger.debug(" not installed, skipping logging configuration")
    except Exception as e:
        logger.debug(f"Error configuring  logging: {e}")


def _register_token_refresh_callback():
    """Register a litellm callback that refreshes auth token before each call."""
    global _TOKEN_REFRESH_REGISTERED
    if _TOKEN_REFRESH_REGISTERED:
        return

    import litellm
    from litellm.integrations.custom_logger import CustomLogger

    # Resolve the internal IDaaS dependency once at registration time instead
    # of importing on every call. It only exists in internal builds; in the
    # open-source build the hook below degrades to the generic
    # message-normalization only.
    try:
        from siada.internal.services.idaas.auth_store import (
            ensure_valid_auth as _ensure_valid_auth,
            generate_dedup_token as _generate_dedup_token,
        )
    except ImportError:
        _ensure_valid_auth = None
        _generate_dedup_token = None

    class _SiadaTokenRefreshCallback(CustomLogger):
        async def async_pre_call_deployment_hook(self, kwargs, call_type):
            _normalize_empty_assistant_content(kwargs.get("messages"))

            # IDaaS token injection is internal-only.
            if _ensure_valid_auth is None:
                return kwargs

            from siada.entrypoint import _CURRENT_PROVIDER
            # Skip IDaaS auth when the active provider is 'default'.
            # Users who configure 'default' provider supply their own base_url + API key;
            # injecting IDaaS (li) tokens into those calls is wrong and causes failures
            # when the IDaaS refresh token has expired.
            # Exception: internal li-proxy calls (e.g. memory service) always use
            # api_key="li" (set by SiadaClient) regardless of the main provider —
            # those still need IDaaS auth.
            if _CURRENT_PROVIDER == "default" and kwargs.get("api_key") != "li":
                return kwargs

            _user_id, _access_token = await _ensure_valid_auth()

            # Debug: log a safe token fingerprint so we can correlate retries
            # and determine whether the refresh actually rotated the token.
            # Only the head/tail 6 chars are emitted to avoid leaking secrets.
            if _access_token:
                _token_sig = f"{_access_token[:6]}..{_access_token[-6:]}"
            else:
                _token_sig = "<empty>"
            _call_uuid = (kwargs.get("extra_headers") or {}).get("uuid", "")
            logger.info(
                "[token-hook] uid=%s token=%s call_type=%s uuid=%s",
                _user_id,
                _token_sig,
                call_type,
                _call_uuid,
            )

            merged = {
                **(kwargs.get("extra_headers") or {}),
                "X-Siada-User-ID": _user_id,
                "X-Siada-Token": _access_token,
                "X-Siada-Dedup": _generate_dedup_token(),
            }
            # httpx rejects None header values with
            # "Header value must be str or bytes, not <class 'NoneType'>".
            # Drop any None-valued entries here to protect every provider
            # (Anthropic/Claude is strictest).
            kwargs["extra_headers"] = {
                k: v for k, v in merged.items() if v is not None
            }
            return kwargs

    if not any(
        type(cb).__name__ == "_SiadaTokenRefreshCallback"
        for cb in litellm.callbacks
    ):
        litellm.callbacks.append(_SiadaTokenRefreshCallback())
    _TOKEN_REFRESH_REGISTERED = True
