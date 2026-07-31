/**
 * Banner Component
 * Displays the Siada CLI welcome banner with ASCII art and system information
 * Mimics the style from siada-cli TTY mode with gradient colors
 * Refactored to use Ink's native border components
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';

export interface BannerProps {
  version?: string;
  workingDir: string;
  agent?: string;
  provider?: string;
  model?: string;
  prePlanMode?: boolean;
  isCollapsed?: boolean;
  showAgentInfo?: boolean;
  quotaUsage?: string | null;
}

export const Banner: React.FC<BannerProps> = ({
  version,
  workingDir,
  agent = 'coder',
  provider = 'default',
  model,
  prePlanMode = true,
  isCollapsed = false,
  showAgentInfo = true,
  quotaUsage = null,
}) => {
  // Use reactive terminal size hook for responsive banner
  const { columns } = useTerminalSize();
  // Reserve two columns for left/right borders so content fits snugly
  const contentWidth = Math.max(0, columns - 2);
  // ASCII art lines - matching siada-cli output
  const bannerLines = [
    "  ▆▆▆▆▆▆▆╗▆▆╗ ▆▆▆▆▆╗ ▆▆▆▆▆▆╗  ▆▆▆▆▆╗      ▆▆▆▆▆▆╗▆▆╗     ▆▆╗",
    "  ▆▆╔════╝▆▆║▆▆╔══▆▆╗▆▆╔══▆▆╗▆▆╔══▆▆╗    ▆▆╔════╝▆▆║     ▆▆║",
    "  ▆▆▆▆▆▆▆╗▆▆║▆▆▆▆▆▆▆║▆▆║  ▆▆║▆▆▆▆▆▆▆║    ▆▆║     ▆▆║     ▆▆║",
    "  ╚════▆▆║▆▆║▆▆╔══▆▆║▆▆║  ▆▆║▆▆╔══▆▆║    ▆▆║     ▆▆║     ▆▆║",
    "  ▆▆▆▆▆▆▆║▆▆║▆▆║  ▆▆║▆▆▆▆▆▆╔╝▆▆║  ▆▆║    ╚▆▆▆▆▆▆╗▆▆▆▆▆▆▆╗▆▆║",
    "  ╚══════╝╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝     ╚═════╝╚══════╝╚═╝",
  ];

  // Gradient palette: 256-color indices mapped from terminal screenshot
  //   75, 111, 117, 116, 115, 121
  //   75  -> #5F87FF
  //   111 -> #87AFFF
  //   117 -> #87D7FF
  //   116 -> #5FD7AF
  //   115 -> #5FD787
  //   121 -> #87FF87
  const lineColors = [
    '#71a8fb', // color(75)  Blue
    '#87AFFF', // color(111) Bright blue
    '#87D7FF', // color(117) Light blue (GitHub theme start)
    '#6bccac', // color(116) Cyan-ish
    '#76e5c0', // color(115) Light cyan-green
    '#7aebc5', // color(121) Light green
  ];

  // Theme color for borders: brighter blue from gradient, matching panel border in screenshot
  const borderColor = '#87D7FF';

  // Helper to render a single content line inside left/right borders
  const renderContentLine = (children: React.ReactNode, key: React.Key) => (
    <Box key={key} width={columns}>
      {/* Side borders use brighter theme color with bold for contrast on dark bg */}
      <Text color={borderColor} bold>
        │
      </Text>
      <Box width={contentWidth}>{children}</Box>
      <Text color={borderColor} bold>
        │
      </Text>
    </Box>
  );

  // Build top and bottom border lines with embedded title
  const innerWidth = Math.max(0, contentWidth);
  const titleText = version ? `Siada CLI v${version}` : 'Siada CLI';
  const titleSegment = `─ ${titleText} `;
  const topMiddle = innerWidth > 0
    ? (titleSegment.length >= innerWidth
        ? titleSegment.slice(0, innerWidth)
        : titleSegment + '─'.repeat(innerWidth - titleSegment.length))
    : '';
   const topBorder = `╭${topMiddle}╮`;
   const bottomBorder = `╰${innerWidth > 0 ? '─'.repeat(innerWidth) : ''}╯`;

  return (
    <Box flexDirection="column" width={columns}>
       {/* Top border with embedded title */}
       <Text color={borderColor} bold>
         {topBorder}
       </Text>

      {/* Empty spacer line */}
      {renderContentLine(<Text>{' '.repeat(contentWidth)}</Text>, 'spacer-top')}

      {/* ASCII Art Banner with left-to-right gradient colors (responsive to terminal width) */}
      {bannerLines.map((line, index) => {
        // Preserve all spaces (including leading) to avoid breaking ASCII art layout
        const chars = [...line];
        // Limit visible characters to current content width to avoid overflow/ghosting
        const maxChars = contentWidth > 0 ? Math.min(chars.length, contentWidth) : chars.length;
        const visibleChars = chars.slice(0, maxChars);
        const paddingLength = Math.max(0, contentWidth - visibleChars.length);
        const padding = ' '.repeat(paddingLength);

        return renderContentLine(
          <>
            {visibleChars.map((ch, i) => {
               // Color index algorithm mirrors Python banner.py::_show_pretty_banner
               // color_index = min(int(gradient_pos * len(colors)), len(colors) - 1)
               const ratio = visibleChars.length <= 1 ? 0 : i / (visibleChars.length - 1);
               const colorIndex = Math.min(
                 Math.floor(ratio * lineColors.length),
                 lineColors.length - 1,
               );
              const color = lineColors[colorIndex];

              return (
                <Text key={i} color={color} bold>
                  {ch}
                </Text>
              );
            })}
            {paddingLength > 0 && <Text>{padding}</Text>}
          </>,
          index
        );
      })}

      {/* Spacer */}
      {renderContentLine(<Text>{' '.repeat(contentWidth)}</Text>, 'spacer-middle-1')}

      {/* Working Directory */}
      {renderContentLine(
        (() => {
          const label = 'Working Directory: ';
          const fullPath = workingDir;
          const maxWidth = contentWidth;

          const maxPathLen =
            label.length + fullPath.length > maxWidth
              ? Math.max(0, maxWidth - label.length)
              : fullPath.length;

          const visiblePath = fullPath.slice(0, maxPathLen);
          const used = label.length + visiblePath.length;
          const paddingLen = Math.max(0, maxWidth - used);
          const padding = ' '.repeat(paddingLen);

          return (
            <>
               <Text>{label}</Text>
               <Text color={borderColor}>{visiblePath}</Text>
              {paddingLen > 0 && <Text>{padding}</Text>}
            </>
          );
        })(),
        'working-dir'
      )}

      {/* Agent, Provider, Model info */}
      {showAgentInfo && renderContentLine(
        (() => {
          type Segment = { text: string; color?: string };

          const segments: Segment[] = [
            { text: 'Agent: ' },
            { text: agent, color: 'yellow' },
            { text: ', Provider: ' },
            { text: provider, color: 'yellow' },
            { text: ', Model: ' },
            { text: model || 'default', color: 'yellow' },
          ];

          if (prePlanMode) {
            segments.push({ text: '; ' });
            segments.push({ text: 'pre-plan mode', color: 'green' });
          }

          if (quotaUsage !== null && quotaUsage !== undefined) {
            segments.push({ text: '; Balance: ' });
            segments.push({ text: quotaUsage, color: 'green' });
          }

          segments.push({ text: '; ' });
          segments.push({
            text: isCollapsed ? 'compact mode' : 'expanded mode',
            color: isCollapsed ? 'cyan' : 'gray'
          });
          segments.push({ text: ' (ctrl+o)' });

          const nodes: React.JSX.Element[] = [];
          let used = 0;

          segments.forEach((seg, idx) => {
            if (used >= contentWidth) return;
            const remain = contentWidth - used;
            const piece = seg.text.slice(0, remain);
            if (!piece) return;
            nodes.push(
              <Text key={idx} color={seg.color as any}>{piece}</Text>
            );
            used += piece.length;
          });

          const paddingLen = Math.max(0, contentWidth - used);
          const padding = ' '.repeat(paddingLen);

          return (
            <>
              {nodes}
              {paddingLen > 0 && <Text>{padding}</Text>}
            </>
          );
        })(),
        'agent-info'
      )}

       {/* Bottom spacer */}
       {renderContentLine(<Text>{' '.repeat(contentWidth)}</Text>, 'spacer-bottom')}

       {/* Bottom border */}
       <Text color={borderColor} bold>
         {bottomBorder}
       </Text>
    </Box>
  );
};
