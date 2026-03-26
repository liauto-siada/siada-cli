#!/usr/bin/env node
import React, { useState, useEffect, useRef } from 'react';
import { render, Box, Text } from 'ink';
import { MessageList } from '../src/components/Chat/MessageList.js';
import type { Message } from '../src/types/index.js';

// 生成带唯一标记的测试内容 - 总共4行
function generateUniqueContent(): string {
  const lines: string[] = [];
  lines.push('# START_MARKER_AAAA');  // 第1行
  lines.push('Content line 2');        // 第2行
  lines.push('Content line 3');        // 第3行
  lines.push('# END_MARKER_ZZZZ');     // 第4行
  
  return lines.join('\n');
}

const App: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'user-1',
      role: 'user',
      content: '测试',
      timestamp: Date.now(),
    }
  ]);
  
  const [charIndex, setCharIndex] = useState(0);
  const [completed, setCompleted] = useState(false);
  const [testResult, setTestResult] = useState<{
    startCount: number;
    endCount: number;
    passed: boolean;
  } | null>(null);
  
  const fullContent = generateUniqueContent();
  const messageListRef = useRef<any>(null);
  
  useEffect(() => {
    if (charIndex < fullContent.length) {
      const timer = setTimeout(() => {
        const currentContent = fullContent.substring(0, charIndex + 5);
        
        setMessages([
          {
            id: 'user-1',
            role: 'user',
            content: '测试',
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
        
        setCharIndex(charIndex + 5);
      }, 100);
      
      return () => clearTimeout(timer);
    } else if (!completed) {
      setCompleted(true);
      
      // 完成后检测最终内容
      setTimeout(() => {
        const finalMessage = messages[messages.length - 1];
        if (finalMessage && finalMessage.content) {
          const content = finalMessage.content;
          const startCount = (content.match(/START_MARKER_AAAA/g) || []).length;
          const endCount = (content.match(/END_MARKER_ZZZZ/g) || []).length;
          
          setTestResult({
            startCount,
            endCount,
            passed: startCount === 1 && endCount === 1,
          });
          
          process.stderr.write(`\n\n========== 测试结果 ==========\n`);
          process.stderr.write(`START_MARKER 出现次数: ${startCount} (期望: 1)\n`);
          process.stderr.write(`END_MARKER 出现次数: ${endCount} (期望: 1)\n`);
          process.stderr.write(`测试状态: ${startCount === 1 && endCount === 1 ? '✅ PASSED' : '❌ FAILED'}\n`);
          process.stderr.write(`==============================\n\n`);
          
          // 退出
          setTimeout(() => process.exit(startCount === 1 && endCount === 1 ? 0 : 1), 1000);
        }
      }, 500);
    }
  }, [charIndex, fullContent, completed, messages]);
  
  const lineCount = messages[messages.length - 1]?.content?.split('\n').length || 0;
  const hasSplit = lineCount > 2;
  
  return (
    <Box flexDirection="column">
      <Box marginBottom={1}>
        <Text>
          {completed ? '✅ 测试完成' : '⏳ 测试中...'} | 
          行数: <Text bold color="cyan">{lineCount}</Text> | 
          拆分: <Text bold color={hasSplit ? "green" : "yellow"}>{hasSplit ? "是" : "否"}</Text>
        </Text>
      </Box>
      
      {testResult && (
        <Box marginBottom={1} paddingX={2} borderStyle="double" borderColor={testResult.passed ? "green" : "red"}>
          <Text>
            <Text bold color={testResult.passed ? "green" : "red"}>
              {testResult.passed ? "✅ 测试通过" : "❌ 测试失败"}
            </Text>{'\n'}
            {'\n'}
            START_MARKER: {testResult.startCount} 次 (期望: 1){'\n'}
            END_MARKER: {testResult.endCount} 次 (期望: 1){'\n'}
            {'\n'}
            {!testResult.passed && (
              <Text color="red">检测到重复渲染bug！</Text>
            )}
          </Text>
        </Box>
      )}
      
      <MessageList ref={messageListRef} messages={messages} />
    </Box>
  );
};

render(<App />);
