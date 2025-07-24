import functools
import os
import subprocess
import webbrowser
from dataclasses import dataclass

from prompt_toolkit.completion import Completer, ThreadedCompleter
from prompt_toolkit.cursor_shapes import ModalCursorShapeConfig
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.output.vt100 import is_dumb_terminal
from prompt_toolkit.shortcuts import CompleteStyle, PromptSession
from prompt_toolkit.styles import Style
from pygments.lexers import MarkdownLexer
from rich.color import ColorParseError
from rich.console import Console
from rich.markdown import Markdown
from rich.style import Style as RichStyle
from rich.text import Text

from siada.io.components.mdstream import MarkdownStream
from siada.io.console_printer import ConsolePrinter
from siada.io.notification_command import NotificationCommandUtil
from .color_settings import ColorSettings
from .key_bindings import KeyBindingsFactory

# from .editor import pipe_editor

# Constants
NOTIFICATION_MESSAGE = "Siada is waiting for your input"


from siada.io.color_utils import ColorUtils


@dataclass
class ConfirmGroup:
    preference: str = None
    show_group: bool = True

    def __init__(self, items=None):
        if items is not None:
            self.show_group = len(items) > 1

class InputOutput:
    num_error_outputs = 0
    num_user_asks = 0
    clipboard_watcher = None
    bell_on_next_input = False
    notifications_command = None

    @staticmethod
    def _restore_multiline(func):
        """Decorator to restore multiline mode after function execution"""

        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            orig_multiline = self.multiline_mode
            self.multiline_mode = False
            try:
                return func(self, *args, **kwargs)
            except Exception:
                raise
            finally:
                self.multiline_mode = orig_multiline

        return wrapper

    def __init__(
        self,
        pretty=True,
        yes=None,
        input=None,
        output=None,
        color_settings: "ColorSettings" = None,
        encoding="utf-8",
        line_endings="platform",
        editingmode=EditingMode.EMACS,
        fancy_input=True,
        multiline_mode=False,
        notifications=False,
        notifications_command=None,
    ):
        self.placeholder = None
        self.interrupted = False
        self.never_prompts = set()
        self.editingmode = editingmode
        self.multiline_mode = multiline_mode
        self.bell_on_next_input = False
        self.notifications = notifications
        if notifications and notifications_command is None:
            self.notifications_command = (
                NotificationCommandUtil.get_default_notification_command()
            )
        else:
            self.notifications_command = notifications_command

        no_color = os.environ.get("NO_COLOR")
        if no_color is not None and no_color != "":
            pretty = False

        self.color_settings = color_settings or ColorSettings()
        self.user_input_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.user_input_color) if pretty else None
        )
        self.tool_output_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.tool_output_color) if pretty else None
        )
        self.tool_error_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.tool_error_color) if pretty else None
        )
        self.tool_warning_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.tool_warning_color) if pretty else None
        )
        self.tool_result_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.tool_result_color) if pretty else None
        )
        self.tool_call_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.tool_call_color) if pretty else None
        )
        self.assistant_output_color = ColorUtils.ensure_hash_prefix(
            self.color_settings.assistant_output_color
        )
        self.completion_menu_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.completion_menu_color) if pretty else None
        )
        self.completion_menu_bg_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.completion_menu_bg_color)
            if pretty
            else None
        )
        self.completion_menu_current_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.completion_menu_current_color)
            if pretty
            else None
        )
        self.completion_menu_current_bg_color = (
            ColorUtils.ensure_hash_prefix(self.color_settings.completion_menu_current_bg_color)
            if pretty
            else None
        )

        self.code_theme = self.color_settings.code_theme

        self.input = input
        self.output = output

        self.pretty = pretty
        if self.output:
            self.pretty = False

        self.yes = yes

        self.encoding = encoding
        valid_line_endings = {"platform", "lf", "crlf"}
        if line_endings not in valid_line_endings:
            raise ValueError(
                f"Invalid line_endings value: {line_endings}. "
                f"Must be one of: {', '.join(valid_line_endings)}"
            )
        self.newline = (
            None if line_endings == "platform" else "\n" if line_endings == "lf" else "\r\n"
        )

        self.prompt_session = None
        self.is_dumb_terminal = is_dumb_terminal()

        if self.is_dumb_terminal:
            self.pretty = False
            fancy_input = False

        if fancy_input:
            # Initialize PromptSession only if we have a capable terminal
            session_kwargs = {
                "input": self.input,
                "output": self.output,
                "lexer": PygmentsLexer(MarkdownLexer),
                "editing_mode": self.editingmode,
            }
            if self.editingmode == EditingMode.VI:
                session_kwargs["cursor"] = ModalCursorShapeConfig()
            try:
                self.prompt_session = PromptSession(**session_kwargs)
                self.console = Console()  # pretty console
                self._initialize_printer()
            except Exception as err:
                self.console = Console(force_terminal=False, no_color=True)
                self._initialize_printer()
                self.print_error(f"Can't initialize prompt toolkit: {err}")  # non-pretty
        else:
            self.console = Console(force_terminal=False, no_color=True)  # non-pretty
            self._initialize_printer()
            if self.is_dumb_terminal:
                self.print_info("Detected dumb terminal, disabling fancy input and pretty output.")

        # Validate color settings after console is initialized
        self._validate_color_settings()

    def _initialize_printer(self):
        """Initialize the console printer."""
        printer_colors = {
            "error": self.tool_error_color,
            "warning": self.tool_warning_color,
            "output": self.tool_output_color,
            "result": self.tool_result_color,
            "call": self.tool_call_color,
        }
        self.printer = ConsolePrinter(self.console, self.pretty, colors=printer_colors)

    def _validate_color_settings(self):
        """Validate configured color strings and reset invalid ones."""
        color_attributes = [
            "user_input_color",
            "tool_output_color",
            "tool_error_color",
            "tool_warning_color",
            "assistant_output_color",
            "completion_menu_color",
            "completion_menu_bg_color",
            "completion_menu_current_color",
            "completion_menu_current_bg_color",
        ]
        for attr_name in color_attributes:
            color_value = getattr(self, attr_name, None)
            if color_value:
                try:
                    # Try creating a style to validate the color
                    RichStyle(color=color_value)
                except ColorParseError as e:
                    self.console.print(
                        "[bold red]Warning:[/bold red] Invalid configuration for"
                        f" {attr_name}: '{color_value}'. {e}. Disabling this color."
                    )
                    setattr(self, attr_name, None)  # Reset invalid color to None

    def _get_style(self):
        style_dict = {}
        if not self.pretty:
            return Style.from_dict(style_dict)

        if self.user_input_color:
            style_dict.setdefault("", self.user_input_color)
            style_dict.update(
                {
                    "pygments.literal.string": f"bold italic {self.user_input_color}",
                }
            )

        # Conditionally add 'completion-menu' style
        completion_menu_style = []
        if self.completion_menu_bg_color:
            completion_menu_style.append(f"bg:{self.completion_menu_bg_color}")
        if self.completion_menu_color:
            completion_menu_style.append(self.completion_menu_color)
        if completion_menu_style:
            style_dict["completion-menu"] = " ".join(completion_menu_style)

        # Conditionally add 'completion-menu.completion.current' style
        completion_menu_current_style = []
        if self.completion_menu_current_bg_color:
            completion_menu_current_style.append(self.completion_menu_current_bg_color)
        if self.completion_menu_current_color:
            completion_menu_current_style.append(f"bg:{self.completion_menu_current_color}")
        if completion_menu_current_style:
            style_dict["completion-menu.completion.current"] = " ".join(
                completion_menu_current_style
            )

        return Style.from_dict(style_dict)

    def rule(self):
        if self.pretty:
            style = dict(style=self.user_input_color) if self.user_input_color else dict()
            self.console.rule(**style)
        else:
            print()

    def interrupt_input(self):
        if self.prompt_session and self.prompt_session.app:
            # Store any partial input before interrupting
            self.placeholder = self.prompt_session.app.current_buffer.text
            self.interrupted = True
            self.prompt_session.app.exit()

    def get_input(
        self,
        root: str,
        completer: Completer
    ):
        self.rule()

        # Ring the bell if needed
        self.ring_bell()

        show = ""
        # if rel_fnames:
        #     rel_read_only_fnames = [
        #         get_rel_fname(fname, root) for fname in (abs_read_only_fnames or [])
        #     ]
        #     show = self.format_files_for_input(rel_fnames, rel_read_only_fnames)

        prompt_prefix = ""
        if self.multiline_mode:
            prompt_prefix += "multi"
        prompt_prefix += "> "

        show += prompt_prefix
        self.prompt_prefix = prompt_prefix

        inp = ""
        multiline_input = False

        style = self._get_style()

        completer_instance = ThreadedCompleter(completer=completer)

        kb_factory = KeyBindingsFactory(self)
        kb = kb_factory.create_key_bindings()

        while True:
            if multiline_input:
                show = self.prompt_prefix

            try:
                if self.prompt_session:
                    # Use placeholder if set, then clear it
                    default = self.placeholder or ""
                    self.placeholder = None

                    self.interrupted = False
                    if not multiline_input:
                        if self.clipboard_watcher:
                            self.clipboard_watcher.start()

                    def get_continuation(width, line_number, is_soft_wrap):
                        return self.prompt_prefix

                    line = self.prompt_session.prompt(
                        show,
                        default=default,
                        completer=completer_instance,
                        reserve_space_for_menu=4,
                        complete_style=CompleteStyle.MULTI_COLUMN,
                        style=style,
                        key_bindings=kb,
                        complete_while_typing=True,
                        prompt_continuation=get_continuation,
                    )
                else:
                    line = input(show)

                # Check if we were interrupted by a file change
                if self.interrupted:
                    line = line or ""

            except EOFError:
                raise
            except Exception as err:
                import traceback

                self.print_error(str(err))
                self.print_error(traceback.format_exc())
                return ""
            except UnicodeEncodeError as err:
                self.print_error(str(err))
                return ""
            finally:
                if self.clipboard_watcher:
                    self.clipboard_watcher.stop()

            if line.strip("\r\n") and not multiline_input:
                stripped = line.strip("\r\n")
                if stripped == "{":
                    multiline_input = True
                    multiline_tag = None
                    inp += ""
                elif stripped[0] == "{":
                    # Extract tag if it exists (only alphanumeric chars)
                    tag = "".join(c for c in stripped[1:] if c.isalnum())
                    if stripped == "{" + tag:
                        multiline_input = True
                        multiline_tag = tag
                        inp += ""
                    else:
                        inp = line
                        break
                else:
                    inp = line
                    break
                continue
            elif multiline_input and line.strip():
                if multiline_tag:
                    # Check if line is exactly "tag}"
                    if line.strip("\r\n") == f"{multiline_tag}}}":
                        break
                    else:
                        inp += line + "\n"
                # Check if line is exactly "}"
                elif line.strip("\r\n") == "}":
                    break
                else:
                    inp += line + "\n"
            elif multiline_input:
                inp += line + "\n"
            else:
                inp = line
                break

        print()
        self.user_input(inp)
        return inp

    def display_user_input(self, inp):
        if self.pretty and self.user_input_color:
            style = dict(style=self.user_input_color)
        else:
            style = dict()

        self.console.print(Text(inp), **style)

    def offer_url(self, url, prompt="Open URL for more info?", allow_never=True):
        """Offer to open a URL in the browser, returns True if opened."""
        if url in self.never_prompts:
            return False
        if self.confirm_ask(prompt, subject=url, allow_never=allow_never):
            webbrowser.open(url)
            return True
        return False

    @_restore_multiline
    def confirm_ask(
        self,
        question,
        default="y",
        subject=None,
        explicit_yes_required=False,
        group=None,
        allow_never=False,
    ):
        self.num_user_asks += 1

        # Ring the bell if needed
        self.ring_bell()

        question_id = (question, subject)

        if question_id in self.never_prompts:
            return False

        if group and not group.show_group:
            group = None
        if group:
            allow_never = True

        valid_responses = ["yes", "no", "skip", "all"]
        options = " (Y)es/(N)o"
        if group:
            if not explicit_yes_required:
                options += "/(A)ll"
            options += "/(S)kip all"
        if allow_never:
            options += "/(D)on't ask again"
            valid_responses.append("don't")

        if default.lower().startswith("y"):
            question += options + " [Yes]: "
        elif default.lower().startswith("n"):
            question += options + " [No]: "
        else:
            question += options + f" [{default}]: "

        if subject:
            self.print_info()
            if "\n" in subject:
                lines = subject.splitlines()
                max_length = max(len(line) for line in lines)
                padded_lines = [line.ljust(max_length) for line in lines]
                padded_subject = "\n".join(padded_lines)
                self.print_info(padded_subject, bold=True)
            else:
                self.print_info(subject, bold=True)

        style = self._get_style()

        def is_valid_response(text):
            if not text:
                return True
            return text.lower() in valid_responses

        if self.yes is True:
            res = "n" if explicit_yes_required else "y"
        elif self.yes is False:
            res = "n"
        elif group and group.preference:
            res = group.preference
            self.user_input(f"{question}{res}", log_only=False)
        else:
            while True:
                try:
                    if self.prompt_session:
                        res = self.prompt_session.prompt(
                            question,
                            style=style,
                            complete_while_typing=False,
                        )
                    else:
                        res = input(question)
                except EOFError:
                    # Treat EOF (Ctrl+D) as if the user pressed Enter
                    res = default
                    break

                if not res:
                    res = default
                    break
                res = res.lower()
                good = any(valid_response.startswith(res) for valid_response in valid_responses)
                if good:
                    break

                error_message = f"Please answer with one of: {', '.join(valid_responses)}"
                self.print_error(error_message)

        res = res.lower()[0]

        if res == "d" and allow_never:
            self.never_prompts.add(question_id)
            hist = f"{question.strip()} {res}"
            return False

        if explicit_yes_required:
            is_yes = res == "y"
        else:
            is_yes = res in ("y", "a")

        is_all = res == "a" and group is not None and not explicit_yes_required
        is_skip = res == "s" and group is not None

        if group:
            if is_all and not explicit_yes_required:
                group.preference = "all"
            elif is_skip:
                group.preference = "skip"

        hist = f"{question.strip()} {res}"

        return is_yes

    @_restore_multiline
    def prompt_ask(self, question, default="", subject=None):
        self.num_user_asks += 1

        # Ring the bell if needed
        self.ring_bell()

        if subject:
            self.print_info()
            self.print_info(subject, bold=True)

        style = self._get_style()

        if self.yes is True:
            res = "yes"
        elif self.yes is False:
            res = "no"
        else:
            try:
                if self.prompt_session:
                    res = self.prompt_session.prompt(
                        question + " ",
                        default=default,
                        style=style,
                        complete_while_typing=True,
                    )
                else:
                    res = input(question + " ")
            except EOFError:
                # Treat EOF (Ctrl+D) as if the user pressed Enter
                res = default

        hist = f"{question.strip()} {res.strip()}"
        if self.yes in (True, False):
            self.print_info(hist)

        return res

    def print_error(self, message="", strip=True):
        self.num_error_outputs += 1
        self.printer.error(message)

    def print_warning(self, message="", strip=True):
        self.printer.warning(message)

    def print_tool_result(self, message="", strip=True):
        self.printer.result(message)

    def print_tool_call(self, message="", strip=True):
        self.printer.call(message)

    def print_info(self, *messages, log_only=False, bold=False):
        if log_only:
            return
        self.printer.output(*messages, bold=bold)

    def get_assistant_mdstream(self):
        mdargs = dict(
            style=self.assistant_output_color,
            code_theme=self.code_theme,
            inline_code_lexer="text",
        )
        mdStream = MarkdownStream(mdargs=mdargs)
        return mdStream

    def assistant_output(self, message, pretty=None):
        if not message:
            self.print_warning("Empty response received from LLM. Check your provider account?")
            return

        show_resp = message

        # Coder will force pretty off if fence is not triple-backticks
        if pretty is None:
            pretty = self.pretty

        if pretty:
            show_resp = Markdown(
                message, style=self.assistant_output_color, code_theme=self.code_theme
            )
        else:
            show_resp = Text(message or "(empty response)")

        self.console.print(show_resp)

    def set_placeholder(self, placeholder):
        """Set a one-time placeholder text for the next input prompt."""
        self.placeholder = placeholder

    def print(self, message=""):
        print(message)

    def llm_started(self):
        """Mark that the LLM has started processing, so we should ring the bell on next input"""
        self.bell_on_next_input = True

    def ring_bell(self):
        """Ring the terminal bell if needed and clear the flag"""
        if self.bell_on_next_input and self.notifications:
            if self.notifications_command:
                try:
                    result = subprocess.run(
                        self.notifications_command, shell=True, capture_output=True
                    )
                    if result.returncode != 0 and result.stderr:
                        error_msg = result.stderr.decode("utf-8", errors="replace")
                        self.print_warning(f"Failed to run notifications command: {error_msg}")
                except Exception as e:
                    self.print_warning(f"Failed to run notifications command: {e}")
            else:
                print("\a", end="", flush=True)  # Ring the bell
            self.bell_on_next_input = False  # Clear the flag

    def toggle_multiline_mode(self):
        """Toggle between normal and multiline input modes"""
        self.multiline_mode = not self.multiline_mode
        if self.multiline_mode:
            self.print_info(
                "Multiline mode: Enabled. Enter inserts newline, Alt-Enter submits text"
            )
        else:
            self.print_info(
                "Multiline mode: Disabled. Alt-Enter inserts newline, Enter submits text"
            )
