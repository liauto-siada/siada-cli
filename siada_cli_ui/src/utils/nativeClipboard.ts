import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import pngCodec from '../../native-clipboard/png.cjs';

const MAX_BYTES = 30 * 1024 * 1024;
const TIMEOUT_MS = 3000;
const unavailable = () => new Error('Native clipboard unavailable');
export interface NativeClipboardImage {
  data: Buffer;
  width: number;
  height: number;
}
type NativeOperation = 'read' | 'write' | 'image';
type NativeValue = string | NativeClipboardImage | null;

function helperPath(): string {
  for (const relative of ['./native-clipboard/helper.cjs', '../../native-clipboard/helper.cjs']) {
    const candidate = fileURLToPath(new URL(relative, import.meta.url));
    if (existsSync(candidate)) return candidate;
  }
  throw unavailable();
}

/** One owned helper keeps Linux clipboard writes alive between operations. */
export class NativeClipboardClient {
  private child?: ChildProcessWithoutNullStreams;
  private nextId = 0;
  private queue: Promise<unknown> = Promise.resolve();
  private pending?: {
    id: number;
    operation: NativeOperation;
    resolve: (value: NativeValue) => void;
    reject: (error: Error) => void;
  };
  private response = '';
  private onExit = () => this.dispose();

  constructor(private entrypoint?: string, private timeoutMs = TIMEOUT_MS) {}

  private start(): ChildProcessWithoutNullStreams {
    if (this.child) return this.child;
    // A long-lived clipboard helper needs desktop variables, not model keys
    // or a caller-supplied native-library override.
    const env: NodeJS.ProcessEnv = {};
    for (const name of [
      'PATH', 'SystemRoot', 'SYSTEMROOT', 'WINDIR', 'HOME', 'USERPROFILE',
      'TMPDIR', 'TEMP', 'TMP', 'DISPLAY', 'XAUTHORITY', 'WAYLAND_DISPLAY',
      'XDG_RUNTIME_DIR', 'LANG', 'LC_ALL', 'LC_CTYPE',
      'SSH_TTY', 'SSH_CONNECTION', 'SSH_CLIENT', 'WSL_DISTRO_NAME', 'WSL_INTEROP',
    ]) {
      if (process.env[name] !== undefined) env[name] = process.env[name];
    }
    const child = spawn(process.execPath, [this.entrypoint ?? helperPath()], {
      stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true, env,
    });
    this.child = child;
    process.once('exit', this.onExit);
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => {
      if (this.child !== child) return;
      this.response += chunk;
      if (Buffer.byteLength(this.response) > MAX_BYTES) return this.dispose();
      const newline = this.response.indexOf('\n');
      if (newline < 0) return;
      try {
        const result = JSON.parse(this.response.slice(0, newline));
        this.response = this.response.slice(newline + 1);
        if (!this.pending || result.id !== this.pending.id) {
          throw unavailable();
        }
        if (result.ok === false && this.pending.operation === 'image') {
          // An unavailable image backend must not kill the arboard process that
          // may still own the user's last successful Linux text copy.
          this.pending.reject(unavailable());
          return;
        }
        if (result.ok !== true) throw unavailable();
        if (this.pending.operation === 'image') {
          if (result.image === null) {
            this.pending.resolve(null);
          } else {
            const image: NativeClipboardImage = pngCodec.decodePng(result.image?.png);
            if (image.width !== result.image.width || image.height !== result.image.height) {
              throw unavailable();
            }
            this.pending.resolve(image);
          }
          return;
        }
        if (result.text !== undefined && typeof result.text !== 'string') throw unavailable();
        this.pending.resolve(result.text ?? '');
      } catch {
        this.dispose();
      }
    });
    child.stdin.on('error', () => { if (this.child === child) this.dispose(); });
    child.on('error', () => { if (this.child === child) this.dispose(); });
    child.on('exit', () => { if (this.child === child) this.dispose(); });
    // Native stderr must not block the helper or enter the TUI's output.
    child.stderr.resume();
    child.unref();
    for (const stream of [child.stdin, child.stdout, child.stderr]) {
      (stream as typeof stream & { unref?: () => void }).unref?.();
    }
    return child;
  }

  private request(operation: NativeOperation, text?: string, signal?: AbortSignal): Promise<NativeValue> {
    signal?.throwIfAborted();
    const run = () => new Promise<NativeValue>((resolve, reject) => {
      if (signal?.aborted) { reject(unavailable()); return; }
      let timer: ReturnType<typeof setTimeout> | undefined;
      const abort = () => this.dispose();
      const finish = (error?: Error, value: NativeValue = '') => {
        if (timer) clearTimeout(timer);
        signal?.removeEventListener('abort', abort);
        this.pending = undefined;
        error ? reject(error) : resolve(value);
      };
      try {
        const child = this.start();
        const id = ++this.nextId;
        this.pending = { id, operation, resolve: value => finish(undefined, value), reject: error => finish(error) };
        timer = setTimeout(abort, operation === 'image' ? this.timeoutMs * 3 : this.timeoutMs);
        signal?.addEventListener('abort', abort, { once: true });
        child.stdin.write(JSON.stringify({ id, operation, text }) + '\n');
      } catch {
        finish(unavailable());
        this.dispose();
      }
    });
    const result = this.queue.then(run, run);
    this.queue = result.catch(() => {});
    return result;
  }

  async readText(): Promise<string> {
    return await this.request('read') as string;
  }

  async readImage(signal?: AbortSignal): Promise<NativeClipboardImage | null> {
    return await this.request('image', undefined, signal) as NativeClipboardImage | null;
  }

  async writeText(text: string, signal?: AbortSignal): Promise<void> {
    if (Buffer.byteLength(text) > 100000) throw unavailable();
    await this.request('write', text, signal);
  }

  dispose(): void {
    const child = this.child;
    this.child = undefined;
    this.response = '';
    process.removeListener('exit', this.onExit);
    this.pending?.reject(unavailable());
    child?.kill('SIGKILL');
    child?.stdin.destroy();
    child?.stdout.destroy();
    child?.stderr.destroy();
  }
}

export const nativeClipboard = new NativeClipboardClient();