#!/usr/bin/env python

"""
Thread-based, killable spinner utility with beautiful animations and colors.

Features:
- Unicode braille patterns for smooth animation
- Color support with automatic terminal detection
- Graceful fallback to ASCII for limited terminals
- Thread-safe operation

Use it like:

    from siada.support.spinner import WaitingSpinner

    spinner = WaitingSpinner("Waiting for LLM")
    spinner.start()
    ...  # long task
    spinner.stop()
    
Or as a context manager:

    with WaitingSpinner("Processing...") as spinner:
        # long task
        pass
"""

import os
import sys
import threading
import time

from rich.console import Console
from rich.text import Text


class Spinner:
    """
    Modern, colorful spinner with smooth unicode animations.

    Features:
    - Uses unicode braille patterns for smooth, professional animation
    - Automatic color detection and beautiful color cycling
    - Graceful fallback to ASCII for limited terminals
    - Optimized rendering with Rich console integration
    """

    last_frame_idx = 0  # Class variable to store the last frame index

    def __init__(self, text: str, text_color: str = "bright_white"):
        self.text = text
        self.text_color = text_color
        self.start_time = time.time()
        self.last_update = 0.0
        self.visible = False
        self.is_tty = sys.stdout.isatty()
        self.console = Console()
        self.use_colors = self._supports_colors()

        # Modern spinner patterns with better visual appeal
        if self._supports_unicode() and self.use_colors:
            # Beautiful unicode spinner with colors
            self.frames = [
                "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"
            ]
            self.colors = ["cyan", "bright_cyan", "blue", "bright_blue", "magenta", "bright_magenta"]
            self.scan_char = "⠋"
        elif self._supports_unicode():
            # Unicode without colors
            self.frames = [
                "⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"
            ]
            self.colors = None
            self.scan_char = "⠋"
        else:
            # Fallback to ASCII with improved pattern
            self.frames = [
                "|", "/", "-", "\\", "|", "/", "-", "\\"
            ]
            self.colors = None
            self.scan_char = "|"

        self.frame_idx = Spinner.last_frame_idx  # Initialize from class variable
        self.animation_len = 1  # Single character spinner
        self.last_display_len = 0  # Length of the last spinner line (frame + text)

    def _supports_unicode(self) -> bool:
        """Check if terminal supports unicode without side effects."""
        if not self.is_tty:
            return False
        try:
            # Test encoding capability without actually writing to stdout
            test_char = "⠋"
            test_char.encode(sys.stdout.encoding or 'utf-8')
            return True
        except (UnicodeEncodeError, AttributeError, LookupError):
            return False
        except Exception:
            return False

    def _supports_colors(self) -> bool:
        """Check if terminal supports colors"""
        if not self.is_tty:
            return False
        # Check environment variables that indicate color support
        term = os.environ.get('TERM', '').lower()
        colorterm = os.environ.get('COLORTERM', '').lower()
        return (
            'color' in term or 
            term in ('xterm', 'xterm-256color', 'screen', 'tmux') or
            colorterm in ('truecolor', '24bit') or
            hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
        )

    def _next_frame(self) -> str:
        """Get the next frame without applying colors (colors applied in step method)."""
        frame = self.frames[self.frame_idx]
        self.frame_idx = (self.frame_idx + 1) % len(self.frames)
        Spinner.last_frame_idx = self.frame_idx  # Update class variable
        return frame
    
    def _get_current_color(self) -> str:
        """Get the current color for the spinner frame."""
        if self.use_colors and self.colors:
            return self.colors[self.frame_idx % len(self.colors)]
        return "white"
    
    def set_text_color(self, color: str):
        """Set the color for the spinner text."""
        self.text_color = color
    
    def set_text(self, text: str, color: str = None):
        """Set the spinner text and optionally change its color."""
        self.text = text
        if color is not None:
            self.text_color = color

    def step(self, text: str = None) -> None:
        """Update the spinner animation and optionally change the text."""
        if text is not None:
            self.text = text

        if not self.is_tty:
            return

        try:
            now = time.time()
            if not self.visible and now - self.start_time >= 0.5:
                self.visible = True
                self.last_update = 0.0
                if self.is_tty:
                    self.console.show_cursor(False)

            if not self.visible or now - self.last_update < 0.1:
                return

            self.last_update = now
            frame_str = self._next_frame()
        except Exception:
            # If anything goes wrong, just skip this frame
            return

        # Create the spinner line with consistent formatting
        if self.use_colors and self.colors:
            # For colored output, use rich text formatting
            current_color = self._get_current_color()
            text_content = Text()
            text_content.append(frame_str, style=f"bold {current_color}")
            text_content.append(f" {self.text}", style=self.text_color)
            
            # Clear the line and print with rich
            sys.stdout.write("\r")
            with self.console.capture() as capture:
                self.console.print(text_content, end="")
            output = capture.get()
            sys.stdout.write(output)
            self.last_display_len = len(frame_str) + 1 + len(self.text)  # Approximate length
        else:
            # Simple output for terminals without color support
            line_to_display = f"{frame_str} {self.text}"
            
            # Determine the maximum width for the spinner line
            max_spinner_width = self.console.width - 2 if self.console.width > 2 else 0
            if max_spinner_width > 0 and len(line_to_display) > max_spinner_width:
                line_to_display = line_to_display[:max_spinner_width]

            # Calculate padding to clear any remnants from a longer previous line
            padding_to_clear = " " * max(0, self.last_display_len - len(line_to_display))

            # Write the spinner frame and text
            sys.stdout.write(f"\r{line_to_display}{padding_to_clear}")
            self.last_display_len = len(line_to_display)

        sys.stdout.flush()

    def end(self) -> None:
        """Stop the spinner and clean up the display."""
        try:
            if self.visible and self.is_tty:
                # Clear the current line more reliably
                sys.stdout.write("\r\033[K")  # \033[K clears from cursor to end of line
                sys.stdout.flush()
                self.console.show_cursor(True)
        except Exception:
            # If cleanup fails, just continue - better than crashing
            pass
        finally:
            self.visible = False


class WaitingSpinner:
    """Background spinner that can be started/stopped safely and restarted."""

    def __init__(self, text: str = "Waiting for LLM", delay: float = 0.15, text_color: str = "bright_cyan"):
        self.text = text
        self.text_color = text_color
        self.delay = delay
        self.spinner = None
        self._stop_event = None
        self._thread = None

    def _spin(self):
        """Internal spinning loop."""
        if self.spinner is None:
            return
        while not self._stop_event.is_set():
            self.spinner.step()
            time.sleep(self.delay)
        self.spinner.end()

    def start(self):
        """Start the spinner in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return  # Already running
            
        # Create fresh instances for restart capability
        self.spinner = Spinner(self.text, self.text_color)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        """Request the spinner to stop and wait briefly for the thread to exit."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=self.delay * 2)  # Give more time for cleanup
        if self.spinner is not None:
            self.spinner.end()
            
    def update_text(self, text: str, color: str = None):
        """Update the spinner text dynamically and optionally change its color."""
        self.text = text
        if color is not None:
            self.text_color = color
        if self.spinner is not None:
            if color is not None:
                self.spinner.set_text(text, color)
            else:
                self.spinner.text = text
    
    def set_text_color(self, color: str):
        """Set the color for the spinner text."""
        self.text_color = color
        if self.spinner is not None:
            self.spinner.set_text_color(color)

    # Allow use as a context-manager
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


def main():
    """Demo the improved spinner with colors and unicode."""
    print("🎨 Testing the colorful spinner...")
    print("Press Ctrl+C to stop")
    
    # Test the basic Spinner with different text colors
    print("\n🔸 Testing basic Spinner with color changes...")
    spinner = Spinner("Starting with white text...", "bright_white")
    try:
        for i in range(100):
            time.sleep(0.1)
            if i == 20:
                spinner.set_text("Now in green! 🟢", "bright_green")
            elif i == 40:
                spinner.set_text("Switching to red! 🔴", "bright_red")
            elif i == 60:
                spinner.set_text("Beautiful blue! 🔵", "bright_blue")
            elif i == 80:
                spinner.set_text("Magnificent magenta! 🟣", "bright_magenta")
            else:
                spinner.step()
        spinner.end()
        print("✅ Color-changing spinner test completed!")
        
        # Test the WaitingSpinner with color changes
        print("\n🔸 Testing WaitingSpinner with dynamic colors...")
        with WaitingSpinner("Starting in cyan...", text_color="bright_cyan") as waiting_spinner:
            time.sleep(1)
            waiting_spinner.update_text("Now in yellow! ⚡", "bright_yellow")
            time.sleep(1)
            waiting_spinner.set_text_color("bright_red")
            waiting_spinner.update_text("Finishing in red! 🚀")
            time.sleep(1)
        
        print("✅ All colorful tests completed successfully! 🌈")
        
    except KeyboardInterrupt:
        print("\n❌ Interrupted by user.")
    finally:
        spinner.end()


if __name__ == "__main__":
    main()
