import React, { useEffect, useState } from 'react';
import { Text } from '@jrichman/ink';
import stringWidth from '../../utils/terminalWidth.js';
import { getActiveTheme, useThemeVersion } from '../../themes/index.js';
import { colors } from '../../utils/colors.js';

/** Terminal adaptation of vibe-motion's swinging spotlight text mask. */
export function SpotlightThinking({ text = 'Thinking…', active = true, ring = false }: {
  text?: string; active?: boolean; ring?: boolean;
}) {
  useThemeVersion();
  const [phase, setPhase] = useState(0);
  useEffect(() => {
    if (!active) return;
    const started = Date.now();
    const timer = setInterval(() => setPhase((Date.now() - started) / 1000), 80);
    return () => clearInterval(timer);
  }, [active]);
  const segments = [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(text)];
  const width = stringWidth(text);
  const center = (0.5 - Math.cos(phase * Math.PI / 2) / 2) * (width + 4) - 2;
  const dark = getActiveTheme() === 'dark';
  let column = 0;
  const pulse = (1 - Math.cos(phase * Math.PI / 1.6)) / 2;
  const blend = (from: string, to: string, amount: number) => '#' + [1, 3, 5].map(offset => {
    const start = parseInt(from.slice(offset, offset + 2), 16);
    const end = parseInt(to.slice(offset, offset + 2), 16);
    return Math.round(start + (end - start) * amount).toString(16).padStart(2, '0');
  }).join('');
  const dotColor = active ? blend(colors.content.tertiary, dark ? '#d0d7df' : '#39424e', pulse)
    : colors.content.secondary;
  return <Text wrap="truncate-end">
    {ring && <Text color={dotColor}>◉ </Text>}
    {segments.map(({ segment }, index) => {
    const cells = stringWidth(segment);
    const distance = Math.abs(column + cells / 2 - center);
    column += cells;
    const color = !active ? colors.content.secondary : distance < 1.3
      ? dark ? '#f1f4f8' : '#1f2328' : distance < 3 ? dark ? '#d0d7df' : '#39424e' : colors.content.secondary;
    return <Text key={index} color={color} bold={active && distance < 1.3}>{segment}</Text>;
  })}</Text>;
}