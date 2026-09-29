/**
 * Terminal stdio utilities
 * 
 * Provides safe stdout/stderr proxies that bypass any monkey-patching
 * to ensure stable terminal output.
 */

import { isSynchronizedOutputSupported } from './terminalDetector.js';

// Capture the original stdout and stderr write methods before any monkey patching occurs.
const originalStdoutWrite = process.stdout.write.bind(process.stdout);
const originalStderrWrite = process.stderr.write.bind(process.stderr);

// ---------------------------------------------------------------------------
// DEC 2026 synchronized output (anti-flicker)
//
// Ink renders each frame as erase-previous-lines + rewrite. Without
// synchronization the terminal paints the intermediate blank state, which is
// the visible "flicker" during streaming. Wrapping every frame in BSU/ESU
// (same mechanism as claude-code's ink fork, see terminalDetector.ts) makes
// the whole frame atomic: the old frame stays on screen until ESU arrives.
//
// Frames are coalesced per macrotask: Ink emits one frame as several
// synchronous writes (e.g. log.clear() + static output + main output when a
// <Static> item is committed), so the first write opens BSU and ESU is
// appended once the current macrotask drains. A manual hold
// (beginSyncOutput/endSyncOutput) covers cross-frame sequences like
// MessageList.refreshStatic() (clearTerminal + Static remount, where the
// repaint happens in a later React render).
// ---------------------------------------------------------------------------

const BSU = '\x1b[?2026h';
const ESU = '\x1b[?2026l';

// Force-close a manually held sync session after this long — a bug must never
// leave the terminal frozen (it would stop painting anything).
const SYNC_SAFETY_TIMEOUT_MS = 1000;

let syncSupported: boolean | null = null;
let syncOpen = false; // BSU written, ESU not yet written
let syncHoldCount = 0; // manual holds (beginSyncOutput)
let esuTimer: ReturnType<typeof setTimeout> | null = null;
let syncSafetyTimer: ReturnType<typeof setTimeout> | null = null;

function isSyncEnabled(): boolean {
  if (syncSupported === null) {
    // Resolved once — terminal capabilities don't change mid-session.
    syncSupported = isSynchronizedOutputSupported();
  }
  return syncSupported;
}

function writeEsu(): void {
  if (esuTimer) {
    clearTimeout(esuTimer);
    esuTimer = null;
  }
  if (syncOpen) {
    originalStdoutWrite(ESU);
    syncOpen = false;
  }
}

function scheduleEsu(): void {
  if (esuTimer) clearTimeout(esuTimer);
  esuTimer = setTimeout(() => {
    esuTimer = null;
    // A manual hold keeps the session open across frames.
    if (syncHoldCount === 0) writeEsu();
  }, 0);
  esuTimer.unref?.();
}

// Abrupt exits (uncaughtException → process.exit) skip pending ESU timers,
// which would leave the terminal stuck buffering in sync mode. Flush on exit.
process.on('exit', () => {
  if (syncOpen) writeEsu();
});

/**
 * Begin a manual synchronized-output hold. While held, frame writes are
 * deferred by the terminal until endSyncOutput(). Use for clear+repaint
 * sequences that span multiple React renders. No-op when DEC 2026 is
 * unsupported. Safe to nest; a safety timeout force-closes after 1s.
 */
export function beginSyncOutput(): void {
  if (!isSyncEnabled()) return;
  syncHoldCount++;
  if (syncSafetyTimer) clearTimeout(syncSafetyTimer);
  syncSafetyTimer = setTimeout(() => {
    syncSafetyTimer = null;
    syncHoldCount = 0;
    writeEsu();
  }, SYNC_SAFETY_TIMEOUT_MS);
  syncSafetyTimer.unref?.();
}

/**
 * End a manual synchronized-output hold, flushing the deferred frame.
 */
export function endSyncOutput(): void {
  if (!isSyncEnabled() || syncHoldCount === 0) return;
  syncHoldCount--;
  if (syncHoldCount === 0) {
    if (syncSafetyTimer) {
      clearTimeout(syncSafetyTimer);
      syncSafetyTimer = null;
    }
    writeEsu();
  }
}

/**
 * Writes to the real stdout, bypassing any monkey patching on process.stdout.write.
 * When the terminal supports DEC 2026, wraps the write in a synchronized-output
 * session (BSU … ESU) so each rendered frame paints atomically.
 */
export function writeToStdout(
  chunk: Uint8Array | string,
  encodingOrCb?: BufferEncoding | ((err?: NodeJS.ErrnoException | null) => void),
  cb?: (err?: NodeJS.ErrnoException | null) => void,
): boolean {
  if (!isSyncEnabled()) {
    return originalStdoutWrite(chunk, encodingOrCb as BufferEncoding, cb);
  }

  let data = chunk;
  if (!syncOpen) {
    data =
      typeof chunk === 'string'
        ? BSU + chunk
        : Buffer.concat([Buffer.from(BSU), chunk]);
    syncOpen = true;
  }
  scheduleEsu();
  return originalStdoutWrite(data, encodingOrCb as BufferEncoding, cb);
}

/**
 * Writes to the real stderr, bypassing any monkey patching on process.stderr.write.
 */
export function writeToStderr(
  ...args: Parameters<typeof process.stderr.write>
): boolean {
  return originalStderrWrite(...args);
}

/**
 * Creates proxies for process.stdout and process.stderr that use the real write methods
 * (writeToStdout and writeToStderr) bypassing any monkey patching.
 * This is used to write to the real output even when stdio is patched by other libraries.
 * 
 * Critical for Terminal.app stability:
 * - Prevents conflicts with libraries that patch console
 * - Ensures consistent write behavior
 * - Reduces memory pressure from stdout conflicts
 * 
 * @returns Object with proxied stdout and stderr
 */
export function createWorkingStdio() {
  const inkStdout = new Proxy(process.stdout, {
    get(target, prop, receiver) {
      if (prop === 'write') {
        return writeToStdout;
      }
      const value = Reflect.get(target, prop, receiver);
      if (typeof value === 'function') {
        return value.bind(target);
      }
      return value;
    },
  });

  const inkStderr = new Proxy(process.stderr, {
    get(target, prop, receiver) {
      if (prop === 'write') {
        return writeToStderr;
      }
      const value = Reflect.get(target, prop, receiver);
      if (typeof value === 'function') {
        return value.bind(target);
      }
      return value;
    },
  });

  return { stdout: inkStdout, stderr: inkStderr };
}

/**
 * Monkey patches process.stdout.write and process.stderr.write to redirect output.
 * This prevents stray output from libraries from corrupting the UI.
 * Returns a cleanup function that restores the original write methods.
 * 
 * Note: Use createWorkingStdio() for Ink render to bypass this patching.
 */
export function patchStdio(
  onStdout?: (chunk: string) => void,
  onStderr?: (chunk: string) => void
): () => void {
  const previousStdoutWrite = process.stdout.write;
  const previousStderrWrite = process.stderr.write;

  process.stdout.write = (
    chunk: Uint8Array | string,
    encodingOrCb?:
      | BufferEncoding
      | ((err?: NodeJS.ErrnoException | null) => void),
    cb?: (err?: NodeJS.ErrnoException | null) => void,
  ) => {
    const text = typeof chunk === 'string' ? chunk : chunk.toString();
    if (onStdout) {
      onStdout(text);
    }
    const callback = typeof encodingOrCb === 'function' ? encodingOrCb : cb;
    if (callback) {
      callback();
    }
    return true;
  };

  process.stderr.write = (
    chunk: Uint8Array | string,
    encodingOrCb?:
      | BufferEncoding
      | ((err?: NodeJS.ErrnoException | null) => void),
    cb?: (err?: NodeJS.ErrnoException | null) => void,
  ) => {
    const text = typeof chunk === 'string' ? chunk : chunk.toString();
    if (onStderr) {
      onStderr(text);
    }
    const callback = typeof encodingOrCb === 'function' ? encodingOrCb : cb;
    if (callback) {
      callback();
    }
    return true;
  };

  return () => {
    process.stdout.write = previousStdoutWrite;
    process.stderr.write = previousStderrWrite;
  };
}
