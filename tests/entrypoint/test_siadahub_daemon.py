"""Tests for siadahub daemon integration."""

from unittest.mock import Mock, MagicMock, patch

from siada.config.config_loader import Config
from siada.entrypoint.args_parser.args import get_parser
from siada.entrypoint.siadahub import (
    ensure_daemon_running,
    handle_stop_daemon,
    handle_daemon_status,
    handle_special_commands,
)


class TestEnsureDaemonRunning:
    """Test ensure_daemon_running function."""

    def test_ensure_daemon_running_success(self):
        """Test successfully ensuring daemon is running."""
        conf = Mock(spec=Config)
        
        mock_manager = MagicMock()
        mock_manager.ensure_daemon.return_value = (True, 12345)
        
        with patch('siada.agent_hub.proactive.daemon_manager.DaemonManager', return_value=mock_manager), \
             patch('siada.entrypoint.helpers.daemon_commands.threading.Thread') as mock_thread, \
             patch('time.sleep') as mock_sleep:
            ensure_daemon_running(conf, verbose=False)
            mock_thread.return_value.start.assert_called_once()
            assert mock_thread.call_args.kwargs["daemon"] is True
            mock_manager.ensure_daemon.assert_not_called()
            mock_thread.call_args.kwargs["target"]()
            mock_sleep.assert_called_once_with(3)
            mock_manager.ensure_daemon.assert_called_once()

    def test_ensure_daemon_running_failure_no_block(self):
        """Test that daemon failure doesn't block process."""
        conf = Mock(spec=Config)
        
        mock_manager = MagicMock()
        mock_manager.ensure_daemon.side_effect = Exception("Daemon failed")
        
        with patch('siada.agent_hub.proactive.daemon_manager.DaemonManager', return_value=mock_manager), \
             patch('siada.entrypoint.helpers.daemon_commands.threading.Thread') as mock_thread, \
             patch('siada.entrypoint.helpers.daemon_commands.logger') as mock_logger, \
             patch('time.sleep'):
            ensure_daemon_running(conf, verbose=False)
            mock_manager.ensure_daemon.assert_not_called()
            mock_thread.call_args.kwargs["target"]()
            mock_logger.error.assert_called_once()
            assert "Daemon failed" in mock_logger.error.call_args.args[0]


class TestHandleStopDaemon:
    """Test handle_stop_daemon function."""

    def test_stop_daemon_success(self, capsys):
        """Test successfully stopping daemon."""
        mock_manager = MagicMock()
        mock_manager.is_running.return_value = True
        mock_manager.stop_daemon.return_value = True
        
        with patch('siada.agent_hub.proactive.daemon_manager.DaemonManager', return_value=mock_manager):
            result = handle_stop_daemon()
            
            assert result == 0
            mock_manager.stop_daemon.assert_called_once()
            
            captured = capsys.readouterr()
            assert "stopped" in captured.out.lower()

    def test_stop_daemon_not_running(self, capsys):
        """Test stopping when daemon is not running."""
        mock_manager = MagicMock()
        mock_manager.is_running.return_value = False
        
        with patch('siada.agent_hub.proactive.daemon_manager.DaemonManager', return_value=mock_manager):
            result = handle_stop_daemon()
            
            assert result == 0
            mock_manager.stop_daemon.assert_not_called()
            
            captured = capsys.readouterr()
            assert "not running" in captured.out.lower()

    def test_stop_daemon_failure(self, capsys):
        """Test stopping daemon failure."""
        mock_manager = MagicMock()
        mock_manager.is_running.return_value = True
        mock_manager.stop_daemon.return_value = False
        
        with patch('siada.agent_hub.proactive.daemon_manager.DaemonManager', return_value=mock_manager):
            result = handle_stop_daemon()
            
            assert result == 1
            
            captured = capsys.readouterr()
            assert "failed" in captured.err.lower()


class TestHandleDaemonStatus:
    """Test handle_daemon_status function."""

    def test_daemon_status_running(self, capsys):
        """Test showing status when daemon is running."""
        mock_manager = MagicMock()
        mock_manager.get_pid.return_value = 12345
        
        with patch('siada.agent_hub.proactive.daemon_manager.DaemonManager', return_value=mock_manager):
            result = handle_daemon_status()
            
            assert result == 0
            
            captured = capsys.readouterr()
            assert "12345" in captured.out
            assert "running" in captured.out.lower()

    def test_daemon_status_not_running(self, capsys):
        """Test showing status when daemon is not running."""
        mock_manager = MagicMock()
        mock_manager.get_pid.return_value = None
        
        with patch('siada.agent_hub.proactive.daemon_manager.DaemonManager', return_value=mock_manager):
            result = handle_daemon_status()
            
            assert result == 1
            
            captured = capsys.readouterr()
            assert "not running" in captured.out.lower()


class TestHandleSpecialCommands:
    """Test handle_special_commands function."""

    def test_stop_daemon_command(self):
        """Test --stop-daemon command."""
        args = get_parser(git_root=None, default_config_files=[]).parse_args(["--stop-daemon"])
        conf = Mock(spec=Config)
        
        with patch('siada.entrypoint.siadahub.handle_stop_daemon', return_value=0) as mock_stop:
            result = handle_special_commands(args, conf, MagicMock())
            
            assert result == 0
            mock_stop.assert_called_once()

    def test_daemon_status_command(self):
        """Test --daemon-status command."""
        args = get_parser(git_root=None, default_config_files=[]).parse_args(["--daemon-status"])
        conf = Mock(spec=Config)
        
        with patch('siada.entrypoint.siadahub.handle_daemon_status', return_value=0) as mock_status:
            result = handle_special_commands(args, conf, MagicMock())
            
            assert result == 0
            mock_status.assert_called_once()

    def test_no_special_command(self):
        """Test when no special command is given."""
        args = get_parser(git_root=None, default_config_files=[]).parse_args([])
        conf = Mock(spec=Config)
        
        result = handle_special_commands(args, conf, MagicMock())
        
        assert result is None  # Should continue normal flow
