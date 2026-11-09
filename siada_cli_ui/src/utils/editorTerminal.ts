import { ENABLE_MOUSE_TRACKING, DISABLE_MOUSE_TRACKING } from './terminalMouse.js';

/**
 * Temporarily hand the terminal to a synchronous, inherited-stdio editor.
 * The synchronous callback prevents Ink or input handlers from running while
 * the editor owns the tty. Always repaint: even a no-op edit changes the screen.
 */
export function withEditorTerminal<T>(
  action: () => T,
  options: {
    stdin: NodeJS.ReadStream;
    stdout: NodeJS.WriteStream;
    alternateBuffer: boolean;
    kittyKeyboard: boolean;
    mouseTracking: boolean;
    repaint: () => void;
    nativeInput?: { suspend(): void; resume(): void };
  },
): T {
  const { stdin, stdout, alternateBuffer, kittyKeyboard, mouseTracking, repaint, nativeInput } = options;
  const wasRaw = stdin.isRaw;
  const wasFlowing = stdin.readableFlowing;
  // A synchronous editor blocks Node's event loop. Wait for the Win32 reader
  // to acknowledge suspension before that callback can acquire console input.
  nativeInput?.suspend();
  try {
    stdin.pause();
    if (!nativeInput && typeof stdin.setRawMode === 'function') stdin.setRawMode(false);
    if (stdout.isTTY) {
      stdout.write(DISABLE_MOUSE_TRACKING + '\x1b[?2004l');
      if (kittyKeyboard) stdout.write('\x1b[<u');
      if (alternateBuffer) stdout.write('\x1b[?7h\x1b[?1049l');
      stdout.write('\x1b[0m\x1b[?25h');
    }
    return action();
  } finally {
    if (stdout.isTTY) {
      if (alternateBuffer) stdout.write('\x1b[?1049h\x1b[?7l');
      stdout.write('\x1b[0m\x1b[?2004h');
      if (kittyKeyboard) stdout.write('\x1b[>1u');
      if (mouseTracking && !nativeInput) stdout.write(ENABLE_MOUSE_TRACKING + '\x1b]22;default\x1b\\');
    }
    if (nativeInput) nativeInput.resume();
    else {
      if (typeof stdin.setRawMode === 'function') stdin.setRawMode(Boolean(wasRaw));
      if (wasFlowing === true) stdin.resume();
    }
    // Ink's rerender clears both its frame cache and log-update's line cache.
    repaint();
  }
}