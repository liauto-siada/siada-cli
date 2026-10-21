"""Exercise Chrome's NDJSON bridge with the real public login wizard."""
import io
import json
from unittest.mock import Mock

from siada.entrypoint import browser_login
from siada.entrypoint.login import login_prompt
from siada.provider.free_trial import FREE_TRIAL_MODELS


def test_browser_free_trial_retry_and_success(monkeypatch, capsys):
    model = FREE_TRIAL_MODELS[0][0]
    monkeypatch.setattr("sys.stdin", io.StringIO(
        json.dumps({"choice": "4", "payload": {"model": "unsupported"}}) + "\n"
        + json.dumps({"choice": "4", "payload": {"model": model}}) + "\n"
    ))
    save = Mock(return_value=True)
    monkeypatch.setattr(login_prompt, "_save_provider_config", save)
    monkeypatch.setattr("siada.provider.models_dev.get_providers_for_ui", lambda: [])
    monkeypatch.setenv("API_KEY", "")
    monkeypatch.setenv("BASE_URL", "")
    assert browser_login.main() == 0
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert events[0]["params"]["liidDisabled"]
    assert events[0]["params"]["freeTrialModels"][0]["id"] == model
    assert any(event["method"] == "ui/loginError" for event in events)
    assert events[-1]["method"] == "ui/loginSuccess"
    assert save.call_count == 1