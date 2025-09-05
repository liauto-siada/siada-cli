import * as colorDiff from 'color-diff';
import tailwindColors from 'tailwindcss/colors';
import { oklch, lab } from 'culori';

// convert Hex string to RGB
function hexString2RGB(hexStr: string): colorDiff.RGBColor {
    return {
        R: parseInt(hexStr.slice(1, 3), 16),
        G: parseInt(hexStr.slice(3, 5), 16),
        B: parseInt(hexStr.slice(5, 7), 16)
    }
}

// convert OKLCH to LAB
function oklchToLab(oklchValue: string): colorDiff.LabColor {
  const color = oklch(oklchValue);
  if (!color) throw new Error(`Invalid OKLCH color: ${oklchValue}`);

  // 转换为 LAB 格式（culori 的 LAB 与 color-diff 的 LAB 结构一致）
  const labColor = lab(color);
  return {
    L: labColor.l || 0,
    a: labColor.a || 0,
    b: labColor.b || 0,
  };
}

// convert to RGB
function getFullTailwindPalette(): Record<string, colorDiff.LabColor> {
  const palette: Record<string, colorDiff.LabColor> = {};

  for (const [colorName, shades] of Object.entries(tailwindColors)) {
    if (typeof shades === 'string') continue; // 跳过基础颜色（如 black/white）

    for (const [shade, oklchStr] of Object.entries(shades)) {
      if (typeof oklchStr !== 'string') continue;
      palette[`${colorName}-${shade}`] = oklchToLab(oklchStr);
    }
  }

  return palette;
}

/**
 * 根据输入的 RGBA 颜色，找到 Tailwind 调色板中最接近的颜色标签
 * @param rgb 输入颜色（RGB 格式）
 * @returns 最接近的 Tailwind 颜色标签（如 "red-500"）
 */
function findNearestTailwindColor(inputColor: colorDiff.RGBColor): string {
  // 忽略 Alpha 通道，转换为 color-diff 的 RGBColor 格式

  // 使用 CIEDE2000 算法比较颜色差异

  const fullTailwindColors = getFullTailwindPalette();
  let minDeltaE = Infinity;
  let closestColorLabel = '';

  for (const [label, color] of Object.entries(fullTailwindColors)) {
    const inputLab = colorDiff.rgb_to_lab(inputColor);
    const deltaE = colorDiff.diff(inputLab, color);
    if (deltaE < minDeltaE) {
      minDeltaE = deltaE;
      closestColorLabel = label;
    }
  }

  return closestColorLabel;
}

const l = ['#0A5BFC', '#00803E', '#AD231E', '#222732', '#0E50D3', '#AC7414', '#1A79FF', '#151E32', '#A9B2C7', '#B93A3A', '#0A5BFC']
const mindColorMap = new Map(l.map(e => [e, findNearestTailwindColor(hexString2RGB(e))]));

export { hexString2RGB, oklchToLab, getFullTailwindPalette, findNearestTailwindColor, mindColorMap };