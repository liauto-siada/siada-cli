"""Verify model error diagnostics redact credentials without changing requests."""

import copy
import importlib
import json
from unittest.mock import Mock

import pytest

from siada.foundation.log_category import LogCategory


@pytest.fixture
def model_error_logger(monkeypatch):
    module = importlib.import_module("siada.foundation.logging")
    logger = Mock()
    monkeypatch.setattr(module, "logger", logger)
    return module.log_model_error, logger


def logged_body(logger):
    text = logger.error.call_args.args[0]
    return json.loads(text.split("--- Complete LLM Request Body ---\n", 1)[1])


@pytest.mark.parametrize(
    "field",
    [
        "Authorization", "authorization", "Proxy-Authorization", "API_KEY",
        "api-key", "apikey", "X-API-Key", "access_token", "refresh-token",
        "id_token", "client_secret", "password", "Cookie", "Set-Cookie",
        "X-Siada-Token",
        "token",
    ],
)
def test_model_error_redacts_authentication_fields(model_error_logger, field):
    log_error, logger = model_error_logger
    body = {"model": "synthetic-model", "extra_headers": {field: "synthetic-credential"}}
    original = copy.deepcopy(body)

    log_error("SyntheticError", "synthetic failure", body)

    assert logged_body(logger)["extra_headers"][field] == "[REDACTED]"
    assert "synthetic-credential" not in logger.error.call_args.args[0]
    assert body == original
    logger.error.assert_called_once()
    assert logger.error.call_args.kwargs == {"extra": {"log_category": LogCategory.MODEL_ERROR}}


def test_model_error_redacts_nested_credentials_and_preserves_diagnostics(model_error_logger):
    log_error, logger = model_error_logger
    body = {
        "model": "synthetic-model",
        "messages": [{"role": "user", "content": "synthetic input"}],
        "max_tokens": 128,
        "extra_headers": {"uuid": "synthetic-request", "client-version": "test"},
        "metadata": [{"api_key": "synthetic-nested-key"}, ({"token": "synthetic-token"},)],
    }
    original = copy.deepcopy(body)

    log_error("SyntheticError", "synthetic failure", body)

    sanitized = logged_body(logger)
    assert sanitized["model"] == body["model"]
    assert sanitized["messages"] == body["messages"]
    assert sanitized["max_tokens"] == 128
    assert sanitized["extra_headers"] == body["extra_headers"]
    assert sanitized["metadata"] == [{"api_key": "[REDACTED]"}, [{"token": "[REDACTED]"}]]
    assert body == original


def test_model_error_redacts_known_credentials_echoed_in_error_message(model_error_logger):
    log_error, logger = model_error_logger
    body = {
        "api_key": "synthetic-api-key",
        "extra_headers": {"Authorization": "Bearer synthetic-access-token"},
    }

    log_error(
        "SyntheticError",
        "key=synthetic-api-key; header=Bearer synthetic-access-token; token=synthetic-access-token",
        body,
    )

    text = logger.error.call_args.args[0]
    assert "synthetic-api-key" not in text
    assert "synthetic-access-token" not in text
    assert "Error Type: SyntheticError" in text


@pytest.mark.parametrize("body", [None, {}])
def test_model_error_without_body_keeps_error_details(model_error_logger, body):
    log_error, logger = model_error_logger

    log_error("SyntheticError", "synthetic failure", body)

    text = logger.error.call_args.args[0]
    assert "Error Type: SyntheticError" in text
    assert "Error Message: synthetic failure" in text
    assert "Complete LLM Request Body" not in text


def test_model_error_non_json_value_does_not_hide_original_failure(model_error_logger):
    log_error, logger = model_error_logger

    class UnsafeRepresentation:
        def __str__(self):
            raise AssertionError("diagnostics must not stringify arbitrary objects")

    log_error("SyntheticError", "synthetic failure", {"opaque": UnsafeRepresentation()})

    assert logged_body(logger)["opaque"] == "[UNSERIALIZABLE]"
    assert "Error Message: synthetic failure" in logger.error.call_args.args[0]


def test_model_error_cyclic_body_fails_closed(model_error_logger):
    log_error, logger = model_error_logger
    body = {"api_key": "synthetic-cycle-key"}
    body["cycle"] = body

    log_error("SyntheticError", "synthetic failure", body)

    text = logger.error.call_args.args[0]
    assert "request body unavailable" in text.lower()
    assert "synthetic-cycle-key" not in text
    assert body["api_key"] == "synthetic-cycle-key"


@pytest.mark.parametrize("secret", ['synthetic-"quoted"-key', "synthetic\\escaped\nkey", "合成密钥"])
def test_model_error_redacts_escaped_credentials_echoed_in_body(model_error_logger, secret):
    log_error, logger = model_error_logger
    body = {"api_key": secret, "metadata": [{"echo": f"echoed {secret}"}], secret: "synthetic value"}
    original = copy.deepcopy(body)

    log_error("SyntheticError", f"failed with {secret}", body)

    sanitized = logged_body(logger)
    assert sanitized["metadata"] == [{"echo": "echoed [REDACTED]"}]
    assert "[REDACTED]" in sanitized
    assert secret not in logger.error.call_args.args[0]
    assert body == original


@pytest.mark.parametrize("failure", ["cycle", "invalid_key"])
def test_model_error_serialization_failure_does_not_leak_later_credentials(model_error_logger, failure):
    log_error, logger = model_error_logger
    body = {}
    if failure == "cycle":
        body["cycle"] = body
    else:
        body[object()] = "synthetic value"
    body["api_key"] = "synthetic-late-secret"

    log_error("SyntheticError", "failed with synthetic-late-secret", body)

    text = logger.error.call_args.args[0]
    assert "synthetic-late-secret" not in text
    assert "Error Type: SyntheticError" in text
    assert "request body unavailable" in text.lower()


@pytest.mark.parametrize("field,value", [
    ("Authorization", ["Bearer synthetic-multi-token", "Basic synthetic-multi-auth"]),
    ("access_token", ({"value": "synthetic-multi-token"},)),
])
def test_model_error_removes_echoes_of_container_credentials(model_error_logger, field, value):
    log_error, logger = model_error_logger
    body = {"extra_headers": {field: value}, "echo": "synthetic-multi-token synthetic-multi-auth"}
    original = copy.deepcopy(body)

    log_error("SyntheticError", "failed with synthetic-multi-token synthetic-multi-auth", body)

    text = logger.error.call_args.args[0]
    assert "synthetic-multi-token" not in text
    if field == "Authorization":
        assert "synthetic-multi-auth" not in text
    assert logged_body(logger)["extra_headers"][field] == "[REDACTED]"
    assert body == original