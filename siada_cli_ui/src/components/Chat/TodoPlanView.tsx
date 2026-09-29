import React from 'react';
import { Box, Text, useStdout } from '@jrichman/ink';
import stringWidth from 'string-width';
import type { TodoItem } from '../../hooks/useAcp/types.js';
import { useThemeVersion } from '../../themes/index.js';
import { colors } from '../../utils/colors.js';
import { ToolHeading } from './ToolHeading.js';

const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });

function wrapStep(text: string, width: number): string[] {
  const rows: string[] = [];
  let row = '';
  let rowWidth = 0;
  for (const { segment } of segmenter.segment(text.replaceAll('\t', '    '))) {
    const next = stringWidth(segment);
    if (row && rowWidth + next > width) {
      rows.push(row.trimEnd());
      row = '';
      rowWidth = 0;
    }
    if (!row && segment === ' ') continue;
    row += segment;
    rowWidth += next;
  }
  rows.push(row.trimEnd());
  return rows;
}

/** Completed todo snapshots are saved in history; intermediate updates stay live. */
export const TodoPlanView: React.FC<{
  items: TodoItem[];
  collapsed: boolean;
  maxRows?: number;
}> = ({ items, collapsed, maxRows }) => {
  useThemeVersion();
  const { stdout } = useStdout();
  const columns = stdout?.columns || process.stdout.columns || 80;
  // Only the step in progress is highlighted; done and pending steps step down
  // one tone instead of competing with it.
  const currentColor = colors.info;
  const idleColor = colors.content.secondary;
  const completed = items.filter(item => item.status === 'completed').length;
  const title = items.length === 0 ? 'Plan cleared'
    : collapsed ? `Plan completed (${completed}/${items.length})`
      : `Updated Plan (${completed}/${items.length})`;

  // A single summary line is all compact history needs; TodoStatusBar shows
  // intermediate progress independently. A clear operation has no body.
  if (collapsed || items.length === 0) return <ToolHeading parts={[title]} />;

  const rows = items.flatMap((item, index) => {
    const icon = item.status === 'completed' ? '✓' : item.status === 'in_progress' ? '◐' : '○';
    // Two columns of outer indentation, five for the tree/status prefix, and
    // one spare column prevent Ink from soft-wrapping at the final cell.
    return wrapStep(item.content, Math.max(1, columns - 8)).map((line, lineIndex) => ({
      line, icon: lineIndex === 0 ? icon : '  ',
      status: item.status, first: lineIndex === 0, firstItem: index === 0,
    }));
  });
  const visible = maxRows === undefined ? rows : rows.slice(0, maxRows);

  return (
    <Box flexDirection="column">
      <ToolHeading parts={[title]} />
      <Box flexDirection="column" paddingLeft={2}>
        {visible.map((row, index) => {
          const color = row.status === 'in_progress' ? currentColor : idleColor;
          return (
            <Box key={index}>
              <Text color={color}>{row.firstItem && row.first ? '└ ' : '  '}{row.icon} </Text>
              <Text color={color} bold={row.status === 'in_progress'}>{row.line}</Text>
            </Box>
          );
        })}
        {visible.length < rows.length && <Text color={idleColor}>    … {rows.length - visible.length} more lines</Text>}
      </Box>
    </Box>
  );
};
