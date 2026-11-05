"""Read local login readiness without starting a UI or refreshing credentials."""

import json


def browser_check() -> dict:
    import siada
    from siada.config.conf_store import get_conf_section

    try:
        config = get_conf_section("llm_config")
        ready = bool(config.get("provider") == "default" and config.get("base_url") and config.get("api_key"))
        if not ready:
            try:
                from siada.internal.services.idaas.auth_store import (
                    get_stored_user_id, get_stored_access_token, is_token_valid,
                )

                token = get_stored_access_token()
                ready = bool(get_stored_user_id() and token and is_token_valid(token))
            except ImportError:
                pass
        status = "ready" if ready else "login_required"
    except Exception:
        status = "unknown"
    return {"schemaVersion": 1, "version": siada.__version__, "auth": {"status": status}}


def main() -> int:
    print(json.dumps(browser_check()))
    return 0