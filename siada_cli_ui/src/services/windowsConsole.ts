import { spawn, spawnSync, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { Readable } from 'node:stream';
import { StringDecoder } from 'node:string_decoder';
import { logger } from '../utils/logger.js';

/** An Ink-compatible tty stream; Win32 owns raw mode, not libuv. */
export class ConsoleInputStream extends Readable {
  readonly isTTY = true;
  isRaw = false;
  private buffer = '';
  private decoder = new StringDecoder('utf8');
  private receive = (chunk: Buffer | string) => {
    try {
      this.buffer += typeof chunk === 'string' ? chunk : this.decoder.write(chunk);
      let newline: number;
      while ((newline = this.buffer.indexOf('\n')) >= 0) {
        if (newline > 128 * 1024) throw new Error('Native input message exceeds its size limit');
        const line = this.buffer.slice(0, newline);
        this.buffer = this.buffer.slice(newline + 1);
        if (!line) continue;
        const message = JSON.parse(line);
        if (message.type === 'ready') this.emit('ready');
        else if (message.type === 'input' && typeof message.data === 'string') {
          if (message.data.length > 64 * 1024) throw new Error('Native input batch exceeds its size limit');
          if (!this.push(message.data)) this.source.pause();
        } else if (message.type === 'resize' && Number.isInteger(message.columns) &&
          Number.isInteger(message.rows) && message.columns > 0 && message.rows > 0) {
          this.emit('resize', { columns: message.columns, rows: message.rows });
        } else {
          throw new Error(message.type === 'error' ? String(message.error) : 'Invalid native input message');
        }
      }
      if (this.buffer.length > 128 * 1024) throw new Error('Native input message exceeds its size limit');
    } catch (error) {
      // JSON parser errors can quote a fragment of typed text.
      this.destroy(error instanceof SyntaxError ? new Error('Malformed native input message') :
        error instanceof Error ? error : new Error('Native input transport failed'));
    }
  };
  private endSource = () => {
    if (this.buffer.trim()) this.destroy(new Error('Native input message was truncated'));
    else this.push(null);
  };
  private sourceError = (error: Error) => this.destroy(error);

  constructor(private source: Readable) {
    super({ encoding: 'utf8' });
    source.on('data', this.receive).once('end', this.endSource).once('error', this.sourceError);
  }

  _read(): void { this.source.resume(); }
  _destroy(error: Error | null, callback: (error?: Error | null) => void): void {
    this.source.off('data', this.receive).off('end', this.endSource).off('error', this.sourceError);
    callback(error);
  }
  setRawMode(raw: boolean): this { this.isRaw = raw; return this; }
  ref(): this { return this; }
  unref(): this { return this; }
}

export class WindowsConsoleInput {
  readonly stream: ConsoleInputStream;
  private readonly name = `siada-input-${process.pid}-${randomUUID()}`;
  private child: ChildProcessWithoutNullStreams;
  private stopped = false;
  private suspended = false;
  private ready = false;
  private failure: Error | undefined;
  private readonly onExit = () => this.stop();

  private constructor(private python: string, private helper: string) {
    this.child = spawn(python, [
      '-I', helper, '--parent-pid', String(process.pid), '--name', this.name,
    ], {
      // libuv's Windows job kills ordinary children when Node is terminated.
      // Detach so the parent-process HANDLE can wake our restoration finally.
      detached: true, windowsHide: true, stdio: 'pipe',
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    this.child.stdin.end();
    // Diagnostic output must never enter the screen or contain keyboard text.
    this.child.stderr.resume();
    this.stream = new ConsoleInputStream(this.child.stdout);
    this.stream.on('error', error => { this.failure = error; });
    this.child.on('error', error => this.stream.destroy(error));
    this.child.on('exit', (code, signal) => {
      if (!this.stopped) {
        this.stream.destroy(new Error(`Native input reader exited (${code ?? signal})`));
      }
    });
    this.stream.on('resize', () => {
      // Requery libuv's tty handles so every layout consumer sees the change.
      const output = process.stdout as NodeJS.WriteStream & { _refreshSize?: () => void };
      output._refreshSize?.();
      output.emit('resize');
    });
    process.once('exit', this.onExit);
  }

  static async start(python: string, helper: string): Promise<WindowsConsoleInput> {
    const input = new WindowsConsoleInput(python, helper);
    try {
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(() => done(new Error('Native input startup timed out')), 5000);
        const onReady = () => { input.ready = true; done(); };
        const onError = (error: Error) => done(error);
        const done = (error?: Error) => {
          clearTimeout(timer);
          input.stream.off('ready', onReady).off('error', onError);
          if (error) reject(error);
          else resolve();
        };
        input.stream.once('ready', onReady).once('error', onError);
      });
      return input;
    } catch (error) {
      input.stop();
      throw error;
    }
  }

  private control(action: 'pause' | 'resume' | 'stop'): void {
    const result = spawnSync(this.python, [
      '-I', this.helper, '--name', this.name, '--control', action,
    ], { windowsHide: true, encoding: 'utf8', timeout: 2500, maxBuffer: 4096,
      stdio: ['ignore', 'pipe', 'pipe'] });
    if (result.error || result.status !== 0) {
      throw new Error(`Native input ${action} failed: ${result.error?.message || result.stdout.trim()}`);
    }
  }

  private transition(action: 'pause' | 'resume'): void {
    try { this.control(action); }
    catch (error) {
      // A timeout leaves ownership unknown: the request can already have
      // paused Win32. Fail closed and restore rather than retain a dead UI.
      const failure = error instanceof Error ? error : new Error('Native input suspension failed');
      this.failure = failure;
      this.stream.destroy(failure);
      this.stop();
      throw failure;
    }
  }

  suspend(): void {
    if (this.stopped || this.failure) throw this.failure ?? new Error('Native input is closed');
    if (this.suspended) return;
    this.transition('pause');
    this.suspended = true;
  }

  resume(): void {
    if (this.stopped || this.failure) throw this.failure ?? new Error('Native input is closed');
    if (!this.suspended) return;
    this.transition('resume');
    this.suspended = false;
  }

  stop(): void {
    if (this.stopped) return;
    this.stopped = true;
    process.off('exit', this.onExit);
    if (this.ready && this.child.exitCode === null && this.child.signalCode === null) {
      try { this.control('stop'); }
      catch (error) {
        logger.error('Native input state restoration failed', { error: String(error) });
        // Let the parent-process handle wake the helper on exit. Killing it
        // here would skip the finally block which restores console input.
      }
    } else if (!this.ready && this.child.pid) {
      // The events may exist even if stdout's ready message was not delivered.
      try { this.control('stop'); } catch { /* Parent exit also restores state. */ }
    }
    this.stream.destroy();
  }
}

let nativeInput: WindowsConsoleInput | undefined;

export function getNativeWindowsInput(): WindowsConsoleInput | undefined {
  return nativeInput;
}

export function getTerminalInput(): NodeJS.ReadStream {
  return nativeInput ? nativeInput.stream as unknown as NodeJS.ReadStream : process.stdin;
}

export async function initializeWindowsInput(
  pythonPath: string | undefined, helperPath: string, nativeConsole = false,
): Promise<void> {
  if (process.platform !== 'win32' || !nativeConsole || !process.stdin.isTTY ||
    !process.stdout.isTTY || process.env.WT_SESSION || process.env.TERM_PROGRAM) return;
  if (!pythonPath) throw new Error('Native console input requires a Python interpreter');
  // Never leave libuv polling the native console while ReadConsoleInput owns it.
  process.stdin.pause();
  nativeInput = await WindowsConsoleInput.start(pythonPath, helperPath);
  nativeInput.stream.on('error', error => {
    logger.error('Native Windows input failed', { error: error.message });
    process.exit(1);
  });
  logger.info('Native Windows console input enabled');
}