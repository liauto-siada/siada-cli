import chalk from 'chalk';
import { describe, expect, it } from 'vitest';
import {
  STAR_HINT_FADE_MS, STAR_HINT_HOLD_MS, STAR_HINT_SWEEP_MS, STAR_HINT_TOTAL_MS,
  starHintColor, starHintLight,
} from '../src/components/Banner/bannerStarHint.js';

const span = { start: 40, width: 6 };
const light = (elapsed: number, column: number) => starHintLight(column, elapsed, span);
const brightest = (elapsed: number) => {
  let column = 0;
  for (let x = 0; x <= 60; x++) if (light(elapsed, x) > light(elapsed, column)) column = x;
  return column;
};

describe('banner star hint', () => {
  it('starts on the left rule and travels right without ever passing the star', () => {
    expect(light(0, 0)).toBeGreaterThan(0.8);
    expect(light(0, 6)).toBe(0);
    let previous = -1;
    for (let elapsed = 0; elapsed < STAR_HINT_SWEEP_MS; elapsed += 120) {
      const head = brightest(elapsed);
      expect(head).toBeGreaterThanOrEqual(previous);
      previous = head;
      for (let x = 48; x <= 60; x++) expect(light(elapsed, x)).toBe(0);
    }
    expect(previous).toBeGreaterThan(35);
  });

  it('lights the star once and fades back to the untouched row', () => {
    for (let x = span.start; x < span.start + span.width; x++) {
      expect(light(STAR_HINT_SWEEP_MS, x)).toBeCloseTo(1, 5);
      expect(light(STAR_HINT_SWEEP_MS + STAR_HINT_HOLD_MS / 2, x)).toBeCloseTo(1, 5);
    }
    const fading = light(STAR_HINT_SWEEP_MS + STAR_HINT_HOLD_MS + STAR_HINT_FADE_MS / 2, span.start);
    expect(fading).toBeGreaterThan(0);
    expect(fading).toBeLessThan(1);
    for (let x = 0; x <= 60; x++) {
      expect(light(STAR_HINT_TOTAL_MS, x)).toBe(0);
      expect(light(STAR_HINT_TOTAL_MS + 500, x)).toBe(0);
    }
  });

  it('stays dark for empty, negative and clipped spans', () => {
    expect(starHintLight(10, 400, { start: 0, width: 0 })).toBe(0);
    expect(starHintLight(10, Number.NaN, span)).toBe(0);
    expect(starHintLight(10, -1, span)).toBe(0);
    expect(starHintLight(120, 400, span)).toBe(0);
  });

  it('changes the rendered tone at every visible level in 256-color mode', () => {
    const previousLevel = chalk.level;
    chalk.level = 2;
    try {
      const base = '#87d7ff';
      const tones = [0, 0.45, 0.95].map(level => starHintColor(base, level, true));
      expect(tones[0]).toBe(base);
      for (let index = 1; index < tones.length; index++) {
        expect(tones[index]).not.toBe(tones[index - 1]);
        expect(chalk.hex(tones[index])('X')).not.toBe(chalk.hex(tones[index - 1])('X'));
      }
      expect(starHintColor(base, 1, false)).not.toBe(starHintColor(base, 1, true));
    } finally {
      chalk.level = previousLevel;
    }
  });
});
