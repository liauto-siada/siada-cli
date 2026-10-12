"""
Login prompt for unauthenticated users.

The open-source build signs in with the user's own model provider: the only
supported sign-in method is configuring a provider API key (or any other
OpenAI-compatible endpoint), which is persisted to ``~/.siada-cli/conf.yaml``
under ``llm_config`` with ``provider: default``.

Credentials already present in the environment (``BASE_URL`` + ``API_KEY``,
e.g. shell exports or ``--set-env``) are accepted as-is for this process: they
are never persisted and never prompted for, so non-interactive ``--prompt``
runs sign in too. Only a pair that still misses one of the two halves falls
through to the prompt below.

Two entry points share this module:

  * ``ensure_logged_in()`` — first-run sign-in. In ACP mode the frontend
    ``LoginSelector`` is shown with ``liidDisabled`` set (API key only); in TTY
    mode base URL / API key / model are read from stdin.
  * ``reconfigure_acp()`` — the ``/configure`` re-run of the same selector,
    cancelable, without restarting the process.
"""
import os
import sys
import time
from typing import Optional

from siada.foundation.logging import logger

# Set after API-key login; read by siadahub to update runtime provider/model.
_applied_api_key_config: Optional[dict] = None


def get_applied_api_key_config() -> Optional[dict]:
    """Return the API-key provider config applied this session, or None."""
    return _applied_api_key_config


def clear_api_key_config() -> bool:
    """Remove API-key provider config (provider=default) from conf.yaml.

    Returns True if a config was present and successfully cleared."""
    from siada.config.conf_store import get_conf_section, update_conf

    llm_cfg = get_conf_section("llm_config")
    if llm_cfg.get('provider') != 'default':
        return False

    def _remove_provider_keys(data: dict) -> None:
        section = data.get('llm_config')
        if not isinstance(section, dict) or section.get('provider') != 'default':
            return
        for key in ('provider', 'provider_id', 'base_url', 'api_key'):
            section.pop(key, None)
        if section:
            data['llm_config'] = section
        else:
            data.pop('llm_config', None)

    if not update_conf(_remove_provider_keys):
        logger.warning("[login] Failed to clear api key config")
        return False
    logger.info("[login] API key config cleared from conf.yaml")
    return True


def _save_provider_config(provider_id: str, api_key: str, base_url: str, model: str) -> bool:
    """Persist provider API-key config to ~/.siada-cli/conf.yaml.

    Returns True only when the config reached conf.yaml. A failed write must
    reach the caller: reporting a sign-in the next launch cannot reproduce
    (no stored credentials) is worse than failing the prompt.
    """
    from siada.config.conf_store import update_conf

    def _set_provider_config(data: dict) -> None:
        llm_cfg = data.get('llm_config')
        if not isinstance(llm_cfg, dict):
            llm_cfg = {}
            data['llm_config'] = llm_cfg
        llm_cfg['provider'] = 'default'
        llm_cfg['provider_id'] = provider_id
        llm_cfg['base_url'] = base_url
        llm_cfg['api_key'] = api_key
        if model:
            llm_cfg['model'] = model

    if update_conf(_set_provider_config):
        logger.info(f"[login] Provider config saved: provider_id={provider_id}, model={model}")
        return True
    logger.warning("[login] Failed to save provider config")
    return False


def _field_text(value) -> Optional[str]:
    """Return the stripped text of a JSON payload string field.

    ``None`` marks a field whose JSON type is not a string (number, list, …):
    the caller reports it instead of crashing on ``.strip()`` or signing in
    with a half-usable config. Missing fields (``None``) read as empty.
    """
    if value is None:
        return ''
    if isinstance(value, str):
        return value.strip()
    return None


def _save_failed_message() -> str:
    """Error text for a failed conf.yaml write (never contains the API key)."""
    return (
        "Could not save the API key configuration to ~/.siada-cli/conf.yaml. "
        "Check that the file is writable and try again."
    )


def _handle_provider_api_key_config(config_data: dict, io) -> Optional[str]:
    """Handle provider API-key config from a choice-3 JSON payload."""
    global _applied_api_key_config

    provider_id = _field_text(config_data.get('provider_id'))
    api_key = _field_text(config_data.get('api_key'))
    base_url = _field_text(config_data.get('base_url'))
    model = _field_text(config_data.get('model'))

    if provider_id is None or api_key is None or base_url is None or model is None:
        # Wrong JSON types cannot authenticate this build: report them instead
        # of raising (or worse, letting a partial config sign in).
        _send_acp_notification(io, 'ui/loginError', {'error': 'Invalid API key configuration.'})
        return None

    provider_id = provider_id or 'custom'
    if not api_key:
        _send_acp_notification(io, 'ui/loginError', {'error': 'API key cannot be empty.'})
        return None
    if not base_url:
        _send_acp_notification(io, 'ui/loginError', {'error': 'Base URL cannot be empty.'})
        return None

    if not _save_provider_config(provider_id, api_key, base_url, model):
        # Nothing was persisted, so the environment/applied config are left
        # untouched: no fake sign-in, and the key is never echoed back.
        _send_acp_notification(io, 'ui/loginError', {'error': _save_failed_message()})
        return None

    os.environ['BASE_URL'] = base_url
    os.environ['API_KEY'] = api_key

    _applied_api_key_config = {
        'provider_id': provider_id,
        'base_url': base_url,
        'api_key': api_key,
        'model': model,
    }

    user_id = f"api-key-user:{provider_id}"
    _send_acp_notification(io, 'ui/loginSuccess', {'userId': user_id, 'displayName': f'API Key ({provider_id})'})
    logger.info(f"[login] Signed in via provider API key: {user_id}")
    return user_id


def _read_stored_provider_config() -> dict:
    """Return conf.yaml's sanitized ``llm_config`` for a default provider.

    Returns {} when the section is absent, not a mapping, or belongs to another
    provider, so callers can treat "nothing stored" and "not our provider"
    identically. Never raises: a credential check must not crash an entry point.

    conf.yaml is user-editable, so every field is filtered through
    ``_field_text``: a value of the wrong YAML type (number, list, …) reads as
    missing (''), never as a credential, and can never break a caller with
    ``.strip()``. The returned dict therefore always carries strings only.
    """
    try:
        from siada.config.conf_store import get_conf_section

        llm_cfg = get_conf_section("llm_config")
    except Exception as exc:
        logger.debug(f"[login] Could not read stored provider config: {exc}")
        return {}
    if llm_cfg.get('provider') != 'default':
        return {}
    return {
        'provider_id': _field_text(llm_cfg.get('provider_id')) or 'configured',
        'base_url': _field_text(llm_cfg.get('base_url')) or '',
        'api_key': _field_text(llm_cfg.get('api_key')) or '',
        'model': _field_text(llm_cfg.get('model')) or '',
    }


def _resolve_session_credentials() -> Optional[tuple[dict, str]]:
    """Resolve the credentials that authenticate this session, or None.

    ``BASE_URL``/``API_KEY`` already present in the environment (shell exports,
    ``--set-env``, or the values ``get_config()`` pre-loads from conf.yaml) are
    the explicit per-invocation configuration and take priority over the stored
    ``llm_config`` — the same priority model setup resolves them with.
    conf.yaml still supplies whichever half the environment leaves empty; a
    pair that is incomplete even after that (e.g. an API key with no endpoint)
    is rejected so the login prompt/selector below still runs instead of
    reporting a fake sign-in.

    Stored fields arrive already sanitized (see
    ``_read_stored_provider_config``), so bad YAML types read as missing: a
    complete environment pair still signs in even next to a corrupt stored
    config, and a stored pair with a wrongly-typed half never does.

    Returns ``(applied_config, synthetic_user_id)``. The api key is carried for
    the running model only: it is never logged and, for environment
    credentials, never persisted either.
    """
    stored = _read_stored_provider_config()
    stored_base_url = stored.get('base_url') or ''
    stored_api_key = stored.get('api_key') or ''

    base_url = (os.environ.get('BASE_URL') or '').strip() or stored_base_url
    api_key = (os.environ.get('API_KEY') or '').strip() or stored_api_key
    if not base_url or not api_key:
        return None

    if base_url == stored_base_url and api_key == stored_api_key:
        # conf.yaml alone supplied the credentials (the environment either
        # mirrors it or did not provide them): keep the stored provider
        # identity and the model the user configured with the wizard.
        return (
            {
                'provider_id': stored.get('provider_id') or 'configured',
                'base_url': base_url,
                'api_key': api_key,
                'model': stored.get('model') or '',
            },
            'api-key-configured',
        )

    # The credentials came (at least partly) from the environment, which names
    # neither a provider nor a model. The empty model keeps ``_apply_login()``
    # from overriding the model ``--model`` / conf.yaml already selected.
    provider_id = 'configured'
    return (
        {
            'provider_id': provider_id,
            'base_url': base_url,
            'api_key': api_key,
            'model': '',
        },
        f'api-key-user:{provider_id}',
    )


def _is_interactive_tty() -> bool:
    """Return True if running in an interactive TTY."""
    return sys.stdin.isatty() and sys.stdout.isatty()


# --- ACP mode ---

def _read_acp_stdin_message() -> Optional[str]:
    """Read one ACP message from stdin (delimited by SIADA_MSG_START/END).

    In ACP mode the StdinInterruptMonitor owns stdin and drains it byte-by-byte
    into an internal queue. Reading sys.stdin directly here can therefore block
    forever (or only see EOF) because the monitor has already consumed the
    bytes. To stay compatible with both monitored and direct stdin modes, read
    through the monitor when it is active.

    An empty read means different things in the two modes and must not be
    conflated:

      * active monitor — ``readline(timeout=…)`` returned no data yet: keep
        polling. No overall wait timeout is applied here on purpose: the
        frontend may take arbitrarily long over a login configuration, and
        giving up would abort a reply that is still on its way.
      * unmonitored stdin (a pipe) — ``readline()`` only returns '' at EOF:
        raise EOFError so the caller can report a closed/cancelled login
        instead of spinning forever.

    Raises:
        EOFError: unmonitored stdin reached EOF (the pipe/frontend is gone).
    """
    from siada.io.stdin_interrupt_monitor import is_monitor_active, get_stdin_monitor

    def _read_line() -> str:
        if is_monitor_active():
            return get_stdin_monitor().readline(timeout=0.1)
        line = sys.stdin.readline()
        if not line:
            raise EOFError("ACP stdin reached EOF")
        return line

    while True:
        line = _read_line()
        if not line:
            # Monitor poll timeout (no data yet): keep waiting for the choice.
            time.sleep(0.05)
            continue
        if line.strip() == "<<<SIADA_MSG_START>>>":
            parts: list[str] = []
            while True:
                content = _read_line()
                if not content:
                    # Same distinction as above: a monitor timeout mid-frame
                    # keeps polling, while unmonitored EOF inside the frame
                    # propagates as EOFError from _read_line().
                    time.sleep(0.05)
                    continue
                if content.strip() == "<<<SIADA_MSG_END>>>":
                    break
                parts.append(content.rstrip("\n"))
            logger.info("[login_acp] Received ACP stdin message: %d lines", len(parts))
            return "\n".join(parts).strip()


def _send_acp_notification(io, method: str, params: dict) -> None:
    """Send a custom ACP notification to the frontend."""
    try:
        from siada.io.acp.message_builder import ACPMessageBuilder
        msg = ACPMessageBuilder().build_custom_notification(method=method, params=params)
        io.acp_adapter.transport.send_sync(msg)
    except Exception as exc:
        logger.warning(f"[login_acp] Failed to send {method}: {exc}")


def _acp_transport_connected(io) -> bool:
    """Return True when the frontend transport can receive login notifications."""
    return bool(
        hasattr(io, "acp_adapter") and io.acp_adapter
        and hasattr(io.acp_adapter, "transport") and io.acp_adapter.transport
        and getattr(io.acp_adapter.transport, "is_connected", False)
    )


def _ensure_logged_in_acp(io) -> Optional[str]:
    """ACP-mode sign-in: show the frontend LoginSelector and read the choice.

    The API key wizard is the only method offered in this build, so the
    selector is sent with ``liidDisabled`` set — the frontend then renders the
    provider/model/API-key flow alone (the ``liidDisabled`` flag is the existing
    frontend compatibility contract for "no hosted sign-in in this build").

    Returns the synthetic ``api-key-user:<provider_id>`` id on success (after
    saving the config and notifying the frontend), or None when the user could
    not complete the wizard.
    """
    if not _acp_transport_connected(io):
        logger.warning("[login_acp] ACP transport not connected, cannot perform login")
        return None

    try:
        from siada.provider.models_dev import get_providers_for_ui
        providers_data = get_providers_for_ui()
    except Exception:
        providers_data = []

    _send_acp_notification(io, "ui/showLoginSelector", {
        "providers": providers_data,
        "liidDisabled": True,
    })
    logger.info(
        "[login_acp] Sent ui/showLoginSelector with %d providers (API key only)",
        len(providers_data),
    )

    try:
        raw = _read_acp_stdin_message()
    except (EOFError, KeyboardInterrupt):
        _send_acp_notification(io, "ui/loginError", {"error": "Login is required to use Siada."})
        return None

    if not raw or not raw.startswith("__LOGIN_CHOICE__:"):
        _send_acp_notification(io, "ui/loginError", {"error": "Login is required to use Siada."})
        return None

    parts = raw.split(":", 2)
    choice = parts[1] if len(parts) >= 2 else ""

    if choice == "3":
        payload_str = parts[2].strip() if len(parts) >= 3 else ""
        if not payload_str:
            _send_acp_notification(io, "ui/loginError", {"error": "API key cannot be empty."})
            return None
        try:
            import json as _json
            config_data = _json.loads(payload_str)
            if isinstance(config_data, dict) and "provider_id" in config_data:
                return _handle_provider_api_key_config(config_data, io)
        except (ValueError, TypeError):
            pass
        _send_acp_notification(io, "ui/loginError", {
            "error": "Invalid API key configuration.",
        })
        return None

    # Hosted sign-in is not part of this build, and the selector only offers the
    # API key wizard; treat any other choice as an abandoned login.
    _send_acp_notification(io, "ui/loginError", {
        "error": "Login is required to use Siada. Please configure an API key."
    })
    logger.warning("[login_acp] Unsupported login choice %r — API key required", choice)
    return None


def _ensure_logged_in_tty(io) -> Optional[str]:
    """TTY-mode sign-in: read base URL / API key / model from stdin.

    Reached only when neither the environment nor conf.yaml provides a complete
    credential pair; a non-interactive shell (``--prompt`` runs) therefore
    cannot sign in here and returns None.

    Returns the synthetic ``api-key-user:configured`` id on success, or None
    when the user cannot sign in (non-interactive shell, empty base URL/API
    key, or a conf.yaml write failure).
    """
    if not _is_interactive_tty():
        logger.info("[login] Non-interactive environment, login required but not possible")
        return None

    io.print_info("")
    io.print_info("You are not signed in. Configure your model provider to use Siada.")
    io.print_info("")

    try:
        base_url = input("Base URL (e.g. https://api.openai.com/v1): ").strip()
        import getpass
        api_key = getpass.getpass("API key: ").strip()
        model = input("Model (optional, press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        io.print_info("\nLogin is required to use Siada. Exiting.")
        sys.exit(1)

    if not base_url:
        io.print_error("Base URL cannot be empty.")
        return None
    if not api_key:
        io.print_error("API key cannot be empty.")
        return None

    provider_id = "configured"
    if not _save_provider_config(provider_id, api_key, base_url, model):
        # Nothing was persisted: keep the environment and the applied config
        # untouched instead of reporting a sign-in that would not survive.
        io.print_error(_save_failed_message())
        return None

    os.environ['BASE_URL'] = base_url
    os.environ['API_KEY'] = api_key

    global _applied_api_key_config
    _applied_api_key_config = {
        'provider_id': provider_id,
        'base_url': base_url,
        'api_key': api_key,
        'model': model,
    }

    user_id = f"api-key-user:{provider_id}"
    io.print_info(f"API key configured for {provider_id}.")
    logger.info(f"[login] Signed in via provider API key: {user_id}")
    return user_id


# --- Public entry points ---

def reconfigure_acp(io) -> Optional[str]:
    """Reconfiguration flow triggered by /configure (ACP mode).

    Always shows the LoginSelector (skips the stored-config fast path) and
    supports cancel. Like the first-run selector it is API-key only, so
    ``liidDisabled`` is always set.

    Returns:
        'api-key-user:{provider_id}' when the user configured a new API key,
        or None when the user cancelled or the input could not be used.
    """
    if not _acp_transport_connected(io):
        logger.warning("[reconfigure_acp] ACP transport not connected")
        return None

    try:
        from siada.provider.models_dev import get_providers_for_ui
        providers_data = get_providers_for_ui()
    except Exception:
        providers_data = []

    _send_acp_notification(io, "ui/showLoginSelector", {
        "providers": providers_data,
        # cancelable=True so the frontend shows an Esc-to-cancel hint
        "cancelable": True,
        "liidDisabled": True,
    })

    try:
        raw = _read_acp_stdin_message()
    except (EOFError, KeyboardInterrupt):
        _send_acp_notification(io, "ui/loginDismiss", {})
        return None

    if not raw or not raw.startswith("__LOGIN_CHOICE__:"):
        _send_acp_notification(io, "ui/loginDismiss", {})
        return None

    parts = raw.split(":", 2)
    choice = parts[1] if len(parts) >= 2 else ""

    if choice in ("cancel", "skip"):
        _send_acp_notification(io, "ui/loginDismiss", {})
        logger.info("[reconfigure_acp] Cancelled by user")
        return None

    # Option 3: provider API key
    if choice == "3":
        payload_str = parts[2].strip() if len(parts) >= 3 else ""
        if not payload_str:
            _send_acp_notification(io, "ui/loginDismiss", {})
            return None
        try:
            import json as _json
            config_data = _json.loads(payload_str)
            if isinstance(config_data, dict) and "provider_id" in config_data:
                return _handle_provider_api_key_config(config_data, io)
        except (ValueError, TypeError):
            pass
        _send_acp_notification(io, "ui/loginDismiss", {})
        return None

    # Only the API key wizard is offered (liidDisabled); nothing else can be
    # applied, so leave the previous configuration untouched.
    _send_acp_notification(io, "ui/loginError", {
        "error": "Login is required to use Siada. Please configure an API key."
    })
    logger.warning("[reconfigure_acp] Unsupported login choice %r", choice)
    return None


def ensure_logged_in(io, acp_mode: bool = False) -> Optional[str]:
    """Verify login state and prompt the user to sign in if needed.

    Credentials resolved from the environment (``BASE_URL``/``API_KEY``) or from
    conf.yaml sign the session in without any prompt — including non-interactive
    ``--prompt`` runs; a partial pair falls through to the prompt/selector.

    Args:
        io: InputOutput instance.
        acp_mode: True to interact via frontend LoginSelector; False for TTY input().

    Returns:
        Synthetic api-key user_id, or None when the environment cannot sign in.
    """
    global _applied_api_key_config

    # Never reuse credentials applied by an earlier call: when this attempt
    # fails, the caller must see "not signed in", not a stale config.
    _applied_api_key_config = None

    resolved = _resolve_session_credentials()
    if resolved is not None:
        applied, user_id = resolved
        _applied_api_key_config = applied
        os.environ['BASE_URL'] = applied['base_url']
        os.environ['API_KEY'] = applied['api_key']
        logger.info(
            "[login] Signed in as %s (provider_id=%s, model=%s)",
            user_id, applied['provider_id'], applied['model'] or '-',
        )
        return user_id

    if acp_mode:
        return _ensure_logged_in_acp(io)
    return _ensure_logged_in_tty(io)
