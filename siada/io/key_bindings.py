import functools
import signal

from prompt_toolkit.enums import EditingMode
from prompt_toolkit.filters import Condition, is_searching
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.vi_state import InputMode
from prompt_toolkit.keys import Keys

from siada.support.editor import pipe_editor


class KeyBindingsFactory:
    """A factory for creating key bindings for the IO instance."""
    def __init__(self, io_instance):
        self.io = io_instance

    def create_key_bindings(self):
        kb = KeyBindings()

        def suspend_to_bg(event):
            """Suspend currently running application."""
            event.app.suspend_to_background()

        @kb.add(Keys.ControlZ, filter=Condition(lambda: hasattr(signal, "SIGTSTP")))
        def _(event):
            "Suspend to background with ctrl-z"
            suspend_to_bg(event)

        @kb.add("c-space")
        def _(event):
            "Ignore Ctrl when pressing space bar"
            event.current_buffer.insert_text(" ")

        @kb.add("c-up")
        def _(event):
            "Navigate backward through history"
            event.current_buffer.history_backward()

        @kb.add("c-down")
        def _(event):
            "Navigate forward through history"
            event.current_buffer.history_forward()

        @kb.add("c-x", "c-e")
        def _(event):
            "Edit current input in external editor (like Bash)"
            buffer = event.current_buffer
            current_text = buffer.text

            # Open the editor with the current text
            edited_text = pipe_editor(input_data=current_text, suffix="md")

            # Replace the buffer with the edited text, strip any trailing newlines
            buffer.text = edited_text.rstrip("\n")

            # Move cursor to the end of the text
            buffer.cursor_position = len(buffer.text)

        @kb.add("enter", eager=True, filter=~is_searching)
        def _(event):
            "Handle Enter key press"
            if self.io.multiline_mode and not (
                self.io.editingmode == EditingMode.VI
                and event.app.vi_state.input_mode == InputMode.NAVIGATION
            ):
                # In multiline mode and if not in vi-mode or vi navigation/normal mode,
                # Enter adds a newline
                event.current_buffer.insert_text("\n")
            else:
                # In normal mode, Enter submits
                event.current_buffer.validate_and_handle()

        @kb.add("escape", "enter", eager=True, filter=~is_searching)  # This is Alt+Enter
        def _(event):
            "Handle Alt+Enter key press"
            if self.io.multiline_mode:
                # In multiline mode, Alt+Enter submits
                event.current_buffer.validate_and_handle()
            else:
                # In normal mode, Alt+Enter adds a newline
                event.current_buffer.insert_text("\n")

        return kb 