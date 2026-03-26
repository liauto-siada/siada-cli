#!/usr/bin/env node
/**
 * Mini Split Demo - 用于快速测试拆分功能
 * 
 * 阈值：2行
 * 总长度：4行
 * 预期效果：达到第3行时触发拆分
 */

import React, { useState, useEffect } from 'react';
import { render, Box, Text } from '@jrichman/ink';
import { MessageList } from '../src/components/Chat/MessageList.js';
import type { Message } from '../src/types/index.js';

// 生成简单的4行内容
function generateSimpleContent(): string {
  return [
    '# 🔵 第1行：开始标记',
    '第2行：这是第二行内容',
    '第3行：这是第三行内容（触发拆分！）',
    '# 🔴 第4行：结束标记',
  ].join('\n');
}

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'user-1',
      role: 'user',
      content: '请生成4行内容',
      timestamp: Date.now(),
    }
  ]);
  
  const [charIndex, setCharIndex] = useState(0);
  const fullContent = generateSimpleContent();
  
  useEffect(() => {
    if (charIndex < fullContent.length) {
      const timer = setTimeout(() => {
        const currentContent = fullContent.substring(0, charIndex + 3);
        
        setMessages([
          {
            id: 'user-1',
            type: 'user',
            role: 'user',
            content: '请生成4行内容',
            timestamp: Date.now(),
          },
          {
            id: 'agent-1',
            type: 'agent',
            role: 'assistant',
            content: currentContent,
            timestamp: Date.now(),
            metadata: {
              subtype: 'answer',
            }
          }
        ]);
        
        setCharIndex(charIndex + 3);
      }, 200);
      
      return () => clearTimeout(timer);
    }
  }, [charIndex, fullContent]);
  
  const lineCount = messages[messages.length - 1]?.content?.split('\n').length || 0;
  const hasSplit = lineCount > 2;
  
  // 直接显示消息内容，不经过MessageList的复杂逻辑
  const agentMessage = messages.find(m => m.role === 'assistant');
  const displayContent = agentMessage?.content || '';
  
  // 调试：打印消息状态
  useEffect(() => {
    if (hasSplit && charIndex === fullContent.length) {
      // eslint-disable-next-line no-console
      console.error(`\n\n====拆分测试完成====`);
      // eslint-disable-next-line no-console
      console.error(`消息总数: ${messages.length}`);
      // eslint-disable-next-line no-console
      console.error(`行数: ${lineCount}`);
      // eslint-disable-next-line no-console
      console.error(`拆分状态: ${hasSplit ? '已拆分' : '未拆分'}`);
      // eslint-disable-next-line no-console
      console.error(`内容长度: ${displayContent.length}`);
      // eslint-disable-next-line no-console
      console.error(`==================\n`);
    }
  }, [hasSplit, charIndex, fullContent.length, messages.length, lineCount, displayContent.length]);
  
  return (
    <Box flexDirection="column">
      <Box 
        marginBottom={1} 
        paddingX={2} 
        borderStyle="round" 
        borderColor={hasSplit ? "green" : "yellow"}
      >
        <Text>
          {hasSplit ? "✅ 已拆分" : "⏳ 等待拆分"} | 
          当前: <Text bold color="cyan">{lineCount}</Text> 行 | 
          阈值: <Text bold color="magenta">2</Text> 行 | 
          字符: <Text color="gray">{charIndex}/{fullContent.length}</Text>
        </Text>
      </Box>
      
      <Box marginBottom={1} borderStyle="single" borderColor="cyan">
        <Text color="cyan">📋 原始消息内容:</Text>
      </Box>
      
      <Box marginBottom={1} padding={1} borderStyle="single">
        <Text>{displayContent}</Text>
      </Box>
      
      <Box marginBottom={1} borderStyle="single" borderColor="magenta">
        <Text color="magenta">🔧 通过MessageList渲染:</Text>
      </Box>
      
      <MessageList messages={messages} />
      
      {hasSplit && (
        <Box marginTop={1} paddingX={1} borderStyle="single" borderColor="green">
          <Text color="green">
            🎉 拆分已触发！请观察：{'\n'}
            • "🔵 第1行" 应该只出现一次{'\n'}
            • "🔴 第4行" 应该只出现一次{'\n'}
            • 检查上方消息是否有重复内容
          </Text>
        </Box>
      )}
    </Box>
  );
};

render(<App />);
