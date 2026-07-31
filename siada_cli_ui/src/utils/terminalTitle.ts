/**
 * Set the terminal tab/window title via OSC 0 (set title + icon).
 *
 * Strips control characters so a stray backend response can't inject
 * escape sequences into the terminal. On Windows classic conhost doesn't
 * support OSC, so we fall back to `process.title`.
 */
export function setTerminalTitle(title: string): void {
  // eslint-disable-next-line no-control-regex
  const clean = title.replace(/[\x00-\x1f\x7f]/g, '').trim();
  if (!clean) return;

  if (process.platform === 'win32') {
    process.title = clean;
    return;
  }

  process.stdout.write(`\x1b]0;${clean}\x07`);
}
