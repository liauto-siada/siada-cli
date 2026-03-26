"""Tests for SiadaDaemon – lifecycle and scheduler integration."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from siada.agent_hub.proactive.daemon import SiadaDaemon

_LOAD_CONF = "siada.config.config_loader.load_conf"
_SCHEDULER_CLS = "siada.agent_hub.proactive.scheduler.ProactiveScheduler"


def _make_daemon(tmp_path: Path) -> SiadaDaemon:
    return SiadaDaemon(
        pid_file=tmp_path / "daemon.pid",
        workspace=str(tmp_path),
    )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestDaemonInit:

    def test_default_workspace_is_siada_home_tmp(self, tmp_path):
        from siada.foundation.constants import SIADA_HOME
        d = SiadaDaemon(pid_file=tmp_path / "d.pid")
        assert d.workspace == str(SIADA_HOME / "workspace" / "tmp")

    def test_custom_workspace_is_stored(self, tmp_path):
        d = _make_daemon(tmp_path)
        assert d.workspace == str(tmp_path)

    def test_scheduler_is_none_before_start(self, tmp_path):
        assert _make_daemon(tmp_path).scheduler is None

    def test_running_is_false_before_start(self, tmp_path):
        assert _make_daemon(tmp_path).running is False


# ---------------------------------------------------------------------------
# initialize_components
# ---------------------------------------------------------------------------


class TestInitializeComponents:

    def test_creates_scheduler_with_proactive_config_and_workspace(self, tmp_path):
        d = _make_daemon(tmp_path)
        d.setup_logging()

        mock_config = MagicMock()
        mock_scheduler = MagicMock()

        with patch(_LOAD_CONF, return_value=mock_config), \
             patch(_SCHEDULER_CLS, return_value=mock_scheduler) as mock_cls:
            d.initialize_components()

        mock_cls.assert_called_once_with(
            config=mock_config.proactive_config,
            workspace=str(tmp_path),
        )
        assert d.scheduler is mock_scheduler


# ---------------------------------------------------------------------------
# start: scheduler lifecycle
# ---------------------------------------------------------------------------


class TestDaemonStart:

    def _start_with_mock_scheduler(self, d: SiadaDaemon, mock_scheduler):
        """Run daemon.start() with scheduler and run_loop both mocked."""
        with patch(_LOAD_CONF, return_value=MagicMock()), \
             patch(_SCHEDULER_CLS, return_value=mock_scheduler), \
             patch.object(d, "run_loop"):
            return d.start()

    def test_start_calls_scheduler_start(self, tmp_path):
        d = _make_daemon(tmp_path)
        mock_scheduler = MagicMock()
        result = self._start_with_mock_scheduler(d, mock_scheduler)
        assert result is True
        mock_scheduler.start.assert_called_once()

    def test_start_writes_pid_file(self, tmp_path):
        d = _make_daemon(tmp_path)
        self._start_with_mock_scheduler(d, MagicMock())
        assert (tmp_path / "daemon.pid").exists()

    def test_start_returns_false_when_already_running(self, tmp_path):
        d = _make_daemon(tmp_path)
        (tmp_path / "daemon.pid").write_text("99999\n")
        with patch("os.kill"):  # pretend PID is alive
            result = d.start()
        assert result is False

    def test_start_returns_false_on_config_load_error(self, tmp_path):
        d = _make_daemon(tmp_path)
        with patch(_LOAD_CONF, side_effect=RuntimeError("cfg boom")):
            result = d.start()
        assert result is False


# ---------------------------------------------------------------------------
# shutdown: scheduler stopped
# ---------------------------------------------------------------------------


class TestDaemonShutdown:

    def test_shutdown_calls_scheduler_stop(self, tmp_path):
        d = _make_daemon(tmp_path)
        d.setup_logging()
        mock_scheduler = MagicMock()
        d.scheduler = mock_scheduler

        d.shutdown()

        mock_scheduler.stop.assert_called_once()

    def test_shutdown_removes_pid_file(self, tmp_path):
        d = _make_daemon(tmp_path)
        d.setup_logging()
        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("1234\n")
        d.scheduler = MagicMock()

        d.shutdown()

        assert not pid_file.exists()

    def test_shutdown_sets_running_false(self, tmp_path):
        d = _make_daemon(tmp_path)
        d.setup_logging()
        d.running = True
        d.scheduler = MagicMock()

        d.shutdown()

        assert d.running is False

    def test_shutdown_without_scheduler_does_not_raise(self, tmp_path):
        d = _make_daemon(tmp_path)
        d.setup_logging()
        assert d.scheduler is None
        d.shutdown()  # must not raise
