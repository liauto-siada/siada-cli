import React from 'react';
import { Box, Text, useStdout } from '@jrichman/ink';
import stringWidth from 'string-width';
import { useThemeVersion } from '../../themes/index.js';
import { colors } from '../../utils/colors.js';

const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });

export function parseCommandContent(content: string): { body: string; timeout?: string } {
  // The backend adds spaces after both the heading and the fence language,
  // and may append a timeout below the closing fence.
  const withoutHeading = content.replace(/^Run the following (?:PowerShell )?command:[ \t]*(?:\r?\n|$)/, '');
  const openingFence = withoutHeading.match(/^```(?:bash|sh|shell|zsh|powershell|pwsh|cmd)?[ \t]*\r?\n/);
  if (!openingFence) return { body: withoutHeading };
  const fencedBody = withoutHeading.slice(openingFence[0].length);
  // The greedy body selects the final fence, even if the command itself
  // contains a line of backticks. Leave incomplete streams untouched.
  const closingFence = fencedBody.match(/^([\s\S]*)\r?\n```[ \t]*(?:\r?\n([\s\S]*))?$/);
  if (!closingFence) return { body: fencedBody };
  const details = closingFence[2];
  const timeout = details?.match(/^timeout:[ \t]*`?([^`\r\n]+)`?$/);
  if (timeout) return { body: closingFence[1]!, timeout: timeout[1]!.trim() };
  return { body: details ? `${closingFence[1]}\n${details}` : closingFence[1]! };
}

function wrapPlainLine(line: string, width: number): string[] {
  const rows: string[] = [];
  let row = '';
  let rowWidth = 0;
  for (const { segment } of segmenter.segment(line.replaceAll('\t', '    '))) {
    const segmentWidth = stringWidth(segment);
    if (row && rowWidth + segmentWidth > width) {
      rows.push(row);
      row = '';
      rowWidth = 0;
    }
    row += segment;
    rowWidth += segmentWidth;
  }
  rows.push(row);
  return rows;
}

/** Plain, monochrome command display for expanded shell tool calls. */
export const CommandView: React.FC<{ content: string; hiddenLinesCount?: number }> = ({ content, hiddenLinesCount = 0 }) => {
  useThemeVersion();
  const { stdout } = useStdout();
  const columns = stdout?.columns || process.stdout.columns || 80;
  // Two columns for the indentation, two spare columns to avoid terminal auto-wrap.
  const width = Math.max(2, columns - 4);
  const display = hiddenLinesCount > 0
    ? `... ${hiddenLinesCount} lines hidden ...\n${content}`
    : content;
  // Terminals cannot blend a translucent background over their own palette, so
  // the command area uses a near-background surface tone from the theme. The
  // text itself keeps the terminal foreground, like every other body text.
  const background = colors.content.surface;

  if (!display) return null;
  const rows = display.split(/\r?\n/).flatMap(line => wrapPlainLine(line, width));
  return (
    <Box flexDirection="column" paddingLeft={2}>
      {rows.map((line, index) => (
        <Text key={index} backgroundColor={background}>
          {line}{' '.repeat(Math.max(0, width - stringWidth(line)))}
        </Text>
      ))}
    </Box>
  );
};
