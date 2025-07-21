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

    def _print_single_message(self, message, color_name: str = None):
        """Internal method to print a single styled message to the console."""
        if not isinstance(message, Text):
            message = Text(str(message))

        color = self.colors.get(color_name)
        style_dict = {}

        if self.pretty and color:
            style_dict["color"] = ColorUtils.ensure_hash_prefix(color)
        
        style = RichStyle(**style_dict) if style_dict else None

        try:
            self.console.print(message, style=style)
        except UnicodeEncodeError:
            # Fallback to ASCII-safe output
            safe_message = message.plain.encode("ascii", errors="replace").decode("ascii")
            self.console.print(safe_message, style=style)

    def _print_output_messages(self, *messages, color_name: str = None, bold: bool = False):
        """Internal method to print styled messages to the console for tool output."""
        color = self.colors.get(color_name)
        
        text_messages = list(map(Text, messages))
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

    def error(self, message: str = ""):
        """Prints an error message."""
        self._print_single_message(message, color_name='error')

    def warning(self, message: str = ""):
        """Prints a warning message."""
        self._print_single_message(message, color_name='warning')

    def output(self, *messages, bold: bool = False):
        """Prints standard tool output."""
        self._print_output_messages(*messages, color_name='output', bold=bold) 