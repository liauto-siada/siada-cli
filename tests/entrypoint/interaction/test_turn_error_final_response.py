"""User-facing missing completion errors show the active log directory."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agents.exceptions import ModelBehaviorError

from siada.entrypoint.interaction.turn.interface import RunTurn
from siada.foundation import logging as logging_module
from siada.provider.retry import MissingFinalResponseError


@pytest.mark.parametrize("error", [
    MissingFinalResponseError(
        model="synthetic", response_id="resp-test",
        last_event="response.created", output_exposed=False,
    ),
    ModelBehaviorError("Model did not produce a final response!"),
    ModelBehaviorError("Unrelated model behavior"),
])
def test_agent_error_shows_actual_log_path(error, tmp_path, monkeypatch):
    monkeypatch.setattr(logging_module, "log_dir", str(tmp_path))
    turn = SimpleNamespace(config=SimpleNamespace(io=SimpleNamespace(print_error=Mock())))
    RunTurn.handle_error(turn, error)
    message = turn.config.io.print_error.call_args.args[0]
    assert f"Detailed Log: {tmp_path / 'errors.log'}" in message
    assert turn.error is error
    if str(error) == "Unrelated model behavior":
        assert "Unrelated model behavior" in message
        assert "模型响应未完整结束" not in message
    else:
        assert "模型响应未完整结束" in message
        assert "工具执行结果" in message