#!/usr/bin/env node
import React, { useState, useEffect } from 'react';
import { render, Box, Text } from 'ink';
import { MessageList } from '../src/components/Chat/MessageList.js';
import type { Message } from '../src/types/index.js';

// 生成测试内容 - 60 行（会触发拆分）
function generateContent(): string {
  const lines: string[] = [];
  lines.push('# 拆分测试文档');
  lines.push('');
  lines.push('这是一份测试文档，用于验证拆分功能。');
  lines.push('');
  
  for (let i = 1; i <= 10; i++) {
    lines.push(`## 第 ${i} 部分`);
    lines.push('');
    lines.push(`这是第 ${i} 部分的内容。`);
    lines.push('内容行 1');
    lines.push('内容行 2');
    lines.push('');
  }
  
  return lines.join('\n');
}

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'user-1',
      role: 'user',
      content: '请生成一份测试文档。',
      timestamp: Date.now(),
    }
  ]);
  
  const [charIndex, setCharIndex] = useState(0);
  const fullContent = generateContent();
  
  useEffect(() => {
    // 模拟流式输出
    if (charIndex < fullContent.length) {
      const timer = setTimeout(() => {
        const currentContent = fullContent.substring(0, charIndex + 5);
        const lineCount = currentContent.split('\n').length;
        
        setMessages([
          {
            id: 'user-1',
            role: 'user',
            content: '请生成一份测试文档。',
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
        
        // 在控制台输出当前行数（不会被 Ink 捕获）
        if (lineCount === 50 || lineCount === 51) {
          process.stderr.write(`\n[DEBUG] 当前行数: ${lineCount}, 字符: ${charIndex}\n`);
        }
        
        setCharIndex(charIndex + 5);
      }, 50);
      
      return () => clearTimeout(timer);
    }
  }, [charIndex, fullContent]);
  
  const lineCount = messages[messages.length - 1]?.content?.split('\n').length || 0;
  
  return (
    <Box flexDirection="column">
      <Box marginBottom={1}>
        <Text color="yellow">
          📊 当前行数: {lineCount} / 阈值: 50 / 字符: {charIndex}/{fullContent.length}
        </Text>
      </Box>
      <MessageList messages={messages} />
    </Box>
  );
};

render(<App />);
