/**
 * Effort Selector Component — scale-bar (ruler) picker.
 *
 * Renders a horizontal ruler: each effort level is a tick on the scale, the
 * currently-selected tick is highlighted with ● and a ▼ pointer above it.
 * Move with ◀ ▶ (or h/l), confirm with Enter, dismiss with Esc.
 */
import React, { useState, useCallback, useMemo } from 'react';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { patternForLevel } from './patterns.js';
import { useParticleMorph, type Cell } from './useParticleMorph.js';

export interface EffortSelectorProps {
  model: string;
  efforts: string[];
  /** Current effort level ('' or null when none is set yet). */
  current: string | null;
  onSelect: (level: string) => void;
  onExit: () => void;
}

const BORDER = '#87D7FF';

/** Particle canvas sits right of the ruler, same band. */
const CANVAS_HEIGHT = 7;
const CANVAS_WIDTH = 15;

/** Merge a grid row into colored text segments (consecutive same-color runs). */
function rowToSegments(row: (Cell | null)[]): { text: string; color?: string }[] {
  const segments: { text: string; color?: string }[] = [];
  for (const cell of row) {
    const ch = cell?.ch ?? ' ';
    const color = cell?.color;
    const last = segments[segments.length - 1];
    if (last && last.color === color) last.text += ch;
    else segments.push({ text: ch, color });
  }
  return segments;
}

export const EffortSelector: React.FC<EffortSelectorProps> = ({
  model,
  efforts,
  current,
  onSelect,
  onExit,
}) => {
  const idx = current ? efforts.indexOf(current) : -1;
  const [activeIndex, setActiveIndex] = useState(
    idx >= 0 ? idx : Math.max(0, efforts.length - 1),
  );
  const active = efforts[activeIndex] ?? '';

  const moveSelection = useCallback((delta: number) => {
    setActiveIndex(prev => {
      if (efforts.length === 0) return 0;
      return Math.min(efforts.length - 1, Math.max(0, prev + delta));
    });
  }, [efforts.length]);

  useKeypress(
    useCallback((key: any) => {
      if (key.name === 'left' || key.sequence === 'h') moveSelection(-1);
      else if (key.name === 'right' || key.sequence === 'l') moveSelection(1);
      else if (key.name === 'return') { if (active) onSelect(active); }
      else if (key.name === 'escape' || (key.ctrl && key.name === 'c') || key.sequence === 'q' || key.sequence === 'Q') onExit();
    }, [moveSelection, active, onSelect, onExit]),
  );

  // ---- Ruler construction ----
  // Each level spans slotWidth columns; the tick sits at the center of the slot.
  const slotWidth = 8;
  const totalWidth = Math.max(0, efforts.length * slotWidth);
  const centerOf = (i: number) => i * slotWidth + Math.floor(slotWidth / 2);

  // ---- Particle canvas: the pattern scales with the level and morphs on selection change ----
  const pattern = useMemo(
    () => patternForLevel(active, activeIndex, efforts.length),
    [active, activeIndex, efforts.length],
  );
  const particleGrid = useParticleMorph(pattern, CANVAS_WIDTH, CANVAS_HEIGHT);

  // Ruler line: ─ links the ticks; each tick holds ● (active level) or · (others).
  const ruler = Array.from({ length: totalWidth }, () => '─');
  efforts.forEach((_, i) => {
    ruler[centerOf(i)] = i === activeIndex ? '●' : '·';
  });

  // Pointer row: the ▼ above the active level.
  const pointer = Array.from({ length: totalWidth }, () => ' ');
  pointer[centerOf(activeIndex)] = '▼';

  // Label row: each level name centered under its tick (kept within slotWidth).
  const labelCells = efforts.map((level) => {
    const safe = level.length > slotWidth - 1 ? level.slice(0, slotWidth - 1) : level;
    const pad = Math.max(0, slotWidth - safe.length);
    const left = Math.floor(pad / 2);
    return ' '.repeat(left) + safe + ' '.repeat(pad - left);
  });

  return (
    <Box flexDirection="column" paddingX={1} width="100%" borderStyle="single" borderColor={BORDER}>
      <Box>
        <Text color={BORDER} bold>Reasoning Effort</Text>
        <Text color="gray"> (model: {model})</Text>
      </Box>

      <Box flexDirection="row" marginTop={1}>
        <Box flexDirection="column" marginTop={2}>
          <Text color={BORDER}>{pointer.join('')}</Text>
          <Text>
            {ruler.map((ch, i) => (
              <Text key={i} color={ch === '●' ? 'white' : 'dim'} bold={ch === '●'}>{ch}</Text>
            ))}
          </Text>
          <Text color="gray">
            {labelCells.map((cell, i) => (
              <Text key={i} color={i === activeIndex ? 'white' : 'gray'} bold={i === activeIndex}>{cell}</Text>
            ))}
          </Text>
        </Box>
        <Box flexDirection="column" marginLeft={3}>
          {particleGrid.map((row, y) => (
            <Text key={y}>
              {rowToSegments(row).map((seg, i) => (
                <Text key={i} color={seg.color}>{seg.text}</Text>
              ))}
            </Text>
          ))}
        </Box>
      </Box>

      <Box marginTop={1}>
        <Text color={BORDER}>◀ ▶ select · Enter confirm · Esc cancel</Text>
      </Box>
    </Box>
  );
};
