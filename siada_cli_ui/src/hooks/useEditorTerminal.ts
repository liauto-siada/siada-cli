import { createContext, useCallback, useContext } from 'react';
import { useApp, useStdout } from '@jrichman/ink';
import { shouldEnableKittyKeyboard } from '../contexts/KeypressContext.js';
import { withEditorTerminal } from '../utils/editorTerminal.js';
import { hasMouseTracking } from './useMouseTracking.js';
import { getNativeWindowsInput } from '../services/windowsConsole.js';

// The launcher owns the choice of terminal buffer, including --no-alternate-buffer.
export const EditorTerminalContext = createContext(false);

export function useEditorTerminal() {
  const alternateBuffer = useContext(EditorTerminalContext);
  const { stdout } = useStdout();
  const { rerender } = useApp();
  return useCallback(<T,>(action: () => T): T => withEditorTerminal(action, {
    stdin: process.stdin,
    stdout,
    alternateBuffer,
    kittyKeyboard: stdout.isTTY && shouldEnableKittyKeyboard(),
    mouseTracking: hasMouseTracking(stdout),
    nativeInput: getNativeWindowsInput(),
    repaint: rerender,
  }), [alternateBuffer, stdout, rerender]);
}