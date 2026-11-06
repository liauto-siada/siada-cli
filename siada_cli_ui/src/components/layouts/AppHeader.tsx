/**
 * AppHeader Component
 * Static header that renders once and stays at the top
 * Combines Banner with version info and system status
 * 
 * OPTIMIZATION: Wrapped with React.memo to prevent re-renders
 * Uses Ink's built-in Box border instead of manual border drawing
 */

import React from 'react';
import { Box, Text } from '@jrichman/ink';

export interface AppHeaderProps {
  version?: string;
  workingDir: string;
  agent?: string;
  provider?: string;
  model?: string;
  isCollapsed?: boolean;
}

export const AppHeader: React.FC<AppHeaderProps> = React.memo(() => {
  // ASCII art lines - matching siada-cli output
  const bannerLines = [
      "  ▆▆▆▆▆▆▆╗▆▆╗ ▆▆▆▆▆╗ ▆▆▆▆▆▆╗  ▆▆▆▆▆╗      ▆▆▆▆▆▆╗▆▆╗     ▆▆╗",
      "  ▆▆╔════╝▆▆║▆▆╔══▆▆╗▆▆╔══▆▆╗▆▆╔══▆▆╗    ▆▆╔════╝▆▆║     ▆▆║",
      "  ▆▆▆▆▆▆▆╗▆▆║▆▆▆▆▆▆▆║▆▆║  ▆▆║▆▆▆▆▆▆▆║    ▆▆║     ▆▆║     ▆▆║",
      "  ╚════▆▆║▆▆║▆▆╔══▆▆║▆▆║  ▆▆║▆▆╔══▆▆║    ▆▆║     ▆▆║     ▆▆║",
      "  ▆▆▆▆▆▆▆║▆▆║▆▆║  ▆▆║▆▆▆▆▆▆╔╝▆▆║  ▆▆║    ╚▆▆▆▆▆▆╗▆▆▆▆▆▆▆╗▆▆║",
      "  ╚══════╝╚═╝╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝     ╚═════╝╚══════╝╚═╝"
  ];

  // Gradient colors matching siada-cli TTY banner
  const lineColors = [
    '#5b8cd5', // color(75)  Blue
    '#6BA5E7', // color(111) Bright blue
    '#79B8FF', // color(117) Light blue (GitHub theme start)
    '#7FC9E8', // color(116) Cyan
    '#85D89D', // color(115) Light cyan-green
    '#85E89D', // color(121) Light green (GitHub theme end)
  ];

  return (
    <Box 
      flexDirection="column" 
      borderStyle="round" 
      borderColor="cyan"
      paddingX={1}
      paddingY={0}
    >

      {/* ASCII Art Banner with left-to-right gradient colors */}
      {bannerLines.map((line, index) => {
        const chars = [...line];
        
        return (
          <Box key={index}>
            {chars.map((ch, i) => {
              const ratio = chars.length <= 1 ? 0 : i / (chars.length - 1);
              const colorIndex = Math.floor(ratio * (lineColors.length - 1));
              const color = lineColors[colorIndex];

              return (
                <Text key={i} color={color}>{ch}</Text>
              );
            })}
          </Box>
        );
      })}

      {/* Spacer */}
      <Box marginTop={1} />

    </Box>
  );
});

AppHeader.displayName = 'AppHeader';
