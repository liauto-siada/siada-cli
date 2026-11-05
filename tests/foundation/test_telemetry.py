"""Token and cost reporting is absent from both telemetry implementations."""

import importlib.util
import sys

from siada.foundation import telemetry as telemetry_module


def test_telemetry_has_no_token_usage_reporting_api():
    assert not hasattr(telemetry_module.Telemetry, "captureApiTokenUsage")
    assert callable(telemetry_module.Telemetry.captureConversation)
    assert callable(telemetry_module.Telemetry.captureConversationEvent)
    assert callable(telemetry_module.Telemetry.captureToolEditFileUsage)


def test_public_fallback_has_no_token_usage_reporting_api(monkeypatch):
    monkeypatch.setitem(sys.modules, "siada.internal.foundation.telemetry", None)
    spec = importlib.util.spec_from_file_location("telemetry_fallback", telemetry_module.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert not hasattr(module.telemetry, "captureApiTokenUsage")
    assert callable(module.telemetry.captureConversation)
    assert callable(module.telemetry.captureConversationEvent)
    assert callable(module.telemetry.captureToolEditFileUsage)