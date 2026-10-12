import React from 'react';
import { Box, Text, useStdout } from '@jrichman/ink';
import type { ParsedToolCall } from '../../utils/toolCallParser.js';
import { getSemanticToolCallDisplay } from '../../utils/toolCallDisplay.js';
import { colors } from '../../utils/colors.js';
import { ToolHeading } from './ToolHeading.js';
import { wrapToolFieldText } from './ToolPromptView.js';

export const SemanticToolCallView: React.FC<{ tool: ParsedToolCall; maxRows?: number }> = ({ tool, maxRows }) => {
  const { stdout } = useStdout();
  const display = getSemanticToolCallDisplay(tool);
  if (!display) return null;

  // Leave room for indentation, tree markers and the terminal's last column.
  const columns = stdout?.columns || process.stdout.columns || 80;
  const width = Math.max(2, columns - 6);
  const rows = display.fields.flatMap((field, index) => {
    const branch = index === display.fields.length - 1 ? '└─ ' : '├─ ';
    return wrapToolFieldText(`${field.label}: ${field.value}`, width).map((line, lineIndex) => ({
      prefix: lineIndex === 0 ? branch : '   ',
      line,
    }));
  });
  const visibleCount = maxRows === undefined || rows.length <= maxRows - 1
    ? rows.length : Math.max(0, maxRows - 2);

  return (
    <Box flexDirection="column">
      <ToolHeading parts={[display.heading]} />
      {rows.slice(0, visibleCount).map(({ prefix, line }, index) => (
        <Box key={index} paddingLeft={2}>
          <Text color={colors.content.secondary}>{prefix}</Text>
          <Text>{line}</Text>
        </Box>
      ))}
      {visibleCount < rows.length && (
        <Box paddingLeft={2}>
          <Text color={colors.content.secondary}>   … {rows.length - visibleCount} more lines</Text>
        </Box>
      )}
    </Box>
  );
};