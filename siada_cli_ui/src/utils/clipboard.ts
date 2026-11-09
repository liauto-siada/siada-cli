/**
 * Clipboard utilities for reading image/file content from the OS clipboard.
 *
 * Text uses the bundled arboard backend, with platform tools as fallbacks.
 * Native calls run in an owned subprocess with a timeout.
 */

import { execFile } from 'child_process';
import * as os from 'os';
import * as path from 'path';
import * as fs from 'fs';
import { logger } from './logger.js';
import { nativeClipboard } from './nativeClipboard.js';
import { CLIPBOARD_TIPS } from '../constants/tips.js';

const CLIPBOARD_TIMEOUT_MS = 3000;
const TERMINAL_COPY_MAX_BYTES = 100_000;

export function isSshSession(): boolean {
  return !!(process.env.SSH_TTY || process.env.SSH_CONNECTION || process.env.SSH_CLIENT);
}

/** Terminal-owned paste must not trigger a second read of the host clipboard. */
export function canPasteOnRightClick(): boolean {
  return !isSshSession() && process.env.TERM_PROGRAM?.toLowerCase() !== 'vscode' &&
    ['darwin', 'linux', 'win32'].includes(process.platform);
}

export function isWslSession(): boolean {
  return process.platform === 'linux' && (
    !!(process.env.WSL_DISTRO_NAME || process.env.WSL_INTEROP) ||
    /microsoft/i.test(os.release())
  );
}

/** Wrap execFile in a promise with a timeout. Captures both stdout and stderr. */
function execWithTimeout(
  cmd: string,
  args: string[],
  timeoutMs = CLIPBOARD_TIMEOUT_MS,
  input?: string,
  signal?: AbortSignal,
): Promise<{ stdout: Buffer; stderr: string }> {
  return new Promise((resolve, reject) => {
    const proc = execFile(
      cmd, args,
      { encoding: 'buffer', timeout: timeoutMs, maxBuffer: 30 * 1024 * 1024, signal }, // 30 MB
      (err, stdout, stderr) => {
        if (err) reject(err);
        else resolve({
          stdout: stdout as unknown as Buffer,
          stderr: (stderr as unknown as Buffer | string)?.toString('utf8') ?? '',
        });
      },
    );
    // Clipboard writers wait for EOF. Failed delivery must not report success.
    proc.stdin?.on('error', error => {
      reject(error);
      proc.kill();
    });
    proc.stdin?.end(input);
  });
}

/** Check if a Buffer looks like a PNG (first 8 bytes = PNG magic). */
function isPng(buf: Buffer): boolean {
  return (
    buf.length > 8 &&
    buf[0] === 0x89 &&
    buf[1] === 0x50 &&
    buf[2] === 0x4e &&
    buf[3] === 0x47
  );
}

/** Check if a Buffer looks like a JPEG (starts with FF D8 FF). */
function isJpeg(buf: Buffer): boolean {
  return buf.length > 3 && buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff;
}

export interface ClipboardImage {
  /** Absolute path to the saved temp file. Caller should delete it after use. */
  filePath: string;
  mediaType: 'image/png' | 'image/jpeg' | 'image/gif' | 'image/webp';
  /** Available for native PNG reads. */
  width?: number;
  height?: number;
}

/**
 * Save raw image bytes to a temp file and return the path + mediaType.
 * Returns null if the buffer doesn't look like a supported image.
 */
function saveTempImage(data: Buffer): ClipboardImage | null {
  let ext: string;
  let mediaType: ClipboardImage['mediaType'];

  if (isPng(data)) {
    ext = '.png';
    mediaType = 'image/png';
  } else if (isJpeg(data)) {
    ext = '.jpg';
    mediaType = 'image/jpeg';
  } else if (data.length > 3 && data[0] === 0x47 && data[1] === 0x49 && data[2] === 0x46) {
    ext = '.gif';
    mediaType = 'image/gif';
  } else if (
    data.length > 12 &&
    data[0] === 0x52 &&
    data[1] === 0x49 &&
    data[2] === 0x46 &&
    data[3] === 0x46
  ) {
    ext = '.webp';
    mediaType = 'image/webp';
  } else {
    return null; // Not a recognised image format
  }

  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'siada-paste-'));
  const filePath = path.join(directory, `clipboard${ext}`);
  fs.writeFileSync(filePath, data);
  return { filePath, mediaType };
}

// ─────────────────────────────────────────────
// macOS
// ─────────────────────────────────────────────

// Python3 + AppKit: works in subprocess context; osascript ObjC-bridge does not.
const MACOS_PYTHON_IMAGE = `
import sys, base64
try:
    from AppKit import NSPasteboard
    pb = NSPasteboard.generalPasteboard()
    for t in ('public.png', 'public.tiff', 'public.jpeg'):
        d = pb.dataForType_(t)
        if d:
            sys.stdout.buffer.write(base64.b64encode(bytes(d)))
            sys.exit(0)
except Exception as e:
    sys.stderr.write(str(e))
sys.exit(0)
`;

/**
 * Resolve which python interpreter to use for AppKit access on macOS.
 *
 * Order of preference:
 *   1. SIADA_PYTHON_PATH — set by the launcher to the project's conda/venv
 *      python (which has PyObjC/AppKit installed as a transitive dep).
 *   2. plain `python3` from PATH — last resort; will fail if AppKit is
 *      not installed (Homebrew/asdf python3 typically lack it; even
 *      modern macOS no longer ships PyObjC with /usr/bin/python3).
 */
function resolveMacosPython(): string {
  const fromEnv = process.env.SIADA_PYTHON_PATH;
  if (fromEnv && fromEnv.trim()) {
    return fromEnv.trim();
  }
  return 'python3';
}

async function getImageFromClipboardMacos(): Promise<ClipboardImage | null> {
  const pythonBin = resolveMacosPython();
  logger.info('[clipboard] getImageFromClipboardMacos: running python+AppKit', {
    pythonBin,
    fromEnv: !!process.env.SIADA_PYTHON_PATH,
  });
  try {
    const { stdout, stderr } = await execWithTimeout(pythonBin, ['-c', MACOS_PYTHON_IMAGE]);
    const b64 = stdout.toString('utf8').trim();
    logger.info('[clipboard] python result', {
      b64Length: b64.length,
      hasData: !!b64,
      stderr: stderr ? stderr.slice(0, 500) : '',
    });
    if (!b64) {
      // Surface PyObjC import failures so users can diagnose why image paste
      // is silently doing nothing on macOS.
      if (stderr && /No module named ['"]?AppKit['"]?/i.test(stderr)) {
        logger.warn(
          '[clipboard] AppKit/PyObjC missing on this Python interpreter — ' +
          'image paste cannot work. Set SIADA_PYTHON_PATH to a Python that ' +
          'has pyobjc-framework-Cocoa installed (the siada-agenthub conda ' +
          'env normally does).',
          { pythonBin },
        );
      }
      return null;
    }
    const data = Buffer.from(b64, 'base64');
    const result = saveTempImage(data);
    logger.info('[clipboard] saveTempImage result', { result });
    return result;
  } catch (err) {
    logger.warn('[clipboard] python clipboard read failed', {
      err: String(err),
      pythonBin,
    });
    return null;
  }
}

// ─────────────────────────────────────────────
// Linux (xclip / wl-paste)
// ─────────────────────────────────────────────

async function getImageFromClipboardLinux(): Promise<ClipboardImage | null> {
  // Try wl-paste (Wayland) first, then xclip (X11)
  const cmds: [string, string[]][] = [
    ['wl-paste', ['--type', 'image/png', '--no-newline']],
    ['xclip', ['-selection', 'clipboard', '-t', 'image/png', '-o']],
  ];
  for (const [cmd, args] of cmds) {
    try {
      const { stdout } = await execWithTimeout(cmd, args);
      if (stdout.length > 0) {
        const result = saveTempImage(stdout);
        if (result) return result;
      }
    } catch {
      continue;
    }
  }
  return null;
}

// ─────────────────────────────────────────────
// Windows
// ─────────────────────────────────────────────

async function getImageFromClipboardWindows(): Promise<ClipboardImage | null> {
  // Base64 avoids Windows/WSL path translation and quoting temporary paths.
  const psScript = `
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$img = [Windows.Forms.Clipboard]::GetImage()
if ($null -ne $img) {
  try {
    $stream = New-Object System.IO.MemoryStream
    $img.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
    [Console]::Out.Write([Convert]::ToBase64String($stream.ToArray()))
  } finally {
    if ($null -ne $stream) { $stream.Dispose() }
    $img.Dispose()
  }
}
`;
  try {
    const { stdout } = await execWithTimeout(
      isWslSession() ? 'powershell.exe' : 'powershell',
      ['-NoProfile', '-NonInteractive', '-STA', '-Command', psScript],
    );
    return saveTempImage(Buffer.from(stdout.toString('utf8').trim(), 'base64'));
  } catch {
    // ignore
  }
  return null;
}

// ─────────────────────────────────────────────
// Public API
// ─────────────────────────────────────────────

/**
 * Try to read an image from the OS clipboard.
 * Returns null if no image is available or on error.
 */
export async function getImageFromClipboard(): Promise<ClipboardImage | null> {
  try {
    return await readClipboardImage();
  } catch {
    return null;
  }
}

async function readClipboardImage(): Promise<ClipboardImage | null> {
  logger.info('[clipboard] getImageFromClipboard called', { platform: process.platform });
  if (isSshSession()) return null;
  if (isWslSession()) return getImageFromClipboardWindows();
  let nativeFailed = false;
  try {
    const image = await nativeClipboard.readImage();
    if (image) {
      const saved = saveTempImage(image.data);
      if (saved) return { ...saved, width: image.width, height: image.height };
    }
  } catch (error) {
    nativeFailed = true;
    logger.debug('[clipboard] native image unavailable, trying platform fallback', { err: String(error) });
  }
  let image: ClipboardImage | null = null;
  switch (process.platform) {
    case 'darwin':
      image = await getImageFromClipboardMacos();
      break;
    case 'linux':
      image = await getImageFromClipboardLinux();
      break;
    case 'win32':
      image = await getImageFromClipboardWindows();
      break;
    default:
      logger.warn('[clipboard] unsupported platform', { platform: process.platform });
      return null;
  }
  if (!image && nativeFailed) throw new Error(CLIPBOARD_TIPS.imageFailed);
  return image;
}

/**
 * Read plain text from the OS clipboard.
 * Throws a user-facing error when the host clipboard cannot be read.
 */
export async function readClipboardText(): Promise<string> {
  if (isSshSession()) {
    throw new Error(`${CLIPBOARD_TIPS.sshUnavailable}${CLIPBOARD_TIPS.terminalPasteHint}`);
  }
  try {
    let stdout: Buffer;
    if (process.platform === 'win32' || isWslSession()) {
      const readWindows = async () => (await execWithTimeout(
        isWslSession() ? 'powershell.exe' : 'powershell',
        ['-NoProfile', '-NonInteractive', '-STA', '-Command',
          "$ErrorActionPreference = 'Stop'; [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); [Console]::Out.Write((Get-Clipboard -Raw))"],
      )).stdout;
      if (isWslSession()) stdout = await readWindows();
      else {
        try { stdout = Buffer.from(await nativeClipboard.readText(), 'utf8'); }
        catch { stdout = await readWindows(); }
      }
    } else if (process.platform === 'darwin') {
      try {
        stdout = Buffer.from(await nativeClipboard.readText(), 'utf8');
      } catch {
        stdout = (await execWithTimeout('pbpaste', [])).stdout;
      }
    } else if (process.platform === 'linux') {
      try {
        stdout = Buffer.from(await nativeClipboard.readText(), 'utf8');
      } catch {
        try {
          stdout = (await execWithTimeout('wl-paste', ['--no-newline'])).stdout;
        } catch {
          stdout = (await execWithTimeout('xclip', ['-selection', 'clipboard', '-o'])).stdout;
        }
      }
    } else {
      throw new Error('unsupported platform');
    }
    const text = stdout.toString('utf8');
    logger.info('[clipboard] getTextFromClipboard result', { length: text.length });
    return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  } catch (err) {
    logger.warn('[clipboard] getTextFromClipboard failed', { err: String(err) });
    const backend = isWslSession() || process.platform === 'win32'
      ? CLIPBOARD_TIPS.windows
      : process.platform === 'linux' ? CLIPBOARD_TIPS.linux : CLIPBOARD_TIPS.system;
    throw new Error(`${CLIPBOARD_TIPS.readFailed(backend)}${CLIPBOARD_TIPS.terminalPasteHint}`);
  }
}

/** Compatibility API for callers that only need nullable text. */
export async function getTextFromClipboard(): Promise<string | null> {
  try {
    return (await readClipboardText()) || null;
  } catch {
    return null;
  }
}

export type ClipboardContent =
  | { kind: 'text'; text: string }
  | { kind: 'image'; image: ClipboardImage };

// Session-local mirror of the most recent text delivered to the local terminal
// clipboard (OSC 52 / tmux). Remote sessions cannot read the host clipboard, so
// Ctrl+V falls back to what Siada itself copied last.
let lastTerminalCopy: string | null = null;

function rememberTerminalCopy(text: string): void {
  if (text) lastTerminalCopy = text;
}

/** Latest text this session sent to the terminal clipboard (OSC 52 / tmux). */
export function getLastTerminalCopy(): string | null {
  return lastTerminalCopy;
}

/** Clear the remembered terminal copy; exposed for tests. */
export function resetTerminalCopyCache(): void {
  lastTerminalCopy = null;
}

export async function readClipboardContent(includeImages: boolean): Promise<ClipboardContent> {
  if (isSshSession()) {
    // The remote host cannot read the user's local clipboard. Fall back to the
    // most recent text this session copied through the terminal, so "copy in
    // Siada, then Ctrl+V" keeps working over SSH.
    const remembered = getLastTerminalCopy();
    if (remembered !== null) return { kind: 'text', text: remembered };
    throw new Error(`${CLIPBOARD_TIPS.sshUnavailable}${CLIPBOARD_TIPS.terminalPasteHint}`);
  }
  let imageFailed = false;
  if (includeImages) {
    try {
      const image = await readClipboardImage();
      if (image) return { kind: 'image', image };
    } catch {
      imageFailed = true;
    }
  }
  const text = await readClipboardText();
  if (!text && imageFailed) throw new Error(CLIPBOARD_TIPS.imageFailed);
  if (!text) throw new Error(CLIPBOARD_TIPS.empty);
  return { kind: 'text', text };
}

/** Discard an image read whose input owner changed before completion. */
export function discardClipboardContent(content: ClipboardContent): void {
  if (content.kind !== 'image') return;
  void fs.promises.unlink(content.image.filePath)
    .then(() => fs.promises.rmdir(path.dirname(content.image.filePath)))
    .catch(() => {});
}

export type ClipboardCopyResult =
  | { status: 'copied' | 'requested'; message: string }
  | { status: 'failed'; message: string };

export function terminalCopySequence(text: string, tmux: boolean): string {
  if (Buffer.byteLength(text, 'utf8') > TERMINAL_COPY_MAX_BYTES) {
    throw new Error(CLIPBOARD_TIPS.copyTooLarge);
  }
  const encoded = Buffer.from(text, 'utf8').toString('base64');
  return tmux
    ? `\x1bPtmux;\x1b\x1b]52;c;${encoded}\x07\x1b\\`
    : `\x1b]52;c;${encoded}\x07`;
}

async function copyThroughTerminal(text: string): Promise<void> {
  const tmux = !!(process.env.TMUX || process.env.TMUX_PANE);
  const sequence = terminalCopySequence(text, tmux);
  if (tmux && process.env.TMUX_PANE) {
    try {
      const { stdout: setting } = await execWithTimeout('tmux', ['show-options', '-gv', 'set-clipboard']);
      if (setting.toString('utf8').trim() === 'off') throw new Error('tmux clipboard forwarding disabled');
      const { stdout: session } = await execWithTimeout(
        'tmux', ['display-message', '-p', '-t', process.env.TMUX_PANE, '#{session_id}'],
      );
      const sessionId = session.toString('utf8').trim();
      if (!sessionId) throw new Error('no current tmux session');
      const { stdout: clients } = await execWithTimeout(
        'tmux', ['list-clients', '-t', sessionId, '-F', '#{client_activity} #{client_name}'],
      );
      const client = clients.toString('utf8').split('\n')
        .map(line => /^(\d+) (.+)$/.exec(line))
        .filter((match): match is RegExpExecArray => !!match)
        .sort((a, b) => Number(b[1]) - Number(a[1]))[0]?.[2];
      if (!client) throw new Error('no attached tmux client');
      await execWithTimeout('tmux', ['load-buffer', '-w', '-t', client, '-'], CLIPBOARD_TIMEOUT_MS, text);
      rememberTerminalCopy(text);
      return;
    } catch (err) {
      logger.debug('[clipboard] tmux copy failed, trying OSC 52', { err: String(err) });
    }
  }
  if (!process.stdout.isTTY) throw new Error(CLIPBOARD_TIPS.notInteractive);
  await new Promise<void>((resolve, reject) => {
    process.stdout.write(sequence, error => error ? reject(error) : resolve());
  });
  rememberTerminalCopy(text);
}

async function copyNatively(text: string, signal?: AbortSignal): Promise<void> {
  signal?.throwIfAborted();
  if (isSshSession()) throw new Error('Host clipboard unavailable over SSH');
  if (!isWslSession()) {
    try {
      await nativeClipboard.writeText(text, signal);
      signal?.throwIfAborted();
      return;
    } catch {
      signal?.throwIfAborted();
    }
  }
  if (process.platform === 'win32' || isWslSession()) {
    await execWithTimeout(
      isWslSession() ? 'powershell.exe' : 'powershell',
      ['-NoProfile', '-NonInteractive', '-STA', '-Command',
        "$ErrorActionPreference = 'Stop'; [Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false); Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
      CLIPBOARD_TIMEOUT_MS, text, signal,
    );
  } else if (process.platform === 'darwin') {
    await execWithTimeout('/usr/bin/pbcopy', [], CLIPBOARD_TIMEOUT_MS, text, signal);
  } else if (process.platform === 'linux') {
    try {
      await execWithTimeout('wl-copy', [], CLIPBOARD_TIMEOUT_MS, text, signal);
    } catch {
      signal?.throwIfAborted();
      await execWithTimeout('xclip', ['-selection', 'clipboard'], CLIPBOARD_TIMEOUT_MS, text, signal);
    }
  } else {
    throw new Error('unsupported platform');
  }
}

export async function copyClipboardText(text: string): Promise<ClipboardCopyResult> {
  if (!text) return { status: 'failed', message: CLIPBOARD_TIPS.noText };
  const terminalRequired = isSshSession() || !!(process.env.TMUX || process.env.TMUX_PANE);
  if (terminalRequired) {
    try {
      await copyThroughTerminal(text);
      return { status: 'requested', message: CLIPBOARD_TIPS.requested };
    } catch (err) {
      logger.warn('[clipboard] terminal copy failed', { err: String(err) });
      return { status: 'failed', message: CLIPBOARD_TIPS.terminalCopyFailed };
    }
  }
  try {
    await copyNatively(text);
    return { status: 'copied', message: CLIPBOARD_TIPS.copied };
  } catch (err) {
    logger.warn('[clipboard] native copy failed, trying OSC 52', { err: String(err) });
    try {
      await copyThroughTerminal(text);
      return { status: 'requested', message: CLIPBOARD_TIPS.requested };
    } catch {
      return { status: 'failed', message: CLIPBOARD_TIPS.copyFailed };
    }
  }
}

/**
 * Write plain text to the OS clipboard.
 * Returns true only for confirmed native writes; terminal delivery has no acknowledgement.
 */
export async function copyTextToClipboard(text: string, signal?: AbortSignal): Promise<boolean> {
  if (signal?.aborted || Buffer.byteLength(text, 'utf8') > 100000) return false;
  try {
    // Selection callers own terminal delivery; keep this API native-only.
    await copyNatively(text, signal);
    return !signal?.aborted;
  } catch (err) {
    logger.warn('[clipboard] copyTextToClipboard failed', { err: String(err) });
    return false;
  }
}

export type SelectionCopyResult = 'native' | 'osc52' | 'failed';

/** Send only user-selected text; remote sessions use the terminal clipboard protocol. */
export async function copySelectionToClipboard(
  text: string, output: Pick<NodeJS.WriteStream, 'write' | 'isTTY'> | undefined, signal?: AbortSignal,
): Promise<SelectionCopyResult> {
  if (signal?.aborted || !text.trim() || Buffer.byteLength(text, 'utf8') > 100000) return 'failed';
  const remote = isSshSession();
  if (!remote && await copyTextToClipboard(text, signal)) return 'native';
  if (signal?.aborted || !output?.isTTY || process.env.TERM === 'dumb') return 'failed';
  // SSH often omits terminal identity; let the terminal decide whether to accept OSC 52.
  try {
    output.write(selectionClipboardSequence(text, process.env));
    rememberTerminalCopy(text);
    return 'osc52';
  } catch {
    return 'failed';
  }
}

export function selectionClipboardSequence(text: string, environment: NodeJS.ProcessEnv): string {
  const encoded = Buffer.from(text, 'utf8').toString('base64');
  const raw = `\x1b]52;c;${encoded}\x07`;
  if (environment.TMUX) return raw + `\x1bPtmux;${raw.replaceAll('\x1b', '\x1b\x1b')}\x1b\\`;
  if (environment.STY) return `\x1bP\x1b]52;c;${(encoded.match(/.{1,76}/g) || ['']).join('\x1b\\\x1bP')}\x07\x1b\\`;
  return environment.TERM_PROGRAM === 'kitty' ? raw.slice(0, -1) + '\x1b\\' : raw;
}

/**
 * Return true if `text` is an absolute path to an existing file/directory.
 * Used to detect "drag a file from Finder/Explorer" style pastes.
 */
export function isFilePath(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed.startsWith('/') && !trimmed.startsWith('~')) return false;
  const expanded = trimmed.startsWith('~')
    ? path.join(os.homedir(), trimmed.slice(1))
    : trimmed;
  try {
    return fs.existsSync(expanded);
  } catch {
    return false;
  }
}
