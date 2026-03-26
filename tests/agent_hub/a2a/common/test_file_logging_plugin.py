import pytest


from datetime import datetime


from siada.agent_hub.a2a.common.file_logging_plugin import FileLoggingPlugin


class _CaptureFileLoggingPlugin(FileLoggingPlugin):
  """测试用：捕获 _log 输出，避免写入真实文件。"""

  def __init__(self):
    super().__init__(log_file="/tmp/siada_test.log")
    self.lines: list[str] = []

  def _log(self, message: str) -> None:  # type: ignore[override]
    self.lines.append(message)


def test_format_event_timestamp_float_seconds() -> None:
  p = _CaptureFileLoggingPlugin()
  s = p._format_event_timestamp(1700000000.0)
  # should be ISO-like
  assert "T" in s


def test_format_event_timestamp_datetime() -> None:
  p = _CaptureFileLoggingPlugin()
  dt = datetime(2026, 1, 1, 0, 0, 0)
  s = p._format_event_timestamp(dt)
  assert s.startswith("2026-01-01T00:00:00")


def test_format_event_timestamp_none() -> None:
  p = _CaptureFileLoggingPlugin()
  s = p._format_event_timestamp(None)
  assert "T" in s

