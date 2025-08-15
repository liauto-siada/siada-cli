import unittest
from io import StringIO

from rich.console import Console

from siada.io.color_settings import ColorSettings, RunningConfigColorSettings
from siada.io.io import InputOutput


class TestDisplayUserInput(unittest.TestCase):

    def test_display_with_pretty_and_color(self):
        """Demonstrates display_user_input with pretty=True and a color."""
        print(f"\n--- Running: {self.test_display_with_pretty_and_color.__doc__} ---")
        color_settings = ColorSettings(user_input_color="#123456")
        running_color_settings = RunningConfigColorSettings(pretty=True, color_settings=color_settings)
        io = InputOutput(pretty=True, running_color_settings=running_color_settings)
        
        # The console needs to support colors for this test.
        # It will print directly to the terminal.
        io.console = Console(force_terminal=True, color_system="truecolor")

        io.display_user_input("This is a colored test input.")
        print("--- End of Demo ---")

    def test_display_with_pretty_no_color(self):
        """Demonstrates display_user_input with pretty=True and no color."""
        print(f"\n--- Running: {self.test_display_with_pretty_no_color.__doc__} ---")
        color_settings = ColorSettings(user_input_color=None)
        running_color_settings = RunningConfigColorSettings(pretty=True, color_settings=color_settings)
        io = InputOutput(pretty=True, running_color_settings=running_color_settings)
        
        io.console = Console(force_terminal=True)

        io.display_user_input("This is a default color test input.")
        print("--- End of Demo ---")

    def test_display_not_pretty(self):
        """Demonstrates display_user_input with pretty=False."""
        print(f"\n--- Running: {self.test_display_not_pretty.__doc__} ---")
        color_settings = ColorSettings(user_input_color="#123456")
        running_color_settings = RunningConfigColorSettings(pretty=False, color_settings=color_settings)
        io = InputOutput(pretty=False, running_color_settings=running_color_settings)

        # When not pretty, console is simple.
        io.console = Console(no_color=True)

        io.display_user_input("This is a non-pretty test input.")
        print("--- End of Demo ---")


if __name__ == '__main__':
    unittest.main()
