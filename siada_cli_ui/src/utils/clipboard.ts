/**
 * Clipboard utilities for reading image/file content from the OS clipboard.
 *
 * Supports macOS (osascript / pbpaste), Linux (xclip / wl-paste), Windows (powershell).
 * All operations are fire-and-forget with a timeout so a missing tool never blocks the UI.
 */

import { execFile } from 'child_process';
import * as os from 'os';
import * as path from 'path';
import * as fs from 'fs';
import { logger } from './logger.js';

const CLIPBOARD_TIMEOUT_MS = 3000;

/** Wrap execFile in a promise with a timeout. Captures both stdout and stderr. */
function execWithTimeout(
  cmd: string,
  args: string[],
  timeoutMs = CLIPBOARD_TIMEOUT_MS,
): Promise<{ stdout: Buffer; stderr: string }> {
  return new Promise((resolve, reject) => {
    const proc = execFile(
      cmd, args,
      { encoding: 'buffer', timeout: timeoutMs, maxBuffer: 30 * 1024 * 1024 }, // 30 MB
      (err, stdout, stderr) => {
        if (err) reject(err);
        else resolve({
          stdout: stdout as unknown as Buffer,
          stderr: (stderr as unknown as Buffer | string)?.toString('utf8') ?? '',
        });
      },
    );
    void proc;
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

  const filePath = path.join(os.tmpdir(), `siada-paste-${Date.now()}${ext}`);
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
  const tmpPath = path.join(os.tmpdir(), `siada-paste-${Date.now()}.png`);
  const psScript = `
Add-Type -AssemblyName System.Windows.Forms
$img = [Windows.Forms.Clipboard]::GetImage()
if ($null -ne $img) {
  $img.Save('${tmpPath.replace(/\\/g, '\\\\')}')
  Write-Output 'ok'
}
`;
  try {
    const { stdout } = await execWithTimeout('powershell', ['-Command', psScript]);
    if (stdout.toString().trim() === 'ok' && fs.existsSync(tmpPath)) {
      return { filePath: tmpPath, mediaType: 'image/png' };
    }
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
  logger.info('[clipboard] getImageFromClipboard called', { platform: process.platform });
  switch (process.platform) {
    case 'darwin':
      return getImageFromClipboardMacos();
    case 'linux':
      return getImageFromClipboardLinux();
    case 'win32':
      return getImageFromClipboardWindows();
    default:
      logger.warn('[clipboard] unsupported platform', { platform: process.platform });
      return null;
  }
}

/**
 * Read plain text from the OS clipboard.
 * Returns null if clipboard has no text or on error.
 */
export async function getTextFromClipboard(): Promise<string | null> {
  try {
    let stdout: Buffer;
    if (process.platform === 'darwin') {
      stdout = (await execWithTimeout('pbpaste', [])).stdout;
    } else if (process.platform === 'linux') {
      try {
        stdout = (await execWithTimeout('wl-paste', ['--no-newline'])).stdout;
      } catch {
        stdout = (await execWithTimeout('xclip', ['-selection', 'clipboard', '-o'])).stdout;
      }
    } else {
      return null;
    }
    const text = stdout.toString('utf8');
    logger.info('[clipboard] getTextFromClipboard result', { length: text.length });
    return text.length > 0 ? text : null;
  } catch (err) {
    logger.warn('[clipboard] getTextFromClipboard failed', { err: String(err) });
    return null;
  }
}

/**
 * Write plain text to the OS clipboard.
 * Returns true on success, false on error or unsupported platform.
 */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (process.platform === 'darwin') {
      await new Promise<void>((resolve, reject) => {
        const { spawn } = require('child_process');
        const proc = spawn('pbcopy', [], { stdio: ['pipe', 'ignore', 'ignore'] });
        proc.on('error', reject);
        proc.on('close', (code: number) => (code === 0 ? resolve() : reject(new Error(`pbcopy exit ${code}`))));
        proc.stdin.end(text, 'utf8');
      });
      return true;
    } else if (process.platform === 'linux') {
      for (const [cmd, args] of [['wl-copy', []], ['xclip', ['-selection', 'clipboard']]] as [string, string[]][]) {
        try {
          await new Promise<void>((resolve, reject) => {
            const { spawn } = require('child_process');
            const proc = spawn(cmd, args, { stdio: ['pipe', 'ignore', 'ignore'] });
            proc.on('error', reject);
            proc.on('close', (code: number) => (code === 0 ? resolve() : reject(new Error(`${cmd} exit ${code}`))));
            proc.stdin.end(text, 'utf8');
          });
          return true;
        } catch {
          continue;
        }
      }
      return false;
    } else if (process.platform === 'win32') {
      await new Promise<void>((resolve, reject) => {
        const { spawn } = require('child_process');
        const proc = spawn('clip', [], { stdio: ['pipe', 'ignore', 'ignore'] });
        proc.on('error', reject);
        proc.on('close', (code: number) => (code === 0 ? resolve() : reject(new Error(`clip exit ${code}`))));
        proc.stdin.end(text, 'utf8');
      });
      return true;
    }
    return false;
  } catch (err) {
    logger.warn('[clipboard] copyTextToClipboard failed', { err: String(err) });
    return false;
  }
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
