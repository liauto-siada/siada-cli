/**
 * Banner Component
 * Displays the Siada CLI welcome banner with ASCII art
 * Mimics the style from siada-cli TTY mode with gradient colors
 * Refactored to use Ink's native border components
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { BannerArt } from './BannerArt.js';
import { BannerHeader } from './BannerHeader.js';

export interface BannerProps {
  version?: string;
  workingDir: string;
  agent?: string;
  provider?: string;
  model?: string;
  isCollapsed?: boolean;
  showAgentInfo?: boolean;
  quotaUsage?: string | null;
  interactive?: boolean;
}

export const Banner: React.FC<BannerProps> = ({
  version,
  interactive = false,
}) => {
  // Use reactive terminal size hook for responsive banner
  const { columns } = useTerminalSize();
  // The banner has no side borders, so content uses the full terminal width
  const contentWidth = Math.max(0, columns);

  // Theme color for borders: brighter blue from gradient, matching panel border in screenshot
  const borderColor = '#87D7FF';

  // Helper to render a single content line (no side borders)
  const renderContentLine = (children: React.ReactNode, key: React.Key) => (
    <Box key={key} width={columns}>
      <Box width={contentWidth}>{children}</Box>
    </Box>
  );

  const innerWidth = Math.max(0, contentWidth);
  const bottomBorder = innerWidth > 0 ? '─'.repeat(innerWidth) : '';

  return (
    <Box flexDirection="column" width={columns}>
      <BannerHeader columns={contentWidth} version={version} interactive={interactive} />

      {/* Empty spacer line */}
      {renderContentLine(<Text>{' '.repeat(contentWidth)}</Text>, 'spacer-top')}

      <BannerArt columns={contentWidth} interactive={interactive} />

      {/* Spacer */}
      {renderContentLine(<Text>{' '.repeat(contentWidth)}</Text>, 'spacer-middle-1')}

       {/* Bottom spacer */}
       {renderContentLine(<Text>{' '.repeat(contentWidth)}</Text>, 'spacer-bottom')}

       {/* Bottom border */}
       <Text color={borderColor} bold>
         {bottomBorder}
       </Text>
    </Box>
  );
};
