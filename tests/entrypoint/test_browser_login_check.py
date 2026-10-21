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


def test_free_trial_is_ready_without_key(monkeypatch):
    from siada.config import conf_store
    from siada.provider.free_trial import FREE_TRIAL_BASE_URL
    monkeypatch.setattr(conf_store, "get_conf_section", lambda _: {
        "provider": "default", "base_url": FREE_TRIAL_BASE_URL, "api_key": "",
    })
    result = browser_check()
    assert result["auth"]["status"] == "ready"