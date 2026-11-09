import { useEffect } from 'react';
import { useStdout } from '@jrichman/ink';
import { getNativeWindowsInput } from '../services/windowsConsole.js';
import { ENABLE_MOUSE_TRACKING, DISABLE_MOUSE_TRACKING } from '../utils/terminalMouse.js';
import { useNoAltScreen } from '../contexts/TerminalModeContext.js';

// Mouse reporting belongs to the terminal, so nested views share its lifetime.
const owners = new WeakMap<NodeJS.WriteStream, number>();

export function hasMouseTracking(stdout: NodeJS.WriteStream): boolean {
  return (owners.get(stdout) ?? 0) > 0;
}

export function useMouseTracking(enabled = true): void {
  const { stdout } = useStdout();
  const noAltScreen = useNoAltScreen();
  useEffect(() => {
    if (noAltScreen || !enabled || !stdout) return;
    const count = owners.get(stdout) ?? 0;
    owners.set(stdout, count + 1);
    if (count === 0 && !getNativeWindowsInput()) {
      // 1003 reports motion; 1006 uses SGR coordinates. OSC 22 requests an arrow.
      stdout.write(ENABLE_MOUSE_TRACKING + '\x1b]22;default\x1b\\');
    }
    return () => {
      const remaining = (owners.get(stdout) ?? 1) - 1;
      if (remaining > 0) owners.set(stdout, remaining);
      else {
        owners.delete(stdout);
        if (!getNativeWindowsInput()) stdout.write(DISABLE_MOUSE_TRACKING + '\x1b]22;\x1b\\');
      }
    };
  }, [enabled, stdout, noAltScreen]);
}