#!/usr/bin/env node
import React, { useState, useEffect } from 'react';
import { render, Box, Text, useStdout } from 'ink';
import { MessageList } from '../src/components/Chat/MessageList.js';
import type { Message } from '../src/types/index.js';

// 生成带唯一标记的测试内容
function generateUniqueContent(): string {
  const lines: string[] = [];
  lines.push('# 🔵 UNIQUE_MARKER_START_001');
  lines.push('');
  lines.push('这是第一部分的内容，应该在 Static 区域。');
  lines.push('');
  
  for (let i = 1; i <= 10; i++) {
    lines.push(`## 第 ${i} 节`);
    lines.push(`内容 ${i}.1`);
    lines.push(`内容 ${i}.2`);
    lines.push(`内容 ${i}.3`);
    lines.push('');
  }
  
  lines.push('# 🔴 UNIQUE_MARKER_END_999');
  lines.push('');
  lines.push('这是第二部分的内容，应该在 Pending 区域。');
  lines.push('如果你在输出中看到两次 "UNIQUE_MARKER_START_001"，说明有重复bug！');
  lines.push('');
  
  return lines.join('\n');
}

const App: React.FC = () => {
  const { stdout } = useStdout();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'user-1',
      role: 'user',
      content: '测试唯一性标记',
      timestamp: Date.now(),
    }
  ]);
  
  const [charIndex, setCharIndex] = useState(0);
  const [completed, setCompleted] = useState(false);
  const fullContent = generateUniqueContent();
  
  useEffect(() => {
    if (charIndex < fullContent.length) {
      const timer = setTimeout(() => {
        const currentContent = fullContent.substring(0, charIndex + 15);
        
        setMessages([
          {
            id: 'user-1',
            role: 'user',
            content: '测试唯一性标记',
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
        
        setCharIndex(charIndex + 15);
      }, 50);
      
      return () => clearTimeout(timer);
    } else if (!completed) {
      setCompleted(true);
      
      // 完成后，分析输出中的标记出现次数
      setTimeout(() => {
        if (stdout) {
          const output = stdout.write('');  // 获取当前输出
          
          // 统计标记出现次数（这只是示意，实际无法获取终端输出）
          process.stderr.write('\n\n========== 测试完成 ==========\n');
          process.stderr.write('请手动验证：\n');
          process.stderr.write('1. 向上滚动查看完整输出\n');
          process.stderr.write('2. 搜索 "UNIQUE_MARKER_START_001" 应该只出现 1 次\n');
          process.stderr.write('3. 搜索 "UNIQUE_MARKER_END_999" 应该只出现 1 次\n');
          process.stderr.write('4. 如果出现 2 次，说明有重复渲染bug\n');
          process.stderr.write('==============================\n\n');
        }
      }, 1000);
    }
  }, [charIndex, fullContent, completed, stdout]);
  
  const lineCount = messages[messages.length - 1]?.content?.split('\n').length || 0;
  const hasSplit = lineCount > 50;
  
  return (
    <Box flexDirection="column">
      <Box marginBottom={1}>
        <Text>
          {completed ? '✅ 测试完成' : '⏳ 测试中...'} | 
          当前行数: <Text bold color="cyan">{lineCount}</Text> | 
          拆分状态: <Text bold color={hasSplit ? "green" : "yellow"}>{hasSplit ? "已拆分" : "未拆分"}</Text>
        </Text>
      </Box>
      
      {completed && (
        <Box marginBottom={1} paddingX={2} borderStyle="double" borderColor="green">
          <Text>
            <Text bold color="green">✅ 流式输出完成！</Text>{'\n'}
            {'\n'}
            <Text bold>验证方法：</Text>{'\n'}
            1. 向上滚动查看完整输出{'\n'}
            2. 使用 Cmd+F (Mac) 或 Ctrl+F (Windows) 搜索{'\n'}
            {'\n'}
            <Text bold color="cyan">搜索关键词：</Text>{'\n'}
            • "UNIQUE_MARKER_START_001" - 应该只有 <Text bold color="green">1 次</Text>{'\n'}
            • "UNIQUE_MARKER_END_999" - 应该只有 <Text bold color="green">1 次</Text>{'\n'}
            {'\n'}
            <Text bold color="red">如果出现 2 次，说明有重复bug！</Text>
          </Text>
        </Box>
      )}
      
      <MessageList messages={messages} />
    </Box>
  );
};

render(<App />);
