from rich.console import Console
from rich.style import Style as RichStyle
from rich.text import Text

from siada.io.color_utils import ColorUtils


class ConsolePrinter:
    """A utility class for handling styled console output."""

    def __init__(self, console: Console, pretty: bool = True, colors: dict = None):
        """
        Initializes the ConsolePrinter.
        :param console: The rich Console object.
        :param pretty: Whether to use pretty output with colors and styles.
        :param colors: A dictionary mapping message types to color strings.
                       Expected keys: 'error', 'warning', 'output'.
        """
        self.console = console
        self.pretty = pretty
        self.colors = colors if colors else {}

    def print_messages(self, *messages, color_name: str = None, bold: bool = False):
        """Internal method to print styled messages to the console."""
        color = self.colors.get(color_name)
        
        # Convert each message to Text, treating each message as a whole unit
        text_messages = [Text(str(msg)) for msg in messages]
        style_dict = {}

        if self.pretty:
            if color:
                style_dict["color"] = ColorUtils.ensure_hash_prefix(color)
            if bold:
                style_dict["reverse"] = True

        style = RichStyle(**style_dict)

        try:
            self.console.print(*text_messages, style=style)
        except UnicodeEncodeError:
            # Fallback to ASCII-safe output
            plain_messages = [m.plain if isinstance(m, Text) else str(m) for m in text_messages]
            safe_messages = [str(m).encode("ascii", errors="replace").decode("ascii") for m in plain_messages]
            self.console.print(*safe_messages, style=style)

    def error(self, *messages):
        """Prints error messages."""
        self.print_messages(*messages, color_name='error')

    def warning(self, *messages):
        """Prints warning messages."""
        self.print_messages(*messages, color_name='warning')

    def output(self, *messages, bold: bool = False):
        """Prints standard tool output."""
        self.print_messages(*messages, color_name='output', bold=bold)

    def print(self, *args, **kwargs):
        self.console.print(*args, **kwargs)

    def result(self, *messages):
        """Prints tool result messages."""
        self.print_messages(*messages, color_name='result')

    def call(self, *messages):
        """Prints tool call messages."""
        self.print_messages(*messages, color_name='call') 