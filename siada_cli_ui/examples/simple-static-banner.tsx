#!/usr/bin/env node
/**
 * Simple Static Banner Demo
 * 
 * 最简单的示例，展示如何使用 Ink 的 Static 组件渲染 ASCII 艺术横幅
 * 
 * 运行方式:
 *   npx tsx examples/simple-static-banner.tsx
 */

import React from 'react';
import { render, Box, Text, Static } from '@jrichman/ink';

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

/**
 * 简单的静态横幅组件
 */
const SimpleBanner: React.FC = () => {
  return (
    <Box flexDirection="column" paddingX={1}>
      {/* 使用 Static 组件 - 只渲染一次 */}
      <Static items={bannerLines}>
        {(line, lineIndex) => {
          const chars = [...line];
          const color = lineColors[lineIndex];
          
          return (
            <Box key={lineIndex}>
              {chars.map((ch, charIndex) => (
                <Text key={charIndex} color={color}>
                  {ch}
                </Text>
              ))}
            </Box>
          );
        }}
      </Static>
      
      <Box paddingTop={1}>
        <Text bold color="green">✓ Static Banner Demo - 横幅使用 Static 组件渲染</Text>
      </Box>
    </Box>
  );
};

// 渲染组件
console.clear();
render(<SimpleBanner />);
