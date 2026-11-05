import { spawnSync } from 'node:child_process';
import stripAnsi from 'strip-ansi';
import stringWidth from 'string-width';
import { setStringWidthFunction } from '@jrichman/ink';
import { logger } from './logger.js';

const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
let nativeConsole = false;
let widths = new Map<string, number>();

/** Keep application width decisions and Ink's terminal cells in agreement. */
export function displayWidth(text: string): number {
  let width = stringWidth(text);
  if (widths.size === 0 || !/[^\x00-\x7f]/.test(text)) return width;
  for (const { segment } of segmenter.segment(stripAnsi(text))) {
    // Preserve Unicode's combined emoji width instead of counting its scalars.
    if (/[\u200d\ufe0f]/u.test(segment)) continue;
    for (const character of segment) {
      const actual = widths.get(character);
      if (actual !== undefined) width += actual - stringWidth(character);
    }
  }
  return width;
}

export function clipToColumns(text: string, columns: number): string {
  let used = 0;
  let clipped = '';
  for (const { segment } of segmenter.segment(text)) {
    const width = displayWidth(segment);
    if (used + width > Math.max(0, columns)) break;
    clipped += segment;
    used += width;
  }
  return clipped;
}

export function configureTerminalWidths(overrides: Record<string, number> = {}, native = false): void {
  widths = new Map(Object.entries(overrides).filter(([character, width]) =>
    [...character].length === 1 && (width === 1 || width === 2)));
  nativeConsole = native;
  setStringWidthFunction(displayWidth);
}

export function terminalLayoutColumns(columns: number | undefined): number {
  const physical = columns || 80;
  // Avoid a pending wrap at the physical last column on native conhost.
  return Math.max(1, physical - Number(nativeConsole));
}

/** The artwork's letter grid requires one terminal cell per block. */
export function bannerBlockCharacter(): string {
  if (!nativeConsole || widths.get('\u2586') !== 2) return '\u2586';
  // Do not infer a native font's width from the Unicode default.
  return ['\u25fc', '\u25aa'].find(character => widths.get(character) === 1) ?? '#';
}

export function initializeWindowsRendering(
  pythonPath: string | undefined,
  probePath: string,
): { mode: number; codePage: number } | undefined {
  if (process.platform !== 'win32' || !process.stdout.isTTY) return;
  if (!pythonPath) {
    logger.warn('Windows rendering calibration unavailable: Python interpreter not configured');
    return;
  }
  const result = spawnSync(pythonPath, ['-I', probePath, '--parent-pid', String(process.pid), '--prepare-output'], {
    encoding: 'utf8', windowsHide: true, timeout: 5000, maxBuffer: 128 * 1024,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  try {
    if (result.error || result.status !== 0) throw result.error ?? new Error(`Probe exited ${result.status}`);
    const profile = JSON.parse(result.stdout);
    if (profile.renderer === 'external-terminal') return;
    if (profile.renderer !== 'native-console' || !profile.widths ||
      typeof profile.widths !== 'object' || Object.keys(profile.widths).length === 0) {
      throw new Error(profile.error || 'Invalid console width profile');
    }
    configureTerminalWidths(profile.widths, true);
    if (profile.outputState) {
      const state = JSON.stringify(profile.outputState);
      process.once('exit', () => {
        spawnSync(pythonPath, [
          '-I', probePath, '--parent-pid', String(process.pid), '--restore-output', state,
        ], { windowsHide: true, timeout: 1500, stdio: 'ignore' });
      });
    }
    logger.info('Native Windows rendering calibrated', {
      font: profile.font, fontSize: profile.fontSize,
      outputCodePage: profile.outputCodePage, calibratedCharacters: widths.size,
    });
    return profile.outputState;
  } catch (error) {
    logger.warn('Windows rendering calibration failed', { error: String(error) });
  }
}

export default displayWidth;