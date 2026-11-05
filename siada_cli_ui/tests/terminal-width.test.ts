import { afterEach, describe, expect, it } from 'vitest';
import { BannerMotion } from '../src/components/Banner/bannerMotion.js';
import { BANNER_LINES } from '../src/constants/banner.js';
import { clipToColumns, configureTerminalWidths, displayWidth, terminalLayoutColumns } from '../src/utils/terminalWidth.js';

afterEach(() => configureTerminalWidths());

describe('native terminal width agreement', () => {
  it('retains existing Unicode widths without a native profile', () => {
    expect(displayWidth('A界👩‍💻')).toBe(5);
    expect(displayWidth('▆●☆─')).toBe(4);
    expect(terminalLayoutColumns(80)).toBe(80);
  });

  it('measures ANSI text using calibrated glyphs rather than a blanket CJK rule', () => {
    configureTerminalWidths({ '▆': 2, '●': 2, '☆': 2, '─': 1 }, true);
    expect(displayWidth('\x1b[31m▆●☆─\x1b[0m')).toBe(7);
    expect(displayWidth('界')).toBe(2);
    expect(terminalLayoutColumns(80)).toBe(79);
    expect(terminalLayoutColumns(1)).toBe(1);
  });

  it('keeps combining marks and emoji sequences intact', () => {
    configureTerminalWidths({ 'Ω': 2, '❤': 2 }, true);
    expect(displayWidth('Ω\u0301')).toBe(2);
    expect(displayWidth('❤️')).toBe(2);
    expect(displayWidth('👩‍💻')).toBe(2);
    expect(clipToColumns('Ω\u0301界', 3)).toBe('Ω\u0301');
    expect(clipToColumns('A👩‍💻B', 2)).toBe('A');
  });

  it('clips wide text while keeping native artwork and hover on a single-cell grid', () => {
    configureTerminalWidths({ '▆': 2, '◼': 1, '▪': 1 }, true);
    expect(clipToColumns('  ▆▆', 5)).toBe('  ▆');
    const narrow = new BannerMotion(5);
    expect(narrow.lines[0].join('')).toBe('  ◼◼◼');
    expect(narrow.lines.every(line => displayWidth(line.join('')) <= 5)).toBe(true);
    const wide = new BannerMotion(120);
    wide.move({ x: 4, y: 0 }, 0);
    expect(wide.hasEffect).toBe(true);
    expect(wide.tick(100).colors[0][4]).not.toBe(wide.baseColors[0][4]);
  });

  it('aligns every letter across all six rows when native blocks occupy two cells', () => {
    configureTerminalWidths({ '▆': 2, '◼': 1, '▪': 1 }, true);
    const motion = new BannerMotion(120);
    const starts = [2, 10, 13, 21, 29, 41, 49, 57];
    expect(motion.lines.map(line => line.length)).toEqual([60, 60, 60, 60, 60, 60]);
    for (const line of motion.lines) {
      expect(line.every(character => displayWidth(character) === 1)).toBe(true);
      expect(starts.map(index => displayWidth(line.slice(0, index).join('')))).toEqual(starts);
    }
    expect(motion.lines.map(line => line.join(''))).toEqual(BANNER_LINES.map(line => line.replaceAll('▆', '◼')));
  });

  it('lights the complete native D and fades to the same original frame', () => {
    configureTerminalWidths({ '▆': 2, '◼': 1, '▪': 1 }, true);
    const motion = new BannerMotion(120);
    motion.move({ x: 24, y: 2 }, 0);
    let result = motion.tick(33);
    for (let now = 66; now < 900; now += 33) result = motion.tick(now);
    for (let y = 0; y < motion.lines.length; y++) {
      for (let x = 21; x < 29; x++) {
        if (motion.lines[y][x] !== ' ') expect(result.colors[y][x]).not.toBe(motion.baseColors[y][x]);
      }
      expect(result.colors[y][2]).toBe(motion.baseColors[y][2]);
    }
    motion.move(null, 900);
    for (let now = 933; now < 1800; now += 33) result = motion.tick(now);
    expect(result).toEqual({ colors: motion.baseColors, animating: false });
  });

  it.each([{}, { '◼': 2 }])('retains the small square if the larger square is unmeasured or wide: %j', extra => {
    configureTerminalWidths({ '▆': 2, '▪': 1, ...extra }, true);
    expect(new BannerMotion(120).lines.map(line => line.join('')))
      .toEqual(BANNER_LINES.map(line => line.replaceAll('▆', '▪')));
  });

  it.each([{}, { '▪': 2 }])('uses a one-cell ASCII block when the candidate is unmeasured or wide: %j', extra => {
    configureTerminalWidths({ '▆': 2, ...extra }, true);
    const motion = new BannerMotion(120);
    expect(motion.lines.map(line => line.join(''))).toEqual(BANNER_LINES.map(line => line.replaceAll('▆', '#')));
    expect(motion.lines.every(line => displayWidth(line.join('')) === 60)).toBe(true);
  });

  it('keeps the original artwork for ordinary terminals and one-cell native blocks', () => {
    for (const [overrides, native] of [[{}, false], [{ '▆': 1, '▪': 1 }, true],
      [{ '▆': 2, '▪': 1 }, false]] as const) {
      configureTerminalWidths(overrides, native);
      const motion = new BannerMotion(120);
      expect(motion.lines.map(line => line.join(''))).toEqual(BANNER_LINES);
    }
  });

  it('clears the width model when restoring default rendering', () => {
    configureTerminalWidths({ '●': 2 }, true);
    expect(displayWidth('●')).toBe(2);
    configureTerminalWidths();
    expect(displayWidth('●')).toBe(1);
    expect(terminalLayoutColumns(80)).toBe(80);
  });
});