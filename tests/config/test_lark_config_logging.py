"""Lark config loading reports its mode to log files, never to the console."""

from unittest.mock import Mock

from siada.config import config_loader
from siada.foundation.log_category import LogCategory


def test_lark_config_diagnostic_is_logged_for_files_only(monkeypatch):
    logger = Mock()
    monkeypatch.setattr(config_loader, "logger", logger)

    assert config_loader._load_lark_config({"lark": {"mode": "relay"}}) == {"lark": {"mode": "relay"}}

    logger.info.assert_called_once_with(
        "Lark config loaded, mode=relay",
        extra={"log_category": LogCategory.FILE_ONLY},
    )


def test_missing_lark_section_logs_nothing(monkeypatch):
    logger = Mock()
    monkeypatch.setattr(config_loader, "logger", logger)

    assert config_loader._load_lark_config({"llm_config": {"model": "synthetic-model"}}) is None

    logger.info.assert_not_called()
