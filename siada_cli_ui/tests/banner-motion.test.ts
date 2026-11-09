import { describe, expect, it } from 'vitest';
import chalk from 'chalk';
import { BannerMotion } from '../src/components/Banner/bannerMotion.js';
import { BANNER_LINES } from '../src/constants/banner.js';

describe('banner lighting', () => {
  it('follows the pointer locally and returns exactly to its original colors', () => {
    const motion = new BannerMotion(80);
    motion.move({ x: 26, y: 2 }, 0);
    const lit = motion.tick(100);
    expect(lit.colors[2][26]).not.toBe(motion.baseColors[2][26]);
    expect(lit.colors[2][2]).toBe(motion.baseColors[2][2]);
    motion.move(null, 100);
    let faded = lit;
    for (let now = 133; now <= 900; now += 33) faded = motion.tick(now);
    expect(faded.colors).toEqual(motion.baseColors);
    expect(faded.animating).toBe(false);
    expect(motion.hasEffect).toBe(false);
  });

  it('sweeps once on letter entry and stays idle after the pointer settles', () => {
    const motion = new BannerMotion(80);
    motion.move({ x: 2, y: 0 }, 0);
    const sweep = motion.tick(250).colors[5][6];
    expect(sweep).not.toBe(motion.baseColors[5][6]);
    for (let now = 283; now < 900; now += 33) motion.tick(now);
    motion.move({ x: 3, y: 0 }, 900);
    expect(motion.tick(1150).colors[5][6]).not.toBe(motion.baseColors[5][6]);
    // Staying within S must not restart the moving white band.
    expect(motion.tick(1150).colors[5][6]).not.toBe(sweep);
    let settled = motion.tick(1183);
    for (let now = 1216; now < 1800; now += 33) settled = motion.tick(now);
    expect(settled.animating).toBe(false);
    motion.move({ x: 11, y: 0 }, 1800);
    expect(motion.tick(2050).colors[5][11]).not.toBe(motion.baseColors[5][11]);
  });

  it('visibly lights every D stroke in 256-color mode when hovering its interior gap', () => {
    const previousLevel = chalk.level;
    chalk.level = 2;
    try {
      const motion = new BannerMotion(100);
      motion.move({ x: 24, y: 2 }, 0);
      let lit = motion.tick(33);
      for (let now = 66; now < 1200; now += 33) lit = motion.tick(now);
      let changed = 0;
      for (let y = 0; y < motion.lines.length; y++) {
        for (let x = 21; x < 29; x++) {
          if (motion.lines[y][x] === ' ') continue;
          expect(chalk.hex(lit.colors[y][x])('X')).not.toBe(chalk.hex(motion.baseColors[y][x])('X'));
          changed++;
        }
      }
      expect(changed).toBeGreaterThan(25);
      expect(lit.animating).toBe(false);
    } finally { chalk.level = previousLevel; }
  });

  it.each([0, 1, 20, 60, 100])('keeps the shared artwork clipped at %i columns', columns => {
    const motion = new BannerMotion(columns);
    expect(motion.lines.map(line => line.join(''))).toEqual(BANNER_LINES.map(line => line.slice(0, columns)));
    for (const point of [{ x: -1, y: 0 }, { x: columns, y: 0 }, { x: 39, y: 2 }, { x: 3, y: 6 }]) {
      motion.move(point, 0);
      expect(motion.tick(100).colors).toEqual(motion.baseColors);
      expect(motion.hasEffect).toBe(false);
    }
  });

  it('discards sweeps and stale light when resetting an active banner', () => {
    const motion = new BannerMotion(80);
    for (let x = 2; x < 60; x += 3) {
      motion.move({ x, y: 2 }, x * 10);
      motion.tick(x * 10 + 1);
    }
    expect(motion.reset()).toEqual(motion.baseColors);
    expect(motion.tick(700)).toEqual({ colors: motion.baseColors, animating: false });
  });
});