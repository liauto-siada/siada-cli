#!/usr/bin/env node
/**
 * Syntax Highlighting Test
 * Demonstrates the new smart highlighting features for:
 * - File paths (38 languages supported via lowlight)
 * - Bash commands
 * - Inline code
 * - URLs
 */

import React from 'react';
import { render, Box, Text } from '@jrichman/ink';
import { HighlightedText } from '../src/components/common/HighlightedText.js';
import { MarkdownText } from '../src/components/common/MarkdownText.js';

const TestApp: React.FC = () => {
  return (
    <Box flexDirection="column" padding={1}>
      <Text bold color="cyan">
        🎨 Syntax Highlighting Test - 38 Languages Supported
      </Text>
      <Text dimColor>
        arduino, bash, c, cpp, csharp, css, diff, go, graphql, ini, java,
      </Text>
      <Text dimColor>
        javascript, json, kotlin, less, lua, makefile, markdown, objectivec,
      </Text>
      <Text dimColor>
        perl, php, php-template, plaintext, python, python-repl, r, ruby,
      </Text>
      <Text dimColor>
        rust, scss, shell, sql, swift, typescript, vbnet, wasm, xml, yaml
      </Text>
      <Text>{''}</Text>

      {/* Test 1: File Paths */}
      <Box flexDirection="column" borderStyle="round" borderColor="blue" paddingX={1}>
        <Text bold color="yellow">📁 Test 1: File Path Highlighting</Text>
        <Text>{''}</Text>
        
        <Text color="gray">Unix absolute path:</Text>
        <HighlightedText text="请查看文件 /Users/caoxin/mycli/siada-cli-1.6.0/siada-cli-ui/src/components/markdown/CodeColorizer.tsx" />
        <Text>{''}</Text>
        
        <Text color="gray">Relative path:</Text>
        <HighlightedText text="配置文件位于 ./config/settings.json 和 ../src/index.ts" />
        <Text>{''}</Text>
        
        <Text color="gray">Home directory:</Text>
        <HighlightedText text="日志存储在 ~/logs/app.log 目录" />
        <Text>{''}</Text>
      </Box>

      <Text>{''}</Text>

      {/* Test 2: Bash Commands */}
      <Box flexDirection="column" borderStyle="round" borderColor="green" paddingX={1}>
        <Text bold color="yellow">💻 Test 2: Bash Command Highlighting</Text>
        <Text>{''}</Text>
        
        <Text color="gray">Command with prompt:</Text>
        <HighlightedText text="$ npm install && npm run build" />
        <Text>{''}</Text>
        
        <Text color="gray">Common commands:</Text>
        <HighlightedText text="cd /tmp && ls -la | grep test" />
        <Text>{''}</Text>
        
        <Text color="gray">Docker command:</Text>
        <HighlightedText text="docker run -it --rm node:18 bash" />
        <Text>{''}</Text>
      </Box>

      <Text>{''}</Text>

      {/* Test 3: Inline Code */}
      <Box flexDirection="column" borderStyle="round" borderColor="magenta" paddingX={1}>
        <Text bold color="yellow">🔤 Test 3: Inline Code Highlighting</Text>
        <Text>{''}</Text>
        
        <Text color="gray">Backtick code:</Text>
        <HighlightedText text="使用 `const greeting = 'Hello'` 来定义变量" />
        <Text>{''}</Text>
        
        <Text color="gray">Function reference:</Text>
        <HighlightedText text="调用 `highlightSegments()` 函数处理文本" />
        <Text>{''}</Text>
      </Box>

      <Text>{''}</Text>

      {/* Test 4: Mixed Content */}
      <Box flexDirection="column" borderStyle="round" borderColor="cyan" paddingX={1}>
        <Text bold color="yellow">🎯 Test 4: Mixed Content Highlighting</Text>
        <Text>{''}</Text>
        
        <HighlightedText text="在 /Users/caoxin/project 目录下运行 $ npm test 执行测试，使用 `jest --coverage` 生成报告" />
        <Text>{''}</Text>
      </Box>

      <Text>{''}</Text>

      {/* Test 5: Code Blocks with Language Support */}
      <Box flexDirection="column" borderStyle="round" borderColor="yellow" paddingX={1}>
        <Text bold color="yellow">🌈 Test 5: Code Block Language Support (38 Languages)</Text>
        <Text>{''}</Text>
        
        <Text color="gray">TypeScript example:</Text>
        <MarkdownText 
          content={`\`\`\`typescript
const greeting: string = "Hello, World!";
function sayHello(name: string): void {
  console.log(\`Hello, \${name}!\`);
}
\`\`\``}
        />
        <Text>{''}</Text>

        <Text color="gray">Python example:</Text>
        <MarkdownText 
          content={`\`\`\`python
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
\`\`\``}
        />
        <Text>{''}</Text>

        <Text color="gray">Bash example:</Text>
        <MarkdownText 
          content={`\`\`\`bash
#!/bin/bash
for i in {1..5}; do
  echo "Iteration $i"
done
\`\`\``}
        />
        <Text>{''}</Text>

        <Text color="gray">JSON example:</Text>
        <MarkdownText 
          content={`\`\`\`json
{
  "name": "siada-cli-ui",
  "version": "0.1.0",
  "dependencies": {
    "lowlight": "^3.3.0"
  }
}
\`\`\``}
        />
        <Text>{''}</Text>
      </Box>

      <Text>{''}</Text>

      {/* Test 6: Markdown with Smart Highlighting */}
      <Box flexDirection="column" borderStyle="round" borderColor="white" paddingX={1}>
        <Text bold color="yellow">📝 Test 6: Markdown + Smart Highlighting</Text>
        <Text>{''}</Text>
        
        <MarkdownText 
          content={`## 配置说明

修改配置文件 ~/config/app.yaml 并执行以下命令：

$ cd /opt/app && ./setup.sh

使用 \`npm run dev\` 启动开发服务器。

**注意**: 确保 /var/log/app.log 有写入权限。`}
        />
      </Box>

      <Text>{''}</Text>
      <Text bold color="green">✅ 测试完成！</Text>
      <Text dimColor>按 Ctrl+C 退出</Text>
    </Box>
  );
};

// Render the app
const { unmount, waitUntilExit } = render(<TestApp />);

// Handle cleanup
waitUntilExit().then(() => {
  unmount();
  process.exit(0);
});
