"""Read local login readiness without starting a UI or refreshing credentials."""

import json


def browser_check() -> dict:
    import siada
    from siada.config.conf_store import get_conf_section
    from siada.provider.free_trial import is_free_trial_endpoint

    try:
        config = get_conf_section("llm_config")
        ready = bool(config.get("provider") == "default" and config.get("base_url")
                     and (config.get("api_key") or is_free_trial_endpoint(config.get("base_url"))))
        status = "ready" if ready else "login_required"
    except Exception:
        status = "unknown"
    return {"schemaVersion": 1, "version": siada.__version__, "auth": {"status": status}}


def main() -> int:
    print(json.dumps(browser_check()))
    return 0