import React from 'react';
import { Box, Text, useStdout } from '@jrichman/ink';
import stringWidth from '../../utils/terminalWidth.js';
import type { ParsedToolCall } from '../../utils/toolCallParser.js';
import { getSemanticToolCallDisplay } from '../../utils/toolCallDisplay.js';
import { colors } from '../../utils/colors.js';
import { ToolHeading } from './ToolHeading.js';
import { wrapHeading, wrapToolFieldText } from './ToolPromptView.js';

export const SemanticToolCallView: React.FC<{
  tool: ParsedToolCall;
  maxRows?: number;
  width?: number;
  showHeading?: boolean;
}> = ({ tool, maxRows, width: availableWidth, showHeading = true }) => {
  const { stdout } = useStdout();
  const display = getSemanticToolCallDisplay(tool);
  if (!display) return null;

  // Leave room for indentation, tree markers and the terminal's last column.
  const columns = availableWidth ?? (stdout?.columns || process.stdout.columns || 80);
  const width = Math.max(2, columns - 6);
  const headingIndent = showHeading ? stringWidth(`● ${display.heading} `) : 0;
  const argumentRows = display.headingArgument ? wrapHeading(
    display.headingArgument, Math.max(2, columns - headingIndent - 1),
    Math.max(2, columns - headingIndent - 1),
  ) : [];
  const headingCount = Math.max(showHeading ? 1 : 0, argumentRows.length);
  const rows = display.fields.flatMap((field, index) => {
    const branch = index === display.fields.length - 1 ? '└─ ' : '├─ ';
    return wrapToolFieldText(`${field.label}: ${field.value}`, width).map((line, lineIndex) => ({
      prefix: lineIndex === 0 ? branch : '   ',
      line,
    }));
  });
  const totalRows = headingCount + rows.length;
  const budget = maxRows === undefined ? totalRows : Math.max(1, maxRows);
  const contentBudget = totalRows > budget ? budget - 1 : budget;
  const shownHeadingCount = Math.min(headingCount, contentBudget);
  const visibleArguments = argumentRows.slice(0, shownHeadingCount);
  const visibleCount = Math.min(rows.length, Math.max(0, contentBudget - shownHeadingCount));
  const hiddenCount = totalRows - shownHeadingCount - visibleCount;

  return (
    <Box flexDirection="column">
      {showHeading && shownHeadingCount > 0 ? <ToolHeading parts={[display.heading]}
        suffix={visibleArguments[0] ? <> {visibleArguments[0]}</> : undefined} />
        : visibleArguments[0] && <Text>{visibleArguments[0]}</Text>}
      {visibleArguments.slice(1).map((line, index) => (
        <Box key={`argument-${index}`} paddingLeft={headingIndent}>
          <Text>{line}</Text>
        </Box>
      ))}
      {rows.slice(0, visibleCount).map(({ prefix, line }, index) => (
        <Box key={index} paddingLeft={2}>
          <Text color={colors.content.secondary}>{prefix}</Text>
          <Text>{line}</Text>
        </Box>
      ))}
      {hiddenCount > 0 && (
        <Box paddingLeft={2}>
          <Text color={colors.content.secondary}>   … {hiddenCount} more lines</Text>
        </Box>
      )}
    </Box>
  );
};