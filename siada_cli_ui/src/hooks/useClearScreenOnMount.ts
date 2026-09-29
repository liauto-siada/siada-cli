/**
 * Clear the terminal and home the cursor when a fullscreen view mounts.
 *
 * Ink writes each new frame wherever the previous frame ended — mid-screen
 * after chat history — so even a frame that fits the terminal can scroll
 * its top rows (header, active item) into scrollback on the first paint.
 * Clearing once on mount makes the first frame start at row 1.
 *
 * Returns `true` once the clear has been issued: render nothing until then,
 * so the component's first real frame is painted after the clear (Ink
 * dedupes identical frames, so repainting the same frame after the clear
 * would be a no-op and leave the screen blank). Mirrors
 * MessageList.refreshStatic's clearTerminal + DEC 2026 sync-output hold.
 */

import { useEffect, useState } from 'react';
import { useStdout } from '@jrichman/ink';
import ansiEscapes from 'ansi-escapes';
import { beginSyncOutput, endSyncOutput } from '../utils/stdio.js';

export function useClearScreenOnMount(): boolean {
  const { stdout } = useStdout();
  const [cleared, setCleared] = useState(false);

  useEffect(() => {
    if (cleared || !stdout) return;
    // Hold DEC 2026 synchronized output so supporting terminals paint the
    // clear + repaint atomically (no blank flash). No-op elsewhere; the
    // sync channel also has a 1s safety timeout.
    beginSyncOutput();
    stdout.write(ansiEscapes.clearTerminal);
    setTimeout(endSyncOutput, 150);
    setCleared(true);
  }, [stdout, cleared]);

  return cleared;
}
