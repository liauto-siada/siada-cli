/**
 * Effort Selector Component — scale-bar (刻度尺) picker.
 *
 * Renders a horizontal ruler: each effort level is a tick on the scale, the
 * currently-selected tick is highlighted with ● and a ▼ pointer above it.
 * Move with ◀ ▶ (or h/l), confirm with Enter, dismiss with Esc.
 */
import React, { useState, useCallback, useMemo } from 'react';
import { PickerFrame, pickerHint } from '../Picker/Picker.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { colors } from '../../utils/colors.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { patternForLevel } from './patterns.js';
import { useParticleMorph, type Cell } from './useParticleMorph.js';

export interface EffortSelectorProps {
  embedded?: boolean;
  model: string;
  efforts: string[];
  /** Current effort level ('' or null when none is set yet). */
  current: string | null;
  onSelect: (level: string) => void;
  onExit: () => void;
}


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
  useUiLanguage();
  const { columns, rows } = useTerminalSize();
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

  // ---- 刻度尺构建 ----
  // 每档占 slotWidth 个字符，刻点（tick）位于档位单元的正中。
  const slotWidth = Math.max(1, Math.min(8, Math.floor((columns - 2) / Math.max(1, efforts.length))));
  const totalWidth = Math.max(0, efforts.length * slotWidth);
  const showParticles = columns - 2 >= totalWidth + 3 + CANVAS_WIDTH && rows >= CANVAS_HEIGHT + 5;
  const centerOf = (i: number) => i * slotWidth + Math.floor(slotWidth / 2);

  // ---- 粒子画布：菱形图案随档位缩放，选择变化时联动形变 ----
  const pattern = useMemo(
    () => patternForLevel(active, activeIndex, efforts.length),
    [active, activeIndex, efforts.length],
  );
  const particleGrid = useParticleMorph(pattern, CANVAS_WIDTH, CANVAS_HEIGHT);

  // 尺线：─ 连接，每个刻点上放 ●（当前档）或 ·（其余档）。
  const ruler = Array.from({ length: totalWidth }, () => '─');
  efforts.forEach((_, i) => {
    ruler[centerOf(i)] = i === activeIndex ? '●' : '·';
  });

  // 指示行：当前档位上方的 ▼。
  const pointer = Array.from({ length: totalWidth }, () => ' ');
  pointer[centerOf(activeIndex)] = '▼';

  // 档位名行：每个刻点下居中显示该档位名称（避免溢出 slotWidth）。
  const labelCells = efforts.map((level) => {
    const safe = level.length > slotWidth - 1 ? level.slice(0, slotWidth - 1) : level;
    const pad = Math.max(0, slotWidth - safe.length);
    const left = Math.floor(pad / 2);
    return ' '.repeat(left) + safe + ' '.repeat(pad - left);
  });

  return (
    <PickerFrame title={t('推理强度', 'Reasoning Effort')}
      summary={`${t('当前：', 'Current: ')}${current || t('模型默认', 'model default')} · ${model}`}
      hint={pickerHint('horizontal')}>
      <Box flexDirection="row">
        <Box flexDirection="column" marginTop={showParticles ? 1 : 0}>
          <Text color={colors.content.secondary}>{pointer.join('')}</Text>
          <Text>
            {ruler.map((ch, i) => (
              <Text key={i} color={ch === '●' ? undefined : colors.content.secondary} bold={ch === '●'}>{ch}</Text>
            ))}
          </Text>
          <Text color={colors.content.secondary}>
            {labelCells.map((cell, i) => (
              <Text key={i} color={i === activeIndex ? undefined : colors.content.secondary} bold={i === activeIndex}>{cell}</Text>
            ))}
          </Text>
        </Box>
        {showParticles && <Box flexDirection="column" marginLeft={3}>
          {particleGrid.map((row, y) => (
            <Text key={y}>
              {rowToSegments(row).map((seg, i) => (
                <Text key={i} color={seg.color}>{seg.text}</Text>
              ))}
            </Text>
          ))}
        </Box>}
      </Box>

    </PickerFrame>
  );
};
