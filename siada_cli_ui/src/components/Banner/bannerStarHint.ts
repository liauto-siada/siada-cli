/**
 * Banner star hint.
 *
 * One light leaves the left edge of the navigation row, travels along the rule
 * and title, then lights the Star link once — the same self-lit look as the
 * thinking spotlight, without a background block. The cycle plays once per
 * banner mount and leaves no timer running afterwards.
 */

export const STAR_HINT_FRAME_MS = 33;
/** Deliberately unhurried: the light should be noticed, not flashed past. */
export const STAR_HINT_SWEEP_MS = 1900;
export const STAR_HINT_HOLD_MS = 420;
export const STAR_HINT_FADE_MS = 900;
/** Half-width, in columns, of the travelling highlight band. */
const HEAD_RADIUS = 3;
const LIT_DARK = '#f4fcff';
const LIT_LIGHT = '#0b2a38';

export const STAR_HINT_TOTAL_MS = STAR_HINT_SWEEP_MS + STAR_HINT_HOLD_MS + STAR_HINT_FADE_MS;

/** Columns the Star label occupies inside its navigation row. */
export interface StarSpan { start: number; width: number }

const clamp = (value: number) => Math.min(1, Math.max(0, value));
const smooth = (value: number) => {
  const unit = clamp(value);
  return unit * unit * (3 - 2 * unit);
};

/** 0..1 brightness at `column`, `elapsed` ms after the banner appeared. */
export function starHintLight(column: number, elapsed: number, span: StarSpan): number {
  if (!Number.isFinite(elapsed) || elapsed < 0 || span.width <= 0) return 0;
  const center = column + 0.5;
  const head = smooth(elapsed / STAR_HINT_SWEEP_MS) * (span.start + span.width / 2);
  const band = elapsed < STAR_HINT_SWEEP_MS ? clamp(1 - Math.abs(center - head) / HEAD_RADIUS) : 0;
  const settled = elapsed - STAR_HINT_SWEEP_MS;
  const lit = settled < 0 ? 0
    : settled < STAR_HINT_HOLD_MS ? 1
      : 1 - smooth((settled - STAR_HINT_HOLD_MS) / STAR_HINT_FADE_MS);
  // The trailing pad belongs to the link, so a click target never looks half lit.
  const inside = center >= span.start && center < span.start + span.width + 1;
  return clamp(Math.max(band, inside ? lit : 0));
}

/** Blend towards the theme's highlight tone; the gamma keeps mid-tones apart in 256-color mode. */
export function starHintColor(base: string, light: number, dark: boolean): string {
  const amount = Math.pow(clamp(light), 0.8);
  const target = dark ? LIT_DARK : LIT_LIGHT;
  return '#' + [1, 3, 5].map(offset => {
    const from = parseInt(base.slice(offset, offset + 2), 16);
    const to = parseInt(target.slice(offset, offset + 2), 16);
    return Math.round(from + (to - from) * amount).toString(16).padStart(2, '0');
  }).join('');
}
