/**
 * Regression tests for the UI credential log-leak fix.
 *
 * The previous logging schema recorded keystrokes and bracketed paste:
 *   - `process_stdin_data` logged the raw chunk plus its hex dump,
 *   - `broadcast` logged `key.name` + `key.sequence` (a typed secret could be
 *     rebuilt character by character),
 *   - `bufferPaste done` logged `cleanedPreview` (the first 80 chars of the
 *     pasted text, e.g. an API key).
 * On unmount the provider also removed the wrong function from
 * `process.stdin`, so every mount/unmount cycle left a live stdin listener
 * behind.
 *
 * These tests drive the real `KeypressProvider` through a controlled,
 * in-memory stdin (the native terminal is never touched: no raw mode, no
 * reads from the real fd) and assert that
 *   1. key delivery is unchanged - the subscriber still receives the typed
 *      characters and the pasted text byte-for-byte,
 *   2. no logger call carries the secret, a fragment of it, or a
 *      per-character/hex payload, while the non-content metadata
 *      (lengths/flags) is still logged,
 *   3. unmounting removes the very listener the provider registered.
 *
 * Run with a throwaway HOME (`HOME=$(mktemp -d)`) so the real user log file
 * and config are never used.
 */

import React from 'react';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { KeypressProvider, useKeypress } from '../src/contexts/KeypressContext.js';
import type { Key } from '../src/contexts/KeypressContext.js';
import { logger } from '../src/utils/logger.js';
import { SiadaACPAdapter } from '../src/acp/adapter.js';
import { AppProvider } from '../src/store/context.js';
import { InputPromptWithWrapUseKPC } from '../src/components/Input/InputPromptWithWrapUseKPC.js';
import { slashCommandService } from '../src/services/slashCommandService.js';

vi.mock('../src/hooks/useCommandCompletion.js', () => ({
  useCommandCompletion: () => ({
    suggestions: [], activeIndex: 0, isLoading: false, showSuggestions: false,
    visibleStartIndex: 0, mode: 'IDLE', navigateUp: vi.fn(), navigateDown: vi.fn(),
    acceptSuggestion: () => null, reset: vi.fn(),
  }),
}));

vi.mock('../src/hooks/useShellHistory.js', () => ({
  useShellHistory: () => ({
    addCommand: vi.fn(), navigateUp: vi.fn(), navigateDown: vi.fn(), resetIndex: vi.fn(),
  }),
}));

const SECRET_TYPED = 'hunter2-API-KEY-9f4c';
const SECRET_PASTED = 'pasted-api-key-7b21';

/** In-memory stand-in for process.stdin: no TTY, no raw mode, no real reads. */
class ControlledStdin extends PassThrough {
  isTTY = false;
  isRaw = false;
  setRawMode = (enabled: boolean): this => {
    this.isRaw = enabled;
    return this;
  };
}

const stdinDescriptor = Object.getOwnPropertyDescriptor(process, 'stdin')!;

let fakeStdin: ControlledStdin;
let stdoutTTYDescriptor: PropertyDescriptor | undefined;
let savedEnv: Record<string, string | undefined> = {};

/** Collect every logger call instead of writing it to console/file. */
type LoggerCall = { level: string; args: any[] };
let loggerCalls: LoggerCall[] = [];

function captureLoggerCalls(): void {
  loggerCalls = [];
  for (const level of ['debug', 'info', 'warn', 'error'] as const) {
    vi.spyOn(logger, level).mockImplementation((...args: any[]) => {
      loggerCalls.push({ level, args });
    });
  }
}

/** Full serialized text of everything that would have reached the log file. */
function loggedText(): string {
  return loggerCalls
    .map((call) =>
      call.args
        .map((arg) => (typeof arg === 'string' ? arg : JSON.stringify(arg)))
        .join(' '),
    )
    .join('\n');
}

/** All context objects logged for a given `operation` field. */
function loggedContexts(operation: string): any[] {
  return loggerCalls
    .map((call) => call.args[1])
    .filter((context) => context && context.operation === operation);
}

/** The `\xNN` hex dump representation the old code logged for stdin chunks. */
function hexDump(text: string): string {
  return Array.from(text)
    .map((char) => '\\x' + char.charCodeAt(0).toString(16).padStart(2, '0'))
    .join('');
}

const tick = (ms = 25) => new Promise((resolve) => setTimeout(resolve, ms));

const Subscriber: React.FC<{ onKey: (key: Key) => void }> = ({ onKey }) => {
  useKeypress(onKey);
  return null;
};

function renderProvider(received: Key[], children?: React.ReactNode) {
  const stdout = Object.assign(new PassThrough(), { columns: 120, rows: 30 });
  const inkStdin = new PassThrough();
  return render(
    <KeypressProvider>
      <Subscriber onKey={(key) => received.push(key)} />
      {children}
    </KeypressProvider>,
    { stdout, stdin: inkStdin, patchConsole: false, exitOnCtrlC: false, debug: true },
  );
}

beforeEach(() => {
  captureLoggerCalls();

  // Swap the real stdin for a controlled in-memory stream: the provider must
  // never read from, or switch raw mode on, the native terminal.
  fakeStdin = new ControlledStdin();
  Object.defineProperty(process, 'stdin', {
    value: fakeStdin,
    configurable: true,
    writable: true,
    enumerable: true,
  });

  // Keep the provider from writing terminal control sequences (bracketed
  // paste / Kitty protocol) to the real stdout.
  stdoutTTYDescriptor = Object.getOwnPropertyDescriptor(process.stdout, 'isTTY');
  Object.defineProperty(process.stdout, 'isTTY', { value: false, configurable: true });

  savedEnv = {
    TERM: process.env.TERM,
    TERM_PROGRAM: process.env.TERM_PROGRAM,
    KITTY_WINDOW_ID: process.env.KITTY_WINDOW_ID,
  };
  process.env.TERM = 'xterm-256color';
  delete process.env.TERM_PROGRAM;
  delete process.env.KITTY_WINDOW_ID;
});

afterEach(() => {
  Object.defineProperty(process, 'stdin', stdinDescriptor);
  if (stdoutTTYDescriptor) {
    Object.defineProperty(process.stdout, 'isTTY', stdoutTTYDescriptor);
  } else {
    delete (process.stdout as any).isTTY;
  }
  for (const [key, value] of Object.entries(savedEnv)) {
    if (value === undefined) {
      delete process.env[key];
    } else {
      process.env[key] = value;
    }
  }
  vi.restoreAllMocks();
});

describe('KeypressProvider credential logging', () => {
  it('delivers typed and bracketed-paste keys unchanged without logging their content', async () => {
    const received: Key[] = [];
    const app = renderProvider(received);
    try {
      await tick();

      // Real PTY-style delivery: one chunk per keystroke.
      for (const char of SECRET_TYPED) {
        fakeStdin.emit('data', char);
      }
      // Bracketed paste, exactly as a terminal delivers it.
      fakeStdin.emit('data', `\x1b[200~${SECRET_PASTED}\x1b[201~`);
      await tick();

      // 1. Key delivery is unchanged.
      const typed = received
        .filter((key) => key.insertable && key.name !== 'paste')
        .map((key) => key.sequence)
        .join('');
      expect(typed).toBe(SECRET_TYPED);
      const pasteKey = received.find((key) => key.name === 'paste');
      expect(pasteKey?.sequence).toBe(SECRET_PASTED);
      expect(pasteKey?.insertable).toBe(true);

      // 2. No content-bearing log field exists at all: the pre-fix schema
      //    logged `chunk`/`hexDump` for every stdin chunk (one per keystroke),
      //    `sequence`/`name` per broadcast and `cleanedPreview` per paste.
      const text = loggedText();
      expect(text).not.toMatch(/"(chunk|hexDump|cleanedPreview|sequence)"\s*:/);

      // 3. And no form of the secret (raw text or hex dump) is present.
      expect(text).not.toContain(SECRET_TYPED);
      expect(text).not.toContain(SECRET_PASTED);
      expect(hexDump(SECRET_PASTED)).toBeTruthy(); // sanity: helper is meaningful
      expect(text).not.toContain(hexDump(SECRET_TYPED));
      expect(text).not.toContain(hexDump(SECRET_PASTED));

      // 4. Non-content metadata is still logged (the fix is not "silence").
      const stdinChunkLogs = loggedContexts('process_stdin_data');
      expect(stdinChunkLogs.length).toBeGreaterThan(0);
      for (const context of stdinChunkLogs) {
        expect(typeof context.chunkLength).toBe('number');
        expect(context).not.toHaveProperty('chunk');
        expect(context).not.toHaveProperty('hexDump');
      }
      expect(
        stdinChunkLogs.some(
          (context) => context.chunkLength === `\x1b[200~${SECRET_PASTED}\x1b[201~`.length,
        ),
      ).toBe(true);

      const broadcasts = loggedContexts('broadcast');
      expect(broadcasts.length).toBeGreaterThan(0);
      const insertableBroadcasts = broadcasts.filter((context) => context.insertable === true);
      expect(insertableBroadcasts.length).toBeGreaterThanOrEqual(SECRET_TYPED.length);
      for (const context of insertableBroadcasts) {
        // A printable key must not be identifiable from its log entry.
        expect(context.keyName).toBeUndefined();
        expect(typeof context.sequenceLength).toBe('number');
      }

      const pasteLogs = loggerCalls.filter((call) =>
        String(call.args[0]).includes('bufferPaste done'),
      );
      expect(pasteLogs).toHaveLength(1);
      expect(pasteLogs[0].args[1].cleanedBufferLength).toBe(SECRET_PASTED.length);
      expect(pasteLogs[0].args[1]).not.toHaveProperty('cleanedPreview');
    } finally {
      app.unmount();
    }
  });

  it('delivers single-character shortcuts without recording their names', async () => {
    const received: Key[] = [];
    const app = renderProvider(received);
    try {
      await tick();
      fakeStdin.emit('data', '\x02');
      if (process.platform === 'darwin') fakeStdin.emit('data', '∫');
      await tick();
      expect(received.some((key) => key.name === 'b' && key.ctrl)).toBe(true);
      if (process.platform === 'darwin') {
        expect(received.some((key) => key.name === 'b' && key.alt && key.sequence === '∫')).toBe(true);
      }
      const shortcuts = loggedContexts('broadcast').filter((context) => context.ctrl || context.alt);
      expect(shortcuts.length).toBeGreaterThan(0);
      expect(shortcuts.every((context) => context.keyName === undefined)).toBe(true);
    } finally {
      app.unmount();
      app.cleanup();
    }
  });

  it('removes the process.stdin data listener it registered on unmount', async () => {
    const received: Key[] = [];
    const listenersBeforeMount = fakeStdin.listenerCount('data');

    const app = renderProvider(received);
    await tick();
    expect(fakeStdin.listenerCount('data')).toBe(listenersBeforeMount + 1);

    app.unmount();
    await tick();
    // The registered handler itself must be gone (not the unregistered
    // parser closure from createDataListener()).
    expect(fakeStdin.listenerCount('data')).toBe(listenersBeforeMount);

    // ...and no processing/logging may happen for data arriving afterwards.
    const logsAfterUnmount = loggerCalls.length;
    fakeStdin.emit('data', SECRET_PASTED);
    await tick();
    expect(received).toHaveLength(0);
    expect(loggerCalls.length).toBe(logsAfterUnmount);
  });
});

describe('prompt paste credential logging', () => {
  it.each([SECRET_PASTED, `${SECRET_PASTED}\n${'example line\n'.repeat(70)}end`])(
    'submits pasted text unchanged while logging only paste metadata (%#)',
    async (secret) => {
      vi.spyOn(slashCommandService, 'getCommands').mockResolvedValue([]);
      const onSubmit = vi.fn();
      const app = renderProvider([], (
        <AppProvider>
          <InputPromptWithWrapUseKPC onSubmit={onSubmit} width={100} />
        </AppProvider>
      ));
      try {
        await tick();
        fakeStdin.emit('data', `\x1b[200~${secret}\x1b[201~`);
        // Let the input commit and pass the terminal's fast-return threshold.
        await tick(80);
        const pasteLogs = loggerCalls.filter((call) =>
          call.args[0] === '[InputPromptWithWrapUseKPC] paste event',
        );
        expect(pasteLogs).toHaveLength(1);
        expect(pasteLogs[0].args[1]).toEqual({ textLength: secret.length, isEmpty: false });
        expect(loggedText()).not.toContain(SECRET_PASTED);
        expect(loggedText()).not.toMatch(/"(preview|cleanedPreview|sequence|chunk|hexDump)"\s*:/);
        fakeStdin.emit('data', '\r');
        await tick();
        expect(onSubmit).toHaveBeenCalledTimes(1);
        expect(onSubmit).toHaveBeenCalledWith(secret, undefined);
      } finally {
        app.unmount();
        app.cleanup();
      }
    },
  );
});

describe('adapter startup credential logging', () => {
  it('never logs --set-env credentials carried by siadaArgs', () => {
    const secret = 'sk-test-9f4c2a7e-not-a-real-key';
    const config: any = {
      workingDir: process.cwd(),
      model: 'siada-test-model',
      acpMode: true,
      siadaArgs: ['--set-env', `API_KEY=${secret}`, '--model', 'siada-test-model'],
    };

    const { command, args } = (new SiadaACPAdapter() as any).buildCommand(config);

    // The spawn contract is untouched: the credential is still passed through
    // to the child process, it just never reaches the log.
    expect(typeof command).toBe('string');
    expect(args).toContain('--set-env');
    expect(args).toContain(`API_KEY=${secret}`);

    const text = loggedText();
    expect(text).not.toContain(secret);
    expect(text).not.toContain('API_KEY=');
    expect(text).not.toMatch(/"siadaArgs"\s*:/);

    // Diagnosis value kept: the non-sensitive counts are still logged.
    const skipLog = loggerCalls.find((call) =>
      String(call.args[0]).includes('Skipping --model from config'),
    );
    expect(skipLog).toBeTruthy();
    expect(skipLog!.args[1].siadaArgsCount).toBe(config.siadaArgs.length);
    expect(skipLog!.args[1].configModel).toBe('siada-test-model');
  });
});