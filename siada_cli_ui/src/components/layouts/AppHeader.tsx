/**
 * AppHeader Component
 * Static header that renders once and stays at the top
 * Combines Banner with version info and system status
 * 
 * OPTIMIZATION: Wrapped with React.memo to prevent re-renders
 * Uses Ink's built-in Box border instead of manual border drawing
 */

import React from 'react';
import { t, useUiLanguage } from '../../i18n/index.js';
import { Box, Text } from '@jrichman/ink';

export interface AppHeaderProps {
  version?: string;
  workingDir: string;
  agent?: string;
  provider?: string;
  model?: string;
  isCollapsed?: boolean;
}

export const AppHeader: React.FC<AppHeaderProps> = React.memo(({
  version = '0.0.0',
  workingDir,
  agent = 'coder',
  provider = 'default',
  model,
  isCollapsed = false,
}) => {
  useUiLanguage();
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

      {/* Working Directory */}
      <Box>
        <Text>{t('工作目录：', 'Working Directory: ')}</Text>
        <Text color="blue">{workingDir}</Text>
      </Box>

      {/* Provider routing stays out of the user-facing banner. */}
      <Box marginTop={0}>
        <Text>{t('智能体：', 'Agent: ')}</Text>
        <Text color="yellow">{agent}</Text>
        <Text>{t('，模型：', ', Model: ')}</Text>
        <Text color="yellow">{model || t('默认', 'default')}</Text>
        <Text>.</Text>
      </Box>

      {/* Collapse mode hint */}
      <Box marginTop={0}>
        <Text dimColor>{t('按 ', 'Press ')}</Text>
        <Text color="cyan" bold>Ctrl+O</Text>
        <Text dimColor>{t(` ${isCollapsed ? '显示' : '隐藏'}工具详情`, ` to ${isCollapsed ? 'show' : 'hide'} tool use details`)}</Text>
        <Text dimColor>{t('（当前：', ' (currently: ')}</Text>
        <Text color={isCollapsed ? 'yellow' : 'green'}>{isCollapsed ? t('精简', 'collapsed') : t('展开', 'expanded')}</Text>
        <Text dimColor>{t('）', ')')}</Text>
      </Box>
    </Box>
  );
});

AppHeader.displayName = 'AppHeader';
