import type { Key, KeypressHandler } from '../contexts/KeypressContext.js';

/** Maximum separation of a mouse report and its alternate-scroll arrow burst. */
export const JEDITERM_WHEEL_PAIR_MS = 30;

export function isJediTerm(): boolean {
  return [process.env.TERM_PROGRAM, process.env.TERMINAL_EMULATOR]
    .some(value => /^(?:JetBrains-)?JediTerm$/i.test(value ?? ''));
}

export type DisposableKeypressHandler = KeypressHandler & { dispose: () => void };

/**
 * Reworked JediTerm reports zero wheel rotation as SGR wheel-up, but emits no
 * alternate-scroll arrows for it (getUnitsToScroll() is zero). Nonzero wheel
 * events emit a matching arrow burst. Detect that behavior before requiring
 * confirmation, keeping terminals without alternate-scroll reporting intact.
 */
export function createJediTermWheelFilter(handler: KeypressHandler): DisposableKeypressHandler {
  const enabled = isJediTerm();
  let paired = false;
  let disposed = false;
  let last: { key: Key; at: number; pending: boolean } | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;

  const cancelPending = () => {
    if (timer !== undefined) clearTimeout(timer);
    timer = undefined;
    if (last) last.pending = false;
  };

  const processor: KeypressHandler = key => {
    if (disposed) return;
    if (!enabled) { handler(key); return; }
    if (key.name === 'wheelup' || key.name === 'wheeldown') {
      cancelPending();
      last = { key, at: Date.now(), pending: paired && key.name === 'wheelup' };
      if (last.pending) {
        // An unconfirmed report carries no reliable direction information.
        timer = setTimeout(cancelPending, JEDITERM_WHEEL_PAIR_MS);
      } else handler(key);
      return;
    }
    const plainArrow = !key.insertable && !key.shift && !key.alt && !key.ctrl && !key.cmd &&
      /^\x1b(?:\[[AB]|O[AB])$/.test(key.sequence);
    if (plainArrow && last && Date.now() - last.at < JEDITERM_WHEEL_PAIR_MS &&
      key.name === (last.key.name === 'wheelup' ? 'up' : 'down')) {
      paired = true;
      if (last.pending) {
        const wheel = last.key;
        cancelPending();
        handler(wheel);
      }
      // The matched arrows are terminal-generated duplicates of the wheel.
      return;
    }
    if (key.name !== 'mousemove') {
      cancelPending();
      last = undefined;
    }
    handler(key);
  };
  return Object.assign(processor, {
    dispose: () => { disposed = true; cancelPending(); last = undefined; },
  });
}