#!/usr/bin/env node
/**
 * Markdown Split Demo
 * 
 * 演示 MessageList 组件的 Markdown 拆分功能
 * 模拟一个长消息的流式输出过程，观察拆分效果
 * 
 * 运行方式:
 * npx tsx examples/demo-markdown-split.tsx
 * 或
 * npm run demo:split
 */

import React, { useState, useEffect } from 'react';
import { render, Box, Text } from '@jrichman/ink';
import { MessageList } from '../src/components/Chat/MessageList.js';
import { Message } from '../src/types/index.js';

// 生成长文本内容（包含 Markdown 格式）- 增强版，生成更多内容
const generateLongMarkdownContent = (lineCount: number): string => {
  const sections = [];
  
  sections.push('# Markdown 拆分功能测试文档\n\n');
  sections.push('这是一份自动生成的超长技术文档，用于测试 Markdown 拆分功能的性能和正确性。\n\n');
  sections.push('本文档将包含多个段落、代码块、列表等 Markdown 元素，总行数将超过 ' + lineCount + ' 行。\n\n');
  
  let currentLines = 6;
  let sectionNum = 1;
  
  while (currentLines < lineCount) {
    // 添加主标题和详细段落
    sections.push(`## ${sectionNum}. 第 ${sectionNum} 部分：核心功能说明\n\n`);
    sections.push(`### ${sectionNum}.1 功能概述\n\n`);
    sections.push(`这是第 ${sectionNum} 部分的详细内容。本节将深入探讨 Markdown 拆分功能的核心特性。`);
    sections.push(`拆分功能的设计目标是在保证 Markdown 格式完整性的前提下，提升超长文本的渲染性能。\n\n`);
    sections.push(`在实际使用中，当消息内容超过 50 行时，系统会自动触发智能拆分机制。`);
    sections.push(`拆分点会选择在段落边界或换行符处，确保不会破坏代码块、列表等结构化内容。\n\n`);
    currentLines += 10;
    
    // 添加特性列表
    if (currentLines < lineCount - 20) {
      sections.push(`### ${sectionNum}.2 核心特性详解\n\n`);
      sections.push('拆分功能包含以下核心特性：\n\n');
      sections.push(`1. **智能拆分算法**\n`);
      sections.push(`   - 自动检测消息长度（阈值：50 行）\n`);
      sections.push(`   - 在安全的位置进行拆分（段落边界、换行符）\n`);
      sections.push(`   - 保护代码块、列表等结构完整性\n\n`);
      sections.push(`2. **Markdown 格式保护**\n`);
      sections.push(`   - 不在代码块内拆分\n`);
      sections.push(`   - 优先选择段落边界（\\n\\n）\n`);
      sections.push(`   - 次优选择单换行符（\\n）\n\n`);
      sections.push(`3. **无缝拼接技术**\n`);
      sections.push(`   - 拆分片段之间无多余空行\n`);
      sections.push(`   - 视觉上完全一致\n`);
      sections.push(`   - Agent 图标只显示一次\n\n`);
      sections.push(`4. **性能优化**\n`);
      sections.push(`   - 已完成片段加入 Static 区域（锁定）\n`);
      sections.push(`   - 只有最后片段在动态更新\n`);
      sections.push(`   - 性能提升最高可达 50x\n\n`);
      currentLines += 22;
    }
    
    // 添加代码示例
    if (currentLines < lineCount - 30) {
      sections.push(`### ${sectionNum}.3 代码实现示例\n\n`);
      sections.push('以下是拆分功能的核心代码实现：\n\n');
      sections.push('```typescript\n');
      sections.push(`// 拆分逻辑实现 - 第 ${sectionNum} 部分\n`);
      sections.push('interface SplitResult {\n');
      sections.push('  completed: string;\n');
      sections.push('  pending: string;\n');
      sections.push('  splitPoint: number;\n');
      sections.push('}\n\n');
      sections.push(`function splitContent${sectionNum}(content: string): SplitResult {\n`);
      sections.push('  const threshold = 50;\n');
      sections.push('  const lines = content.split("\\n");\n');
      sections.push('  \n');
      sections.push('  if (lines.length <= threshold) {\n');
      sections.push('    return { completed: "", pending: content, splitPoint: 0 };\n');
      sections.push('  }\n');
      sections.push('  \n');
      sections.push('  const splitPoint = findLastSafeSplitPoint(content);\n');
      sections.push('  return {\n');
      sections.push('    completed: content.substring(0, splitPoint),\n');
      sections.push('    pending: content.substring(splitPoint),\n');
      sections.push('    splitPoint\n');
      sections.push('  };\n');
      sections.push('}\n');
      sections.push('```\n\n');
      currentLines += 26;
    }
    
    // 添加性能分析
    if (currentLines < lineCount - 25) {
      sections.push(`### ${sectionNum}.4 性能分析与对比\n\n`);
      sections.push('拆分前后的性能对比数据：\n\n');
      sections.push('| 消息长度 | 拆分前（重渲染行数） | 拆分后（重渲染行数） | 性能提升 |\n');
      sections.push('|---------|---------------------|---------------------|----------|\n');
      sections.push('| 50 行   | 50 行               | 10 行               | **5x**   |\n');
      sections.push('| 100 行  | 100 行              | 10 行               | **10x**  |\n');
      sections.push('| 200 行  | 200 行              | 10 行               | **20x**  |\n');
      sections.push('| 500 行  | 500 行              | 10 行               | **50x**  |\n\n');
      sections.push('从以上数据可以看出，拆分功能对长消息的性能优化效果显著。\n\n');
      currentLines += 12;
    }
    
    // 添加使用场景
    if (currentLines < lineCount - 20) {
      sections.push(`### ${sectionNum}.5 典型使用场景\n\n`);
      sections.push('拆分功能特别适用于以下场景：\n\n');
      sections.push('- **技术文档生成**：生成超长的技术说明文档\n');
      sections.push('- **代码解释**：包含大量代码示例的解释说明\n');
      sections.push('- **教程内容**：详细的步骤说明和教程\n');
      sections.push('- **分析报告**：包含多个部分的分析报告\n');
      sections.push('- **API 文档**：完整的 API 参考文档\n\n');
      currentLines += 9;
    }
    
    // 添加总结段落
    sections.push(`### ${sectionNum}.6 小结\n\n`);
    sections.push(`第 ${sectionNum} 部分的内容到此结束。我们介绍了拆分功能的核心特性、代码实现、`);
    sections.push(`性能分析以及典型使用场景。在下一部分中，我们将继续深入探讨更多细节。\n\n`);
    sections.push('---\n\n');
    currentLines += 6;
    
    sectionNum++;
    
    if (currentLines >= lineCount) break;
  }
  
  // 添加结尾
  sections.push('## 文档总结\n\n');
  sections.push('本文档通过大量示例和详细说明，全面展示了 Markdown 拆分功能的实现和效果。\n\n');
  sections.push('**关键要点：**\n\n');
  sections.push('1. 拆分阈值为 50 行\n');
  sections.push('2. 在安全位置拆分（段落边界）\n');
  sections.push('3. 保护 Markdown 格式完整性\n');
  sections.push('4. 性能提升显著（最高 50x）\n\n');
  sections.push('感谢您阅读本文档！🎉\n');
  
  return sections.join('');
};

// Demo 组件
const MarkdownSplitDemo: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streamingContent, setStreamingContent] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [phase, setPhase] = useState<'idle' | 'user' | 'streaming' | 'complete'>('idle');
  
  // 模拟用户输入
  useEffect(() => {
    const timer1 = setTimeout(() => {
      setPhase('user');
      setMessages([{
        id: 'msg_1',
        type: 'user',
        content: '请生成一份包含 100 行的技术文档。',
        timestamp: new Date().toISOString(),
        author: 'user'
      }]);
    }, 1000);
    
    return () => clearTimeout(timer1);
  }, []);
  
  // 模拟 Agent 开始响应
  useEffect(() => {
    if (phase !== 'user') return;
    
    const timer2 = setTimeout(() => {
      setPhase('streaming');
      setIsStreaming(true);
    }, 1500);
    
    return () => clearTimeout(timer2);
  }, [phase]);
  
  // 模拟流式输出
  useEffect(() => {
    if (!isStreaming) return;
    
    const fullContent = generateLongMarkdownContent(100);
    let currentIndex = 0;
    
    const interval = setInterval(() => {
      if (currentIndex >= fullContent.length) {
        clearInterval(interval);
        setIsStreaming(false);
        setPhase('complete');
        
        // 流式完成后，将内容添加到消息列表
        setMessages(prev => [...prev, {
          id: 'msg_2',
          type: 'agent',
          content: fullContent,
          timestamp: new Date().toISOString(),
          author: 'agent',
          metadata: {
            subtype: 'answer'
          }
        }]);
        setStreamingContent('');
        return;
      }
      
      // 每次添加一小段内容（模拟流式输出）
      const chunkSize = Math.floor(Math.random() * 50) + 30;
      const nextContent = fullContent.substring(0, Math.min(currentIndex + chunkSize, fullContent.length));
      currentIndex += chunkSize;
      
      setStreamingContent(nextContent);
      
      // 更新消息列表（模拟 pending message）
      setMessages(prev => {
        const withoutLast = prev.filter(m => m.id !== 'msg_2_pending');
        return [...withoutLast, {
          id: 'msg_2_pending',
          type: 'agent',
          content: nextContent,
          timestamp: new Date().toISOString(),
          author: 'agent',
          metadata: {
            subtype: 'answer'
          }
        }];
      });
    }, 100); // 每 100ms 更新一次
    
    return () => clearInterval(interval);
  }, [isStreaming]);
  
  // 计算当前行数
  const currentLines = streamingContent.split('\n').length;
  const shouldSplit = currentLines > 50; // MESSAGE_SPLIT_THRESHOLD
  
  return (
    <MessageList
      messages={messages}
      headerProps={{
        version: '1.0.0-demo',
        workingDir: '/demo',
        agent: 'Siada',
        provider: 'Demo',
        model: 'test-model'
      }}
      isCollapsed={false}
    />
  );
};

// 渲染应用
console.log('\n🚀 启动 Markdown 拆分测试 Demo...\n');

const { unmount, waitUntilExit } = render(<MarkdownSplitDemo />);

// 优雅退出
process.on('SIGINT', () => {
  unmount();
  console.log('\n\n✓ Demo 已停止\n');
  process.exit(0);
});

waitUntilExit().catch((error) => {
  console.error('Demo 错误:', error);
  process.exit(1);
});
