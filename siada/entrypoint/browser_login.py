"""Expose the existing CLI login wizard as a bounded NDJSON subprocess."""

import json
import sys
from types import SimpleNamespace


def main(*, reconfigure: bool = False) -> int:
    from siada.entrypoint.login import login_prompt
    exhausted = False
    succeeded = False

    class Transport:
        is_connected = True

        def send_sync(self, message):
            nonlocal succeeded
            succeeded = succeeded or message.method == "ui/loginSuccess"
            params = message.params
            if message.method == "ui/showLoginSelector" and not params.get("providers"):
                from siada.provider.models_dev import _PROVIDER_MAP, _PROVIDER_DISPLAY_NAMES
                params = {**params, "providers": [
                    {"id": key, "name": _PROVIDER_DISPLAY_NAMES[key], "baseUrl": url,
                     "apiKeyHint": hint, "models": []}
                    for key, _, url, hint in _PROVIDER_MAP
                ]}
            print(json.dumps({"method": message.method, "params": params}), flush=True)

    def read_choice():
        nonlocal exhausted
        line = sys.stdin.readline()
        if not line:
            exhausted = True
            raise EOFError
        data = json.loads(line)
        choice = data.get("choice")
        if choice not in ("1", "2", "3", "4"):
            raise ValueError("Invalid login choice")
        return f"__LOGIN_CHOICE__:{choice}:{json.dumps(data.get('payload', {}))}"

    io = SimpleNamespace(
        acp_adapter=SimpleNamespace(transport=Transport()),
        print_warning=lambda *_: None,
        print_error=lambda *_: None,
        print_info=lambda *_: None,
    )
    original_reader = login_prompt._read_acp_stdin_message
    login_prompt._read_acp_stdin_message = read_choice
    try:
        wizard = login_prompt.reconfigure_acp if reconfigure else login_prompt._ensure_logged_in_acp
        while True:
            if wizard(io):
                if not succeeded:
                    Transport().send_sync(SimpleNamespace(method="ui/loginSuccess", params={}))
                return 0
            if exhausted:
                return 0
    except (EOFError, KeyboardInterrupt):
        return 0
    except Exception:
        Transport().send_sync(SimpleNamespace(
            method="ui/loginError", params={"error": "Login failed. Please retry."},
        ))
        return 1
    finally:
        login_prompt._read_acp_stdin_message = original_reader