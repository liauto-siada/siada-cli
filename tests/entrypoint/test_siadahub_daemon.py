"""Tests for siadahub daemon integration."""

from unittest.mock import Mock, MagicMock, patch
import pytest

from siada.config.config_loader import Config
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
        
        with patch('siada.agent_hub.proactive.daemon_manager.DaemonManager', return_value=mock_manager):
            ensure_daemon_running(conf, verbose=False)
            mock_manager.ensure_daemon.assert_called_once()

    def test_ensure_daemon_running_failure_no_block(self):
        """Test that daemon failure doesn't block process."""
        conf = Mock(spec=Config)
        
        mock_manager = MagicMock()
        mock_manager.ensure_daemon.side_effect = Exception("Daemon failed")
        
        with patch('siada.agent_hub.proactive.daemon_manager.DaemonManager', return_value=mock_manager), \
             patch('siada.entrypoint.siadahub.logger') as mock_logger:
            
            # Should not raise, just log warning
            ensure_daemon_running(conf, verbose=False)
            mock_logger.warning.assert_called_once()


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
        args = Mock(
            stop_api_server=False,
            api_server=False,
            stop_daemon=True,
            daemon_status=False
        )
        conf = Mock(spec=Config)
        
        with patch('siada.entrypoint.siadahub.handle_stop_daemon', return_value=0) as mock_stop:
            result = handle_special_commands(args, conf)
            
            assert result == 0
            mock_stop.assert_called_once()

    def test_daemon_status_command(self):
        """Test --daemon-status command."""
        args = Mock(
            stop_api_server=False,
            api_server=False,
            stop_daemon=False,
            daemon_status=True
        )
        conf = Mock(spec=Config)
        
        with patch('siada.entrypoint.siadahub.handle_daemon_status', return_value=0) as mock_status:
            result = handle_special_commands(args, conf)
            
            assert result == 0
            mock_status.assert_called_once()

    def test_no_special_command(self):
        """Test when no special command is given."""
        args = Mock(
            stop_api_server=False,
            api_server=False,
            stop_daemon=False,
            daemon_status=False,
            list_models=False,
            just_check_update=False,
            upgrade=False
        )
        conf = Mock(spec=Config)
        
        result = handle_special_commands(args, conf)
        
        assert result is None  # Should continue normal flow
