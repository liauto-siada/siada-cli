import { describe, expect, test } from "bun:test";
import { changedRegions, type Pixels } from "./diff";

const SIZE = 256;

/** Uniform grey frame. */
function blank(value = 0, width = SIZE, height = SIZE): Pixels {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let i = 0; i < data.length; i += 4) {
    data[i] = value;
    data[i + 1] = value;
    data[i + 2] = value;
    data[i + 3] = 255;
  }
  return { data, width, height };
}

/** Flood-fill a rectangle with a flat colour. */
function paint(pixels: Pixels, rect: { x: number; y: number; w: number; h: number }, value: number): Pixels {
  for (let y = rect.y; y < rect.y + rect.h; y++) {
    for (let x = rect.x; x < rect.x + rect.w; x++) {
      const i = (y * pixels.width + x) * 4;
      pixels.data[i] = value;
      pixels.data[i + 1] = value;
      pixels.data[i + 2] = value;
    }
  }
  return pixels;
}

describe("changedRegions", () => {
  test("identical frames have no changed regions", () => {
    expect(changedRegions(blank(128), blank(128))).toEqual([]);
  });

  test("a changed block becomes one rectangle in frame pixels", () => {
    const before = blank(0);
    const after = paint(blank(0), { x: 32, y: 64, w: 64, h: 96 }, 255);

    expect(changedRegions(before, after, { cellSize: 32 })).toEqual([
      { x: 32, y: 64, w: 64, h: 96 },
    ]);
  });

  test("sub-threshold noise is ignored", () => {
    const before = blank(0);
    const after = paint(blank(0), { x: 0, y: 0, w: 128, h: 128 }, 10);

    expect(changedRegions(before, after, { threshold: 24 })).toEqual([]);
    expect(changedRegions(before, after, { threshold: 5 })).toHaveLength(1);
  });

  test("separated changes produce separate rectangles", () => {
    const before = blank(0);
    const after = paint(blank(0), { x: 0, y: 0, w: 32, h: 32 }, 255);
    paint(after, { x: 128, y: 128, w: 32, h: 32 }, 255);

    const regions = changedRegions(before, after, { cellSize: 32 });
    expect(regions).toHaveLength(2);
    expect(regions).toContainEqual({ x: 0, y: 0, w: 32, h: 32 });
    expect(regions).toContainEqual({ x: 128, y: 128, w: 32, h: 32 });
  });

  test("regions are ordered largest first and capped", () => {
    const after = blank(0);
    // Four blocks of increasing size, far enough apart not to merge.
    paint(after, { x: 0, y: 0, w: 32, h: 32 }, 255);
    paint(after, { x: 64, y: 0, w: 64, h: 32 }, 255);
    paint(after, { x: 0, y: 64, w: 96, h: 32 }, 255);
    paint(after, { x: 0, y: 128, w: 128, h: 32 }, 255);

    const regions = changedRegions(blank(0), after, { cellSize: 32, maxRegions: 2 });
    expect(regions).toHaveLength(2);
    expect(regions[0]!.w).toBe(128);
    expect(regions[1]!.w).toBe(96);
  });

  test("a bigger cell size merges nearby changes into fewer regions", () => {
    const after = blank(0);
    paint(after, { x: 0, y: 0, w: 32, h: 32 }, 255);
    paint(after, { x: 0, y: 32, w: 32, h: 32 }, 255);

    expect(changedRegions(blank(0), after, { cellSize: 32 })).toEqual([
      { x: 0, y: 0, w: 32, h: 64 },
    ]);
    expect(changedRegions(blank(0), after, { cellSize: 64 })).toEqual([
      { x: 0, y: 0, w: 64, h: 64 },
    ]);
  });

  test("mismatched or empty sizes compare as nothing", () => {
    expect(changedRegions(blank(0, 64, 64), blank(255, 32, 32))).toEqual([]);
    expect(changedRegions(blank(0, 0, 0), blank(255, 0, 0))).toEqual([]);
  });

  test("regions never exceed the frame bounds", () => {
    // 100x100 with a 32px cell leaves a partial trailing cell on each axis.
    const before = blank(0, 100, 100);
    const after = paint(blank(0, 100, 100), { x: 96, y: 96, w: 4, h: 4 }, 255);

    expect(changedRegions(before, after, { cellSize: 32 })).toEqual([
      { x: 96, y: 96, w: 4, h: 4 },
    ]);
  });
});
