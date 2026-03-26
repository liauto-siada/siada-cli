"""
Login prompt for unauthenticated users.

Presents three options:
  1. Sign in with LiId        — opens browser for OAuth authorization
  2. Sign in with Device Code — prints URL, works without a browser/display
  3. Configure API Key        — enter a provider API key (kimi/openai/claude etc.)

On success the domain account (leg) is written to ~/.siada-cli/conf.yaml
for telemetry and subsequent session use.
"""
import os
import sys
import time
from typing import Optional

from siada.foundation.logging import logger

try:
    import siada.internal.services.idaas.auth_store 
    _HAS_INTERNAL = True
except ImportError:
    _HAS_INTERNAL = False
    logger.warning("siada.internal not available: IDaaS login is disabled.")

# Set after API-key login; read by siadahub to update runtime provider/model.
_applied_api_key_config: Optional[dict] = None


def get_applied_api_key_config() -> Optional[dict]:
    """Return the API-key provider config applied this session, or None."""
    return _applied_api_key_config


def clear_api_key_config() -> bool:
    """Remove API-key provider config (provider=default) from conf.yaml.

    Returns True if a config was present and successfully cleared."""
    try:
        import yaml
        from siada.foundation.constants import SIADA_HOME
        conf_path = SIADA_HOME / 'conf.yaml'
        if not conf_path.exists():
            return False
        with open(conf_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        llm_cfg = data.get('llm_config')
        if not isinstance(llm_cfg, dict) or llm_cfg.get('provider') != 'default':
            return False
        for key in ('provider', 'provider_id', 'base_url', 'api_key'):
            llm_cfg.pop(key, None)
        if llm_cfg:
            data['llm_config'] = llm_cfg
        else:
            data.pop('llm_config', None)
        with open(conf_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
        logger.info("[login] API key config cleared from conf.yaml")
        return True
    except Exception as exc:
        logger.warning(f"[login] Failed to clear api key config: {exc}")
        return False


def _save_provider_config(provider_id: str, api_key: str, base_url: str, model: str) -> None:
    """Persist provider API-key config to ~/.siada-cli/conf.yaml."""
    try:
        import yaml
        from siada.foundation.constants import SIADA_HOME
        conf_path = SIADA_HOME / 'conf.yaml'
        SIADA_HOME.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if conf_path.exists():
            with open(conf_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f) or {}
        llm_cfg = dict(data.get('llm_config') or {})
        llm_cfg['provider'] = 'default'
        llm_cfg['provider_id'] = provider_id
        llm_cfg['base_url'] = base_url
        llm_cfg['api_key'] = api_key
        if model:
            llm_cfg['model'] = model
        data['llm_config'] = llm_cfg
        with open(conf_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
        logger.info(f"[login] Provider config saved: provider_id={provider_id}, model={model}")
    except Exception as exc:
        logger.warning(f"[login] Failed to save provider config: {exc}")


def _handle_provider_api_key_config(config_data: dict, io) -> Optional[str]:
    """Handle provider API-key config from a choice-3 JSON payload."""
    global _applied_api_key_config

    provider_id = config_data.get('provider_id', 'custom')
    api_key = (config_data.get('api_key') or '').strip()
    base_url = (config_data.get('base_url') or '').strip()
    model = (config_data.get('model') or '').strip()

    if not api_key:
        _send_acp_notification(io, 'ui/loginError', {'error': 'API key cannot be empty.'})
        return None

    _save_provider_config(provider_id, api_key, base_url, model)

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


def _check_stored_api_key_config() -> Optional[str]:
    """Check conf.yaml for a stored default-provider config.

    If found, applies credentials to the environment and returns a synthetic
    user_id so LiId login is skipped.
    """
    global _applied_api_key_config
    try:
        import yaml
        from siada.foundation.constants import SIADA_HOME
        conf_path = SIADA_HOME / 'conf.yaml'
        if not conf_path.exists():
            return None
        with open(conf_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
        llm_cfg = data.get('llm_config') or {}
        if (llm_cfg.get('provider') == 'default'
                and llm_cfg.get('base_url')
                and llm_cfg.get('api_key')):
            os.environ['BASE_URL'] = llm_cfg['base_url']
            os.environ['API_KEY'] = llm_cfg['api_key']
            _applied_api_key_config = {
                'provider_id': llm_cfg.get('provider_id', 'configured'),
                'base_url': llm_cfg['base_url'],
                'api_key': llm_cfg['api_key'],
                'model': llm_cfg.get('model', ''),
            }
            logger.info("[login] Found stored API key config, using default provider")
            return 'api-key-configured'
        return None
    except Exception as exc:
        logger.debug(f"[login] _check_stored_api_key_config error: {exc}")
        return None


def _is_interactive_tty() -> bool:
    """Return True if running in an interactive TTY."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def _refresh_telemetry(user_id: str) -> None:
    try:
        from siada.internal.foundation.telemetry import telemetry
        telemetry.config.user_id = user_id
    except Exception:
        pass


def _save(
    user_id: str,
    access_token: str,
    io,
    refresh_token: Optional[str] = None,
    email: Optional[str] = None,
    email_refresh_token: Optional[str] = None,
) -> None:
    if not _HAS_INTERNAL:
        return
    from siada.internal.services.idaas.auth_store import save_login_state
    try:
        save_login_state(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            email=email,
            email_refresh_token=email_refresh_token,
        )
    except Exception as exc:
        io.print_warning(f"Could not save login state: {exc}")


def _extract_user_from_token(access_token: str) -> Optional[str]:
    """Extract user identity (leg/sub/username) from a JWT access token, or None on failure."""
    import base64
    import json
    try:
        parts = access_token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        padding = (4 - len(payload_b64) % 4) % 4
        payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return (
            payload.get("leg")
            or payload.get("sub")
            or payload.get("username")
        )
    except Exception:
        return None


# --- ACP mode ---

def _read_acp_stdin_message() -> Optional[str]:
    """Read one ACP message from stdin (delimited by SIADA_MSG_START/END).

    In ACP mode the StdinInterruptMonitor owns stdin and drains it byte-by-byte
    into an internal queue. Reading sys.stdin directly here can therefore block
    forever (or only see EOF) because the monitor has already consumed the
    bytes. To stay compatible with both monitored and direct stdin modes, read
    through the monitor when it is active.
    """
    from siada.io.stdin_interrupt_monitor import is_monitor_active, get_stdin_monitor

    def _read_line() -> str:
        if is_monitor_active():
            return get_stdin_monitor().readline(timeout=0.1)
        return sys.stdin.readline()

    while True:
        line = _read_line()
        if not line:
            time.sleep(0.05)
            continue
        if line.strip() == "<<<SIADA_MSG_START>>>":
            parts: list[str] = []
            while True:
                content = _read_line()
                if not content:
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


def _ensure_logged_in_acp_apikey_only(io) -> Optional[str]:
    """ACP fallback when siada.internal is absent: only provider API key is available."""
    if not (hasattr(io, "acp_adapter") and io.acp_adapter
            and hasattr(io.acp_adapter, "transport") and io.acp_adapter.transport
            and getattr(io.acp_adapter.transport, "is_connected", False)):
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
    logger.info("[login_acp] internal unavailable — showing API-key-only selector")

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
        "error": "LiId login is not available in this build. Please use an API key."
    })
    return None


def _ensure_logged_in_tty_apikey_only(io) -> Optional[str]:
    """TTY fallback when siada.internal is absent: prompt for base_url/api_key/model."""
    if not _is_interactive_tty():
        return None

    io.print_info("")
    io.print_info("LiId login is not available in this build. Please configure an API key.")
    io.print_info("")

    try:
        base_url = input("Base URL (e.g. https://api.openai.com/v1): ").strip()
        import getpass
        api_key = getpass.getpass("API key: ").strip()
        model = input("Model (optional, press Enter to skip): ").strip()
    except (EOFError, KeyboardInterrupt):
        io.print_info("\nLogin is required to use Siada. Exiting.")
        sys.exit(1)

    if not api_key:
        io.print_error("API key cannot be empty.")
        return None

    provider_id = "configured"
    _save_provider_config(provider_id, api_key, base_url, model)
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
    return user_id


def _ensure_logged_in_acp(io) -> Optional[str]:
    """ACP-mode login: interact via frontend LoginSelector, then run Device Code Flow."""
    if not _HAS_INTERNAL:
        return _ensure_logged_in_acp_apikey_only(io)

    from siada.internal.services.idaas.auth_store import (
        get_stored_user_id, get_stored_access_token, get_stored_refresh_token,
        is_token_valid, save_login_state,
    )

    user_id = get_stored_user_id()
    if user_id:
        access_token = get_stored_access_token()
        if access_token and is_token_valid(access_token):
            logger.debug(f"[login_acp] Already logged in as: {user_id}")
            return user_id
        # Token expired — try refresh_token silently before showing login UI
        refresh_token = get_stored_refresh_token()
        if refresh_token:
            try:
                from siada.internal.services.idaas.refresh_token import sync_refresh_access_token
                new_at, new_rt = sync_refresh_access_token(refresh_token)
                save_login_state(user_id, new_at, new_rt or refresh_token)
                logger.info(f"[login_acp] Token silently refreshed for {user_id}")
                return user_id
            except Exception as exc:
                logger.info(f"[login_acp] Silent refresh failed ({exc}), proceeding to login UI")
        logger.info(f"[login_acp] Stored token for {user_id} has expired, re-authenticating")

    if not (hasattr(io, "acp_adapter") and io.acp_adapter
            and hasattr(io.acp_adapter, "transport") and io.acp_adapter.transport
            and getattr(io.acp_adapter.transport, "is_connected", False)):
        logger.warning("[login_acp] ACP transport not connected, cannot perform login")
        return None

    # Send login selector with available providers to the frontend.
    try:
        from siada.provider.models_dev import get_providers_for_ui
        providers_data = get_providers_for_ui()
    except Exception:
        providers_data = []
    _send_acp_notification(io, "ui/showLoginSelector", {"providers": providers_data})
    logger.info("[login_acp] Sent ui/showLoginSelector with %d providers", len(providers_data))

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

    if choice == "skip":
        _send_acp_notification(io, "ui/loginError", {"error": "Login is required to use Siada. Please sign in."})
        logger.warning("[login_acp] User attempted to skip login, which is not allowed")
        return None

    # Choice 3: provider API key (JSON payload) or legacy LiId access token.
    if choice == "3":
        payload_str = parts[2].strip() if len(parts) >= 3 else ""
        if not payload_str:
            _send_acp_notification(io, "ui/loginError", {"error": "API key cannot be empty."})
            return None

        try:
            import json as _json
            config_data = _json.loads(payload_str)
            if isinstance(config_data, dict) and 'provider_id' in config_data:
                return _handle_provider_api_key_config(config_data, io)
        except (ValueError, TypeError):
            pass

        # Fallback: treat payload as a legacy LiId access token.
        api_key = payload_str
        from siada.internal.services.idaas.auth_store import is_token_valid
        if not is_token_valid(api_key):
            _send_acp_notification(io, "ui/loginError", {"error": "Invalid or expired API key."})
            return None

        user_id = _extract_user_from_token(api_key)
        if not user_id:
            _send_acp_notification(io, "ui/loginError", {"error": "Could not extract user identity from the provided API key."})
            return None

        _save(user_id, api_key, io)
        _refresh_telemetry(user_id)
        _send_acp_notification(io, "ui/loginSuccess", {"userId": user_id, "displayName": user_id})
        logger.info(f"[login_acp] Signed in via LiId API key: {user_id}")
        return user_id

    open_browser = choice == "1"
    logger.info(f"[login_acp] choice={choice}, open_browser={open_browser}")

    # Run Device Code Flow.
    try:
        from siada.internal.services.idaas.get_device_code import get_device_code
        from siada.internal.services.idaas.get_auth_token import poll_auth_token, AuthExpiredError, AuthFailedError
        from siada.internal.services.idaas.get_user import decode_id_token

        device = get_device_code()
        url = device.verification_uri_complete
        _send_acp_notification(io, "ui/loginDeviceUrl", {"url": url, "openBrowser": open_browser})
        logger.info(f"[login_acp] Sent ui/loginDeviceUrl: {url}")

        auth_token = poll_auth_token(device.device_code, device.interval)
        user = decode_id_token(auth_token.id_token)

    except (AuthExpiredError, AuthFailedError) as exc:
        _send_acp_notification(io, "ui/loginError", {"error": str(exc)})
        io.print_error(f"Login failed: {exc}")
        return None
    except KeyboardInterrupt:
        _send_acp_notification(io, "ui/loginError", {"error": "Login is required to use Siada."})
        return None
    except Exception as exc:
        _send_acp_notification(io, "ui/loginError", {"error": str(exc)})
        logger.exception("[login_acp] Unexpected error")
        return None

    if not user.leg:
        _send_acp_notification(io, "ui/loginError", {"error": "No domain account (leg) in token"})
        return None

    from siada.internal.services.idaas.get_user import fetch_email
    email = fetch_email(auth_token.access_token)
    email_refresh_token = auth_token.refresh_token

    _save(
        user.leg, auth_token.access_token, io,
        refresh_token=auth_token.refresh_token,
        email=email or None,
        email_refresh_token=email_refresh_token,
    )
    _refresh_telemetry(user.leg)

    display_name = user.nickname if user.nickname else user.leg
    _send_acp_notification(io, "ui/loginSuccess", {"userId": user.leg, "displayName": display_name})
    logger.info(f"[login_acp] Login successful: {user.leg}")
    return user.leg


# --- TTY mode ---

def _ensure_logged_in_tty(io) -> Optional[str]:
    """TTY-mode login: uses input() interactively; login cannot be skipped."""
    if not _HAS_INTERNAL:
        return _ensure_logged_in_tty_apikey_only(io)

    from siada.internal.services.idaas.auth_store import (
        get_stored_user_id, get_stored_access_token, get_stored_refresh_token,
        is_token_valid, save_login_state,
    )

    user_id = get_stored_user_id()
    if user_id:
        access_token = get_stored_access_token()
        if access_token and is_token_valid(access_token):
            logger.debug(f"[login] Already logged in as: {user_id}")
            return user_id
        # Token expired — try refresh_token silently before showing login menu
        refresh_token = get_stored_refresh_token()
        if refresh_token:
            try:
                from siada.internal.services.idaas.refresh_token import sync_refresh_access_token
                new_at, new_rt = sync_refresh_access_token(refresh_token)
                save_login_state(user_id, new_at, new_rt or refresh_token)
                logger.info(f"[login] Token silently refreshed for {user_id}")
                return user_id
            except Exception as exc:
                logger.info(f"[login] Silent refresh failed ({exc}), proceeding to login menu")
        logger.info(f"[login] Stored token for {user_id} has expired, re-authenticating")
        io.print_info(f"Session expired for {user_id}. Please sign in again.")

    if not _is_interactive_tty():
        logger.info("[login] Non-interactive environment, login required but not possible")
        return None

    io.print_info("")
    io.print_info("You are not signed in. Login is required to use Siada.")

    while True:
        io.print_info("")
        io.print_info("  1. Sign in with LiId          (opens browser automatically)")
        io.print_info("  2. Sign in with Device Code   (print URL, no browser needed)")
        io.print_info("  3. Provide API key            (enter access token directly)")
        io.print_info("")

        try:
            raw = input("Select [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            io.print_info("\nLogin is required to use Siada. Exiting.")
            sys.exit(1)

        if raw not in ("1", "2", "3"):
            io.print_warning(f"Invalid selection '{raw}'. Please enter 1, 2, or 3.")
            continue

        if raw == "3":
            try:
                import getpass
                api_key = getpass.getpass("Enter your API key: ").strip()
            except (EOFError, KeyboardInterrupt):
                io.print_info("\nLogin is required to use Siada. Exiting.")
                sys.exit(1)

            if not api_key:
                io.print_warning("API key cannot be empty.")
                continue

            from siada.internal.services.idaas.auth_store import is_token_valid
            if not is_token_valid(api_key):
                io.print_error("Invalid or expired API key.")
                io.print_info("Please try again.")
                continue

            user_id = _extract_user_from_token(api_key)
            if not user_id:
                io.print_error("Could not extract user identity from the provided API key.")
                io.print_info("Please try again.")
                continue

            _save(user_id, api_key, io)
            _refresh_telemetry(user_id)
            io.print_info(f"Signed in as {user_id}")
            io.print_info("")
            logger.info(f"[login] Signed in via API key: {user_id}")
            return user_id

        open_browser = raw == "1"

        try:
            from siada.internal.services.idaas.login import run_device_code_flow
            from siada.internal.services.idaas.get_auth_token import AuthExpiredError, AuthFailedError

            access_token, refresh_token, user, email, email_refresh_token = run_device_code_flow(
                open_browser=open_browser,
                print_line=lambda msg: io.print_info(msg),
            )
        except (AuthExpiredError, AuthFailedError) as exc:
            io.print_error(f"Login failed: {exc}")
            io.print_info("Please try again.")
            continue
        except KeyboardInterrupt:
            io.print_info("\nLogin is required to use Siada. Exiting.")
            sys.exit(1)
        except Exception as exc:
            io.print_error(f"Login error: {exc}")
            logger.exception("[login] Unexpected error during login flow")
            io.print_info("Please try again.")
            continue

        if not user.leg:
            io.print_error("Login succeeded but no domain account (leg) found in token.")
            io.print_info("Please try again.")
            continue

        _save(
            user.leg, access_token, io,
            refresh_token=refresh_token,
            email=email or None,
            email_refresh_token=email_refresh_token,
        )
        _refresh_telemetry(user.leg)

        display_name = user.nickname if user.nickname else user.leg
        io.print_info(f"Signed in as {display_name} ({user.leg})")
        io.print_info("")
        logger.info(f"[login] Successfully logged in: {user.leg}")
        return user.leg


# --- Public entry points ---

def reconfigure_acp(io) -> Optional[str]:
    """Reconfiguration flow triggered by /configure (ACP mode).

    Always shows the LoginSelector (skips the fast path) and supports cancel.

    Returns:
        'api-key-user:{provider_id}' on new API-key config,
        'liid:{user_id}' on LiId switch, or None on cancel/failure.
    """
    if not (hasattr(io, "acp_adapter") and io.acp_adapter
            and hasattr(io.acp_adapter, "transport") and io.acp_adapter.transport
            and getattr(io.acp_adapter.transport, "is_connected", False)):
        logger.warning("[reconfigure_acp] ACP transport not connected")
        return None

    try:
        from siada.provider.models_dev import get_providers_for_ui
        providers_data = get_providers_for_ui()
    except Exception:
        providers_data = []

    # cancelable=True so the frontend shows an Esc-to-cancel hint
    selector_params = {
        "providers": providers_data,
        "cancelable": True,
    }
    if not _HAS_INTERNAL:
        selector_params["liidDisabled"] = True

    _send_acp_notification(io, "ui/showLoginSelector", selector_params)

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

    if not _HAS_INTERNAL:
        _send_acp_notification(io, "ui/loginError", {
            "error": "LiId login is not available in this build. Please use an API key."
        })
        logger.warning("[reconfigure_acp] LiId login requested but siada.internal is unavailable")
        return None

    # Options 1/2: LiId device code flow
    open_browser = choice == "1"
    try:
        from siada.internal.services.idaas.get_device_code import get_device_code
        from siada.internal.services.idaas.get_auth_token import poll_auth_token, AuthExpiredError, AuthFailedError
        from siada.internal.services.idaas.get_user import decode_id_token

        device = get_device_code()
        url = device.verification_uri_complete
        _send_acp_notification(io, "ui/loginDeviceUrl", {"url": url, "openBrowser": open_browser})

        auth_token = poll_auth_token(device.device_code, device.interval)
        user = decode_id_token(auth_token.id_token)
    except (AuthExpiredError, AuthFailedError) as exc:
        _send_acp_notification(io, "ui/loginError", {"error": str(exc)})
        return None
    except Exception as exc:
        _send_acp_notification(io, "ui/loginError", {"error": str(exc)})
        return None

    if not user.leg:
        _send_acp_notification(io, "ui/loginError", {"error": "No domain account (leg) in token"})
        return None

    _save(user.leg, auth_token.access_token, io, refresh_token=auth_token.refresh_token)
    _refresh_telemetry(user.leg)
    # Clear API key config since user switched to LiId
    clear_api_key_config()

    display_name = user.nickname if user.nickname else user.leg
    _send_acp_notification(io, "ui/loginSuccess", {"userId": user.leg, "displayName": display_name})
    logger.info(f"[reconfigure_acp] Switched to LiId: {user.leg}")
    return f"liid:{user.leg}"


def ensure_logged_in(io, acp_mode: bool = False) -> Optional[str]:
    """Verify login state and prompt the user to sign in if needed.

    Args:
        io: InputOutput instance.
        acp_mode: True to interact via frontend LoginSelector; False for TTY input().

    Returns:
        Logged-in domain account (leg) or synthetic api-key user_id, or None on failure.
    """
    # Fast path: conf.yaml already has a default-provider config — skip LiId login.
    api_key_user = _check_stored_api_key_config()
    if api_key_user:
        return api_key_user

    if acp_mode:
        return _ensure_logged_in_acp(io)
    return _ensure_logged_in_tty(io)
