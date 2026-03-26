#!/usr/bin/env node
import React, { useState, useEffect } from 'react';
import { render, Box, Text } from 'ink';
import { MessageList } from '../src/components/Chat/MessageList.js';
import type { Message } from '../src/types/index.js';

// 生成带标记的测试内容 - 60 行
function generateMarkedContent(): string {
  const lines: string[] = [];
  lines.push('# ✅ 第一部分开始（应该在 Static 区域）');
  lines.push('');
  
  for (let i = 1; i <= 8; i++) {
    lines.push(`## 🟦 第 ${i} 小节`);
    lines.push('');
    lines.push(`这是第 ${i} 小节的内容。`);
    lines.push('内容行 1');
    lines.push('内容行 2');
    lines.push('');
  }
  
  lines.push('# ❌ 第二部分开始（应该在 Pending 区域）');
  lines.push('');
  lines.push('## 🟥 关键标记节');
  lines.push('');
  lines.push('如果你看到两个 "# ✅ 第一部分开始"，说明有重复渲染bug！');
  lines.push('正确的渲染应该是：');
  lines.push('- Static: # ✅ 第一部分 + 8个🟦小节');
  lines.push('- Pending: # ❌ 第二部分 + 🟥关键标记节');
  lines.push('');
  
  return lines.join('\n');
}

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'user-1',
      role: 'user',
      content: '测试拆分可视化',
      timestamp: Date.now(),
    }
  ]);
  
  const [charIndex, setCharIndex] = useState(0);
  const fullContent = generateMarkedContent();
  
  useEffect(() => {
    // 模拟流式输出
    if (charIndex < fullContent.length) {
      const timer = setTimeout(() => {
        const currentContent = fullContent.substring(0, charIndex + 10);
        
        setMessages([
          {
            id: 'user-1',
            role: 'user',
            content: '测试拆分可视化',
            timestamp: Date.now(),
          },
          {
            id: 'agent-1',
            role: 'assistant',
            content: currentContent,
            timestamp: Date.now(),
            metadata: {
              subtype: 'answer',
            }
          }
        ]);
        
        setCharIndex(charIndex + 10);
      }, 100);
      
      return () => clearTimeout(timer);
    }
  }, [charIndex, fullContent]);
  
  const lineCount = messages[messages.length - 1]?.content?.split('\n').length || 0;
  const hasSplit = lineCount > 50;
  
  return (
    <Box flexDirection="column">
      <Box marginBottom={1} paddingX={2} borderStyle="round" borderColor={hasSplit ? "green" : "yellow"}>
        <Text>
          {hasSplit ? "🎉 已触发拆分！" : "⏳ 等待触发拆分..."} 当前行数: <Text bold color="cyan">{lineCount}</Text> / 阈值: <Text bold>50</Text>
        </Text>
      </Box>
      
      {hasSplit && (
        <Box marginBottom={1} paddingX={2} borderStyle="single" borderColor="magenta">
          <Text>
            <Text bold color="magenta">🔍 验证点：</Text>{'\n'}
            1. 应该只看到<Text bold color="green">一个</Text> "# ✅ 第一部分开始"{'\n'}
            2. "# ❌ 第二部分开始" 应该在屏幕下方的 Pending 区域{'\n'}
            3. 如果看到两个 "# ✅"，说明有重复渲染bug！
          </Text>
        </Box>
      )}
      
      <MessageList messages={messages} />
    </Box>
  );
};

render(<App />);
