import { BANNER_LINES } from '../../constants/banner.js';
import { bannerBlockCharacter, clipToColumns, displayWidth } from '../../utils/terminalWidth.js';

export const BANNER_COLORS = ['#71a8fb', '#87AFFF', '#87D7FF', '#6bccac', '#76e5c0', '#7aebc5'];
export const BANNER_FRAME_MS = 33;
const LETTERS = [[2, 10], [10, 13], [13, 21], [21, 29], [29, 37], [41, 49], [49, 57], [57, 60]];
const SWEEP_MS = 500;

export interface BannerPoint { x: number; y: number }

/** One mounted banner owns its lighting state; no timer runs after it settles. */
export class BannerMotion {
  readonly lines: string[][];
  readonly baseColors: string[][];
  private lights: number[][];
  private pointer: BannerPoint | null = null;
  private letter = -1;
  private sweeps: { letter: number; started: number }[] = [];
  private lastTick: number | null = null;

  constructor(columns: number) {
    const block = bannerBlockCharacter();
    this.lines = BANNER_LINES.map(line => [...clipToColumns(line.replaceAll('\u2586', block), columns)]);
    this.baseColors = this.lines.map(line => line.map((_, x) =>
      BANNER_COLORS[Math.min(5, Math.floor((line.length <= 1 ? 0 : x / (line.length - 1)) * 6))],
    ));
    this.lights = this.lines.map(line => line.map(() => 0));
  }

  move(point: BannerPoint | null, now: number): void {
    const cell = point ? { x: Math.floor(point.x), y: Math.floor(point.y) } : null;
    if (cell && cell.y >= 0 && cell.y < this.lines.length) {
      let column = 0;
      const index = this.lines[cell.y].findIndex(character => {
        const end = column + displayWidth(character);
        const hit = cell.x >= column && cell.x < end;
        column = end;
        return hit;
      });
      cell.x = index;
    }
    const next = cell && cell.y >= 0 && cell.y < this.lines.length &&
      cell.x >= 0 && cell.x < this.lines[cell.y].length
      ? LETTERS.findIndex(([start, end]) => cell.x >= start && cell.x < end) : -1;
    this.pointer = next < 0 ? null : cell;
    if (next !== this.letter) {
      if (next >= 0) {
        this.sweeps = this.sweeps.filter(sweep => sweep.letter !== next);
        this.sweeps.push({ letter: next, started: now });
      }
      this.letter = next;
    }
    if (this.hasEffect) this.lastTick ??= now;
  }

  get hasEffect(): boolean {
    return this.pointer !== null || this.sweeps.length > 0 ||
      this.lights.some(line => line.some(light => light !== 0));
  }

  reset(): string[][] {
    this.pointer = null;
    this.letter = -1;
    this.sweeps = [];
    this.lastTick = null;
    this.lights = this.lines.map(line => line.map(() => 0));
    return this.baseColors;
  }

  tick(now: number): { colors: string[][]; animating: boolean } {
    const dt = Math.max(1, Math.min(100, now - (this.lastTick ?? now - BANNER_FRAME_MS)));
    this.lastTick = now;
    this.sweeps = this.sweeps.filter(sweep => now - sweep.started < SWEEP_MS);
    let settling = false;
    const colors = this.lines.map((line, y) => line.map((character, x) => {
      let target = 0;
      if (character !== ' ') {
        if (this.pointer) {
          const distance = Math.hypot(x - this.pointer.x, (y - this.pointer.y) * 1.65);
          target = .95 * Math.max(0, 1 - distance / 9);
          const [start, end] = LETTERS[this.letter];
          // A whole-letter floor survives 256-color quantization, even over a gap.
          if (x >= start && x < end) target = Math.max(target, .72);
        }
        for (const sweep of this.sweeps) {
          const [start, end] = LETTERS[sweep.letter];
          if (x < start || x >= end) continue;
          const progress = (now - sweep.started) / SWEEP_MS;
          const center = start - 1 + progress * (end - start + 2);
          const band = Math.max(0, 1 - Math.abs(x - center) / 2);
          target = Math.max(target, band * Math.sin(progress * Math.PI));
        }
      }
      const current = this.lights[y][x];
      const light = current + (target - current) * (1 - Math.exp(-dt / (target > current ? 35 : 65)));
      if (Math.abs(target - light) > .002) settling = true;
      this.lights[y][x] = Math.abs(target - light) > .002 ? light : target;
      if (this.lights[y][x] === 0) return this.baseColors[y][x];
      return '#' + [1, 3, 5].map(offset => {
        const channel = parseInt(this.baseColors[y][x].slice(offset, offset + 2), 16);
        return Math.round(channel + (255 - channel) * this.lights[y][x]).toString(16).padStart(2, '0');
      }).join('');
    }));
    const animating = settling || this.sweeps.length > 0;
    if (!animating) this.lastTick = null;
    return { colors, animating };
  }
}