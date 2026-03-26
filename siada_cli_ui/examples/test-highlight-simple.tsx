#!/usr/bin/env node
/**
 * Simple Syntax Highlighting Test
 * Quick demonstration of path and command highlighting
 */

import React from 'react';
import { render, Box, Text } from '@jrichman/ink';
import { HighlightedText } from '../src/components/common/HighlightedText.js';

const SimpleTest: React.FC = () => {
  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="cyan">
        🎨 Syntax Highlighting Demo
      </Text>
      <Text>{''}</Text>

      <Text bold>1. File Path Highlighting:</Text>
      <HighlightedText text="查看文件 /Users/caoxin/mycli/siada-cli-1.6.0/siada-cli-ui/src/utils/textHighlighter.ts" />
      <Text>{''}</Text>

      <Text bold>2. Bash Command Highlighting:</Text>
      <HighlightedText text="执行命令: $ npm install && npm run build" />
      <Text>{''}</Text>

      <Text bold>3. Inline Code Highlighting:</Text>
      <HighlightedText text="使用 `const x = 10` 定义变量" />
      <Text>{''}</Text>

      <Text bold>4. Mixed Content:</Text>
      <HighlightedText text="在 ~/project 目录运行 $ npm test 并查看 `jest.config.js` 配置" />
      <Text>{''}</Text>

      <Text bold>5. Relative Path:</Text>
      <HighlightedText text="配置文件位于 ./config/settings.json 和 ../src/index.ts" />
      <Text>{''}</Text>

      <Text bold color="green">✅ 测试完成！</Text>
      <Text dimColor>按 Ctrl+C 退出</Text>
    </Box>
  );
};

// Render the app
const { unmount, waitUntilExit } = render(<SimpleTest />);

// Handle cleanup
waitUntilExit().then(() => {
  unmount();
  process.exit(0);
});
