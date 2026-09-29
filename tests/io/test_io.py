import unittest
from io import StringIO

from rich.console import Console

from siada.io.color_settings import ColorSettings, RunningConfigColorSettings
from siada.io.io import InputOutput


def test_acp_input_does_not_construct_legacy_ui_or_print_prompt(monkeypatch, capsys):
    import builtins
    from unittest.mock import Mock

    original_import = builtins.__import__

    def reject_legacy_ui(name, *args, **kwargs):
        if name.startswith(("prompt_toolkit", "siada.io.custom_prompt_session")):
            raise AssertionError(f"Legacy UI imported: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_legacy_ui)
    monkeypatch.setattr(InputOutput, "_initialize_acp", lambda self, *a: None)
    monkeypatch.setattr(InputOutput, "_instance", None)
    io = InputOutput(acp_enabled=True, fancy_input=True)
    assert io.prompt_session is None
    assert not io.pretty
    io.ring_bell = Mock()
    monkeypatch.setattr("siada.io.stdin_interrupt_monitor.is_monitor_active", lambda: False)
    monkeypatch.setattr("sys.stdin", StringIO(
        '<<<SIADA_MSG_START>>>\nhello\n<<<SIADA_MSG_END>>>\n'
    ))
    assert io.get_input(display_rule=False) == "hello"
    assert capsys.readouterr().out == ""


def test_acp_input_returns_background_wakeup_without_prompt(monkeypatch, capsys):
    import threading
    from unittest.mock import Mock
    from siada.io.io import BACKGROUND_WAKEUP_SENTINEL

    monkeypatch.setattr(InputOutput, "_initialize_acp", lambda self, *a: None)
    monkeypatch.setattr(InputOutput, "_instance", None)
    io = InputOutput(acp_enabled=True)
    io.ring_bell = Mock()
    wakeup = threading.Event()
    wakeup.set()
    monkeypatch.setattr("siada.io.stdin_interrupt_monitor.is_monitor_active", lambda: False)
    monkeypatch.setattr("sys.stdin", StringIO(""))
    assert io.get_input(display_rule=False, wakeup_event=wakeup) == BACKGROUND_WAKEUP_SENTINEL
    assert capsys.readouterr().out == ""



class TestDisplayUserInput(unittest.TestCase):

    def test_display_with_pretty_and_color(self):
        """Demonstrates display_user_input with pretty=True and a color."""
        print(f"\n--- Running: {self.test_display_with_pretty_and_color.__doc__} ---")
        color_settings = ColorSettings(user_input_color="#123456")
        running_color_settings = RunningConfigColorSettings(pretty=True, color_settings=color_settings)
        io = InputOutput(pretty=True, running_color_settings=running_color_settings)
        
        # The console needs to support colors for this test.
        # It will print directly to the terminal.
        io._console = Console(force_terminal=True, color_system="truecolor")

        io.display_user_input("This is a colored test input.")
        print("--- End of Demo ---")

    def test_display_with_pretty_no_color(self):
        """Demonstrates display_user_input with pretty=True and no color."""
        print(f"\n--- Running: {self.test_display_with_pretty_no_color.__doc__} ---")
        color_settings = ColorSettings(user_input_color=None)
        running_color_settings = RunningConfigColorSettings(pretty=True, color_settings=color_settings)
        io = InputOutput(pretty=True, running_color_settings=running_color_settings)
        
        io._console = Console(force_terminal=True)

        io.display_user_input("This is a default color test input.")
        print("--- End of Demo ---")

    def test_display_not_pretty(self):
        """Demonstrates display_user_input with pretty=False."""
        print(f"\n--- Running: {self.test_display_not_pretty.__doc__} ---")
        color_settings = ColorSettings(user_input_color="#123456")
        running_color_settings = RunningConfigColorSettings(pretty=False, color_settings=color_settings)
        io = InputOutput(pretty=False, running_color_settings=running_color_settings)

        # When not pretty, console is simple.
        io._console = Console(no_color=True)

        io.display_user_input("This is a non-pretty test input.")
        print("--- End of Demo ---")


if __name__ == '__main__':
    unittest.main()
