"""
Tests for cmd_theme in SlashCommands.

/theme shows or switches the UI color theme. The choice is persisted to
conf.yaml (ui.theme) via conf_store and pushed to the ACP frontend as a
ui/themeChanged notification so the terminal UI repaints immediately.
Legacy 'auto' uses dark without detection and is saved as dark.
"""
from unittest.mock import MagicMock, patch

import pytest

# Pre-import to break circular-import chain:
# slash_commands -> checkpoint_tracker -> session.task_message_state
import siada.session  # noqa: F401
import siada.support.checkpoint_tracker  # noqa: F401

import siada.io.system_theme_detector as std
from siada.support.slash_commands import SlashCommands


def _make_slash_commands() -> SlashCommands:
    io = MagicMock()
    io.acp_adapter = None
    return SlashCommands(io=io)


class TestCmdThemeShow:
    def test_no_args_shows_current_theme(self):
        sc = _make_slash_commands()

        with patch(
            "siada.config.conf_store.get_conf_value", return_value="light"
        ) as get_mock:
            sc.cmd_theme(MagicMock(), "")

        get_mock.assert_called_once_with("ui.theme", "dark")
        sc.io.print_info.assert_called_once_with(
            "Theme: light\nUsage: /theme [dark | light]"
        )

    def test_no_args_shows_dark_for_legacy_auto(self):
        sc = _make_slash_commands()

        with patch("siada.config.conf_store.get_conf_value", return_value="auto"):
            sc.cmd_theme(MagicMock(), "   ")

        sc.io.print_info.assert_called_once_with(
            "Theme: dark\nUsage: /theme [dark | light]"
        )


class TestCmdThemeSelector:
    """Bare /theme opens the theme selector in the ACP frontend (mirrors
    /effort); in TTY mode it prints the current theme instead."""

    def test_no_args_pushes_selector_when_connected(self):
        sc = _make_slash_commands()
        adapter = MagicMock()
        adapter.transport.is_connected = True
        sc.io.acp_adapter = adapter

        with patch("siada.config.conf_store.get_conf_value", return_value="light"):
            sc.cmd_theme(MagicMock(), "")

        adapter.transport.send_sync.assert_called_once()
        msg = adapter.transport.send_sync.call_args[0][0]
        assert msg.method == "ui/showThemeSelector"
        assert msg.params["themes"] == ["dark", "light"]
        assert msg.params["current"] == "light"
        sc.io.print_info.assert_not_called()

    def test_no_args_pushes_selector_with_auto_current(self):
        sc = _make_slash_commands()
        adapter = MagicMock()
        adapter.transport.is_connected = True
        sc.io.acp_adapter = adapter

        with patch("siada.config.conf_store.get_conf_value", return_value="auto"):
            sc.cmd_theme(MagicMock(), "")

        msg = adapter.transport.send_sync.call_args[0][0]
        assert msg.params["current"] == "dark"

    def test_no_args_prints_when_disconnected(self):
        sc = _make_slash_commands()
        adapter = MagicMock()
        adapter.transport.is_connected = False
        sc.io.acp_adapter = adapter

        with patch("siada.config.conf_store.get_conf_value", return_value="dark"):
            sc.cmd_theme(MagicMock(), "")

        adapter.transport.send_sync.assert_not_called()
        sc.io.print_info.assert_called_once_with(
            "Theme: dark\nUsage: /theme [dark | light]"
        )


class TestCmdThemeSet:
    def test_light_persists_and_confirms(self):
        sc = _make_slash_commands()

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=True
        ) as save_mock:
            sc.cmd_theme(MagicMock(), "light")

        save_mock.assert_called_once_with("ui.theme", "light")
        sc.io.print_info.assert_called_once_with("Theme switched to 'light'")

    @pytest.mark.parametrize("argument", ["auto", "  AUTO "])
    def test_auto_persists_and_confirms_dark(self, argument):
        sc = _make_slash_commands()

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=True
        ) as save_mock, patch(
            "siada.io.system_theme_detector.SystemThemeDetector.detect_theme",
            side_effect=AssertionError("unexpected detection"),
        ) as detect:
            sc.cmd_theme(MagicMock(), argument)

        save_mock.assert_called_once_with("ui.theme", "dark")
        sc.io.print_info.assert_called_once_with("Theme switched to 'dark'")
        detect.assert_not_called()

    def test_case_insensitive(self):
        sc = _make_slash_commands()

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=True
        ) as save_mock:
            sc.cmd_theme(MagicMock(), "  Dark ")

        save_mock.assert_called_once_with("ui.theme", "dark")

    def test_invalid_value_rejected(self):
        sc = _make_slash_commands()

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=True
        ) as save_mock:
            sc.cmd_theme(MagicMock(), "solarized")

        sc.io.print_error.assert_called_once_with(
            "Invalid theme 'solarized'. Usage: /theme [dark | light]"
        )
        save_mock.assert_not_called()

    def test_persist_failure_reported(self):
        sc = _make_slash_commands()

        with patch(
            "siada.config.config_loader.save_conf_field", return_value=False
        ):
            sc.cmd_theme(MagicMock(), "light")

        sc.io.print_error.assert_called_once_with(
            "Failed to persist theme to conf.yaml"
        )


class TestCmdThemeAcpPush:
    """The terminal UI owns the color palettes — /theme must push the new
    theme to the ACP frontend so it repaints live."""

    def test_pushes_acp_notification_when_connected(self):
        sc = _make_slash_commands()
        adapter = MagicMock()
        adapter.transport.is_connected = True
        sc.io.acp_adapter = adapter

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_theme(MagicMock(), "light")

        adapter.transport.send_sync.assert_called_once()
        msg = adapter.transport.send_sync.call_args[0][0]
        assert msg.method == "ui/themeChanged"
        assert msg.params["theme"] == "light"

    def test_auto_pushes_resolved_theme_to_acp(self):
        """The frontend only understands dark|light, so 'auto' must be
        resolved before the push, not forwarded verbatim."""
        sc = _make_slash_commands()
        adapter = MagicMock()
        adapter.transport.is_connected = True
        sc.io.acp_adapter = adapter

        with patch("siada.config.config_loader.save_conf_field", return_value=True), \
                patch(
                    "siada.io.system_theme_detector.SystemThemeDetector.detect_theme",
                    side_effect=AssertionError("unexpected detection"),
                ) as detect:
            sc.cmd_theme(MagicMock(), "auto")

        detect.assert_not_called()
        adapter.transport.send_sync.assert_called_once()
        msg = adapter.transport.send_sync.call_args[0][0]
        assert msg.method == "ui/themeChanged"
        assert msg.params["theme"] == "dark"

    def test_skips_acp_push_when_disconnected(self):
        sc = _make_slash_commands()
        adapter = MagicMock()
        adapter.transport.is_connected = False
        sc.io.acp_adapter = adapter

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_theme(MagicMock(), "light")

        adapter.transport.send_sync.assert_not_called()

    def test_skips_acp_push_without_adapter(self):
        sc = _make_slash_commands()  # io.acp_adapter is None (TTY mode)

        with patch("siada.config.config_loader.save_conf_field", return_value=True):
            sc.cmd_theme(MagicMock(), "light")

        sc.io.print_info.assert_called_once_with("Theme switched to 'light'")

    def test_no_push_on_invalid_value(self):
        sc = _make_slash_commands()
        adapter = MagicMock()
        adapter.transport.is_connected = True
        sc.io.acp_adapter = adapter

        sc.cmd_theme(MagicMock(), "solarized")

        adapter.transport.send_sync.assert_not_called()


class TestResolveThemeForUi:
    """resolve_theme_for_ui maps conf values to concrete dark|light values
    the frontend understands without automatic detection."""

    def test_explicit_themes_pass_through_without_detection(self):
        with patch.object(std.SystemThemeDetector, "detect_theme") as detect:
            assert std.resolve_theme_for_ui("dark") == "dark"
            assert std.resolve_theme_for_ui("light") == "light"
        detect.assert_not_called()

    def test_auto_uses_dark_without_detection(self):
        with patch.object(std.SystemThemeDetector, "detect_theme", return_value="light") as detect:
            assert std.resolve_theme_for_ui("auto") == "dark"
        detect.assert_not_called()

    def test_auto_detection_failure_falls_back_to_dark(self):
        with patch.object(std.SystemThemeDetector, "detect_theme", return_value="unknown"):
            assert std.resolve_theme_for_ui("auto") == "dark"

    def test_auto_detection_exception_falls_back_to_dark(self):
        with patch.object(
            std.SystemThemeDetector, "detect_theme", side_effect=OSError("boom")
        ):
            assert std.resolve_theme_for_ui("auto") == "dark"

    def test_unknown_value_resolves_like_auto(self):
        with patch.object(std.SystemThemeDetector, "detect_theme", return_value="dark"):
            assert std.resolve_theme_for_ui(None) == "dark"

    def test_repeated_resolution_never_detects(self):
        with patch.object(
            std.SystemThemeDetector, "detect_theme", return_value="light"
        ) as detect:
            assert std.resolve_theme_for_ui("auto") == "dark"
            assert std.resolve_theme_for_ui("auto") == "dark"
        detect.assert_not_called()
