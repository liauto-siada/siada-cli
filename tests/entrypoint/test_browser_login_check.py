import pytest
from siada.entrypoint.browser_check import browser_check


@pytest.mark.parametrize("config,status", [
    ({"provider": "default", "base_url": "https://example.test", "api_key": "synthetic"}, "ready"),
    ({}, "login_required"),
    ({"provider": "default", "base_url": "https://example.test"}, "login_required"),
])
def test_browser_login_check(monkeypatch, config, status):
    import sys
    from siada.config import conf_store

    monkeypatch.setattr(conf_store, "get_conf_section", lambda _: config)
    monkeypatch.setitem(sys.modules, "siada.internal.services.idaas.auth_store", None)
    result = browser_check()
    assert result["auth"]["status"] == status
    assert "synthetic" not in str(result)


def test_invalid_config_reports_unknown(monkeypatch):
    from siada.config import conf_store

    monkeypatch.setattr(conf_store, "get_conf_section", lambda _: (_ for _ in ()).throw(ValueError("secret")))
    assert browser_check()["auth"]["status"] == "unknown"


@pytest.mark.parametrize("valid,status", [(True, "ready"), (False, "login_required")])
def test_account_login_checks_token_without_returning_credentials(monkeypatch, valid, status):
    import sys
    from types import SimpleNamespace
    from siada.config import conf_store

    monkeypatch.setattr(conf_store, "get_conf_section", lambda _: {})
    monkeypatch.setitem(sys.modules, "siada.internal.services.idaas.auth_store", SimpleNamespace(
        get_stored_user_id=lambda: "synthetic-user",
        get_stored_access_token=lambda: "synthetic-token",
        is_token_valid=lambda _: valid,
    ))
    result = browser_check()
    assert result["auth"]["status"] == status
    assert "synthetic" not in str(result)