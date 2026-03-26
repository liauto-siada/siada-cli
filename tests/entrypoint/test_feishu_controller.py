"""Tests for Lark controller exception formatting."""

import siada.config.config_loader as config_loader
import siada.entrypoint.interaction.feishu_controller as lark_controller
import siada.entrypoint.helpers.model_setup as model_setup

from siada.config.config_loader import Config
from siada.entrypoint.interaction.feishu_controller import (
    LarkController,
    _decode_embedded_bytes_literals,
    _format_exception_for_user,
)
from siada.entrypoint.interaction.running_config import RunningConfig


def test_decode_embedded_bytes_literals_decodes_utf8_bytes_payload() -> None:
    """Should decode bytes-literal payloads embedded in exception text."""
    raw = (
        "AnthropicException - "
        "b'{\"code\":4000005,\"message\":\"\\xe4\\xbe\\x9b\\xe5\\xba\\x94\\xe5\\x95\\x86\"}'"
    )

    decoded = _decode_embedded_bytes_literals(raw)

    assert "AnthropicException - {\"code\":4000005" in decoded
    assert "供应商" in decoded
    assert "\\xe4" not in decoded


def test_format_exception_for_user_decodes_bytes_literal_message() -> None:
    """Should return a user-friendly decoded exception message."""

    class SampleError(RuntimeError):
        pass

    exc = SampleError(
        "litellm.ServiceUnavailableError: AnthropicException - "
        "b'{\"code\":4000005,\"message\":\"\\xe4\\xbe\\x9b\\xe5\\xba\\x94\\xe5\\x95\\x86\\xe6\\xa8\\xa1\\xe5\\x9e\\x8b\\xe5\\x93\\x8d\\xe5\\xba\\x94\\xe5\\xbc\\x82\\xe5\\xb8\\xb8\"}'"
    )

    formatted = _format_exception_for_user(exc, max_length=500)

    assert "ServiceUnavailableError" in formatted
    assert "供应商模型响应异常" in formatted
    assert "b'" not in formatted


def test_format_exception_for_user_truncates_long_messages() -> None:
    """Should keep final IM error messages within the configured max length."""
    exc = RuntimeError("x" * 50)

    formatted = _format_exception_for_user(exc, max_length=20)

    assert formatted == ("x" * 17) + "..."


def test_decode_embedded_bytes_literals_returns_original_text_on_unexpected_eval_error(
    monkeypatch,
) -> None:
    """Should return the original text when literal_eval fails unexpectedly."""
    raw = "AnthropicException - b'abc'"

    def _raise_recursion_error(_literal: str):
        raise RecursionError("boom")

    monkeypatch.setattr(lark_controller.ast, "literal_eval", _raise_recursion_error)

    decoded = _decode_embedded_bytes_literals(raw)

    assert decoded == raw


def test_format_exception_for_user_handles_none_exception() -> None:
    """Should return 'Unknown error' when exc is None."""
    assert _format_exception_for_user(None) == "Unknown error"


def test_decode_embedded_bytes_literals_skips_oversized_literal() -> None:
    """Should skip bytes literals longer than 2000 chars without decoding."""
    # Build a bytes literal that exceeds the 2000 char guard
    huge_body = "\\x41" * 600  # each \\x41 = 4 chars -> 2400 chars in the literal
    raw = f"Error - b'{huge_body}'"
    decoded = _decode_embedded_bytes_literals(raw)
    # The oversized literal should remain untouched (still contains b'...')
    assert "b'" in decoded


def test_decode_embedded_bytes_literals_plain_text_passthrough() -> None:
    """Should return plain text unchanged when no bytes literals are present."""
    text = "Something went wrong: connection refused"
    assert _decode_embedded_bytes_literals(text) == text


def test_format_exception_for_user_empty_message_falls_back_to_class_name() -> None:
    """Should use exception class name when str(exc) is empty."""
    exc = ValueError("")
    result = _format_exception_for_user(exc)
    assert result == "ValueError"


def test_build_running_config_reuses_model_setup_logic(monkeypatch) -> None:
    """Should delegate IM model config building to model_setup helper."""
    conf = Config()
    expected_model_config = object()
    io_token = object()

    monkeypatch.setattr(config_loader, "load_conf", lambda: conf)
    monkeypatch.setattr(lark_controller, "_get_default_workspace", lambda: "/tmp/lark-workspace")

    captured: dict[str, object] = {}

    def _fake_get_config_from_conf(io, passed_conf):
        captured["io"] = io
        captured["conf"] = passed_conf
        return expected_model_config

    monkeypatch.setattr(model_setup, "get_config_from_conf", _fake_get_config_from_conf)

    controller = LarkController({"lark": {"mode": "direct"}})
    controller._lark_io = io_token

    running_config = controller._build_running_config()

    assert isinstance(running_config, RunningConfig)
    assert running_config.llm_config is expected_model_config
    assert running_config.io is io_token
    assert running_config.workspace == "/tmp/lark-workspace"
    assert captured == {"io": io_token, "conf": conf}
