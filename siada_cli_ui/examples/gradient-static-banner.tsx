#!/usr/bin/env node
/**
 * Gradient Static Banner Demo
 * 
 * 展示使用 Ink 的 Static 组件渲染带有渐变色的 ASCII 艺术横幅
 * 渐变色从左到右过渡，每个字符根据其位置应用不同的颜色
 * 
 * 运行方式:
 *   npx tsx examples/gradient-static-banner.tsx
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
 * 渐变色横幅组件
 * 使用 Static 组件渲染，颜色从左到右过渡
 */
const GradientBanner: React.FC = () => {
  // 为 Static 组件准备数据：包含所有需要静态渲染的行
  const allLines = [
    { type: 'title', content: 'SIADA CLI - Static Banner Demo' },
    { type: 'separator', content: '═' },
    ...bannerLines.map(line => ({ type: 'banner', content: line })),
    { type: 'separator', content: '─' },
    { type: 'feature', content: '✓ 使用 Ink 的 Static 组件渲染' },
    { type: 'feature', content: '✓ 左到右渐变色效果 (蓝色 → 青色 → 绿色)' },
    { type: 'feature', content: '✓ 只渲染一次，性能优化' },
  ];

  return (
    <Box flexDirection="column" paddingX={1} paddingY={1}>
      {/* 使用 Static 组件 - 整个横幅只渲染一次 */}
      <Static items={allLines}>
        {(item, index) => {
          if (item.type === 'title') {
            return (
              <Text key={index} bold color="cyan">
                {item.content}
              </Text>
            );
          }
          
          if (item.type === 'separator') {
            return (
              <Text key={index} color="cyan">
                {item.content.repeat(70)}
              </Text>
            );
          }
          
          if (item.type === 'feature') {
            // 特性行：提取 ✓ 符号和文本
            const match = item.content.match(/^(✓)(.+)$/);
            if (match) {
              return (
                <Box key={index}>
                  <Text bold color="green">{match[1]}</Text>
                  <Text color="white">{match[2]}</Text>
                </Box>
              );
            }
            return <Text key={index}>{item.content}</Text>;
          }
          
          if (item.type === 'banner') {
            // 横幅行 - 应用渐变色
            const chars = [...item.content];
            return (
              <Box key={index}>
                {chars.map((ch, charIndex) => {
                  const ratio = chars.length <= 1 ? 0 : charIndex / (chars.length - 1);
                  const colorIndex = Math.floor(ratio * (lineColors.length - 1));
                  const color = lineColors[colorIndex];
                  return (
                    <Text key={charIndex} color={color}>
                      {ch}
                    </Text>
                  );
                })}
              </Box>
            );
          }
          
          return <Text key={index}>{item.content}</Text>;
        }}
      </Static>
      
      <Box paddingTop={1}>
        <Text dimColor italic>按 Ctrl+C 退出</Text>
      </Box>
    </Box>
  );
};

/**
 * 主应用组件
 */
const App: React.FC = () => {
  return (
    <Box flexDirection="column">
      <GradientBanner />
    </Box>
  );
};

// 清屏并渲染
console.clear();
render(<App />);
