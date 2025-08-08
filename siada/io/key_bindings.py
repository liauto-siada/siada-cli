import functools
import signal

from prompt_toolkit.enums import EditingMode
from prompt_toolkit.filters import Condition, is_searching, has_completions
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

        @kb.add("enter", eager=True, filter=~is_searching & ~has_completions)
        def _(event):
            "Handle Enter key press when no completions are shown"
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

        @kb.add("enter", eager=True, filter=~is_searching & has_completions)
        def _(event):
            "Handle Enter key press when completions are shown"
            buffer = event.current_buffer
            
            # Check if this is an @ command completion using cursor position (consistent with completer.py)
            text_before_cursor = buffer.document.text_before_cursor
            at_pos = text_before_cursor.rfind("@")
            is_at_command = at_pos != -1
            
            if buffer.complete_state and buffer.complete_state.completions:
                # Ensure first completion is selected by default if none is currently selected
                if buffer.complete_state.current_completion is None:
                    # Move to first completion to ensure it's highlighted
                    buffer.complete_next()
                
                # Accept the currently selected completion
                if buffer.complete_state.current_completion:
                    buffer.apply_completion(buffer.complete_state.current_completion)
                    
                    # For @ commands, only accept completion without submitting
                    # For other commands (like /), accept completion and submit
                    if not is_at_command:
                        # For non-@ commands, also submit after accepting completion
                        if self.io.multiline_mode and not (
                            self.io.editingmode == EditingMode.VI
                            and event.app.vi_state.input_mode == InputMode.NAVIGATION
                        ):
                            # In multiline mode, Enter adds a newline after accepting completion
                            buffer.insert_text("\n")
                        else:
                            # In normal mode, Enter submits after accepting completion
                            buffer.validate_and_handle()
            else:
                # No completions available, just handle enter normally
                if self.io.multiline_mode and not (
                    self.io.editingmode == EditingMode.VI
                    and event.app.vi_state.input_mode == InputMode.NAVIGATION
                ):
                    # In multiline mode, Enter adds a newline
                    buffer.insert_text("\n")
                else:
                    # In normal mode, Enter submits
                    buffer.validate_and_handle()

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
