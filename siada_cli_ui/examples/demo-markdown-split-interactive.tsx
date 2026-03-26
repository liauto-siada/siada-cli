#!/usr/bin/env node
/**
 * Markdown Split Interactive Demo
 * 
 * 交互式 Markdown 拆分测试 Demo
 * 使用键盘控制流式输出速度，实时观察拆分过程
 * 
 * 运行方式:
 * npx tsx examples/demo-markdown-split-interactive.tsx
 * 
 * 操作说明:
 * - Space: 暂停/继续流式输出
 * - Arrow Up/Down: 调整输出速度
 * - R: 重新开始
 * - Q: 退出
 */

import React, { useState, useEffect } from 'react';
import { render, Box, Text, useInput } from '@jrichman/ink';
import { MessageList } from '../src/components/Chat/MessageList.js';
import { Message } from '../src/types/index.js';

// 生成测试内容 - 增强版，生成更长更详细的内容
const generateContent = (): string[] => {
  const chunks: string[] = [];
  
  chunks.push('# 🧪 Markdown 拆分实时测试文档\n\n');
  chunks.push('这是一份自动生成的超长测试文档，用于实时演示拆分功能。\n\n');
  chunks.push('**测试目标：** 观察内容达到 50 行时的自动拆分效果。\n\n');
  
  for (let i = 1; i <= 20; i++) {
    chunks.push(`## ${i}. 第 ${i} 部分：功能详解\n\n`);
    chunks.push(`### ${i}.1 核心说明\n\n`);
    chunks.push(`这是第 ${i} 部分的详细内容。当内容累积超过 50 行时，系统会自动触发智能拆分机制。\n`);
    chunks.push(`拆分会在 Markdown 安全的位置进行（段落边界或换行符），确保不会破坏代码块等结构化内容。\n\n`);
    chunks.push(`**拆分后的效果：**\n\n`);
    chunks.push(`- 已完成的内容移入 Static 区域，锁定不再重新渲染\n`);
    chunks.push(`- 正在输出的内容保持在 Pending 区域，动态更新\n`);
    chunks.push(`- 视觉上无缝拼接，不会有多余的空行\n`);
    chunks.push(`- Agent 图标只在第一个片段显示一次\n\n`);
    
    if (i % 3 === 0) {
      chunks.push(`### ${i}.2 代码实现\n\n`);
      chunks.push('拆分功能的核心代码实现：\n\n');
      chunks.push('```typescript\n');
      chunks.push(`// 第 ${i} 部分 - 拆分逻辑\n`);
      chunks.push('interface SplitConfig {\n');
      chunks.push('  threshold: number;      // 拆分阈值（行数）\n');
      chunks.push('  minPending: number;     // 最小 pending 行数\n');
      chunks.push('  protectCodeBlock: boolean;  // 保护代码块\n');
      chunks.push('}\n\n');
      chunks.push(`const config${i}: SplitConfig = {\n`);
      chunks.push('  threshold: 50,\n');
      chunks.push('  minPending: 10,\n');
      chunks.push('  protectCodeBlock: true\n');
      chunks.push('};\n\n');
      chunks.push(`function performSplit${i}(content: string) {\n`);
      chunks.push('  const lines = content.split("\\n");\n');
      chunks.push(`  if (lines.length <= config${i}.threshold) {\n`);
      chunks.push('    return { static: "", pending: content };\n');
      chunks.push('  }\n');
      chunks.push('  const splitPoint = findLastSafeSplitPoint(content);\n');
      chunks.push('  return {\n');
      chunks.push('    static: content.substring(0, splitPoint),\n');
      chunks.push('    pending: content.substring(splitPoint)\n');
      chunks.push('  };\n');
      chunks.push('}\n');
      chunks.push('```\n\n');
    }
    
    if (i % 2 === 0) {
      chunks.push(`### ${i}.3 特性详解\n\n`);
      chunks.push('拆分功能的核心特性包括：\n\n');
      chunks.push('1. **智能检测**\n');
      chunks.push('   - 自动监控消息长度\n');
      chunks.push('   - 达到阈值即触发拆分\n\n');
      chunks.push('2. **格式保护**\n');
      chunks.push('   - 不在代码块内拆分\n');
      chunks.push('   - 优先选择段落边界\n\n');
      chunks.push('3. **无缝拼接**\n');
      chunks.push('   - 精确控制边距\n');
      chunks.push('   - 视觉完全连续\n\n');
      chunks.push('4. **性能优化**\n');
      chunks.push('   - Static 区域锁定\n');
      chunks.push('   - 减少重渲染\n\n');
    }
    
    if (i % 4 === 0) {
      chunks.push(`### ${i}.4 性能数据\n\n`);
      chunks.push('拆分前后的性能对比：\n\n');
      chunks.push('| 消息长度 | 拆分前 | 拆分后 | 提升倍数 |\n');
      chunks.push('|---------|--------|--------|----------|\n');
      chunks.push('| 50 行   | 50 行重渲染 | 10 行重渲染 | 5x |\n');
      chunks.push('| 100 行  | 100 行重渲染 | 10 行重渲染 | 10x |\n');
      chunks.push('| 200 行  | 200 行重渲染 | 10 行重渲染 | 20x |\n');
      chunks.push('| 500 行  | 500 行重渲染 | 10 行重渲染 | 50x |\n\n');
      chunks.push('从数据可以看出，消息越长，性能提升越明显。\n\n');
    }
    
    chunks.push(`### ${i}.5 小结\n\n`);
    chunks.push(`第 ${i} 部分介绍了拆分功能的实现细节和性能优化效果。`);
    chunks.push(`通过智能拆分，我们能够显著提升长消息的渲染性能和用户体验。\n\n`);
    chunks.push('---\n\n');
  }
  
  chunks.push('## 📊 测试总结\n\n');
  chunks.push('本文档包含了大量的技术说明、代码示例和性能数据，总行数远超 150 行。\n\n');
  chunks.push('**关键观察点：**\n\n');
  chunks.push('1. 行数达到 50 时，状态从绿色变为红色\n');
  chunks.push('2. 拆分后，前面的内容不再闪烁\n');
  chunks.push('3. 只有最后的 Pending 部分在更新\n');
  chunks.push('4. Agent 图标只显示一次\n');
  chunks.push('5. 片段之间完全无缝\n\n');
  chunks.push('测试完成！感谢您的耐心观察。🎉\n');
  
  return chunks;
};

// 速度配置
const SPEEDS = [
  { name: '慢速', delay: 300, label: '🐢' },
  { name: '正常', delay: 150, label: '🚶' },
  { name: '快速', delay: 50, label: '🏃' },
  { name: '极速', delay: 10, label: '🚀' }
];

// Interactive Demo 组件
const InteractiveSplitDemo: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'msg_user_1',
      type: 'user',
      content: '请生成一份长文档，观察拆分过程。',
      timestamp: new Date().toISOString(),
      author: 'user'
    }
  ]);
  
  const [contentChunks] = useState(() => generateContent());
  const [currentChunkIndex, setCurrentChunkIndex] = useState(0);
  const [currentContent, setCurrentContent] = useState('');
  const [isPaused, setIsPaused] = useState(false);
  const [speedIndex, setSpeedIndex] = useState(1); // 默认正常速度
  const [isComplete, setIsComplete] = useState(false);
  
  const currentLines = currentContent.split('\n').length;
  const hasSplit = currentLines > 50;
  const speed = SPEEDS[speedIndex];
  
  // 键盘控制
  useInput((input, key) => {
    if (input === 'q' || input === 'Q') {
      process.exit(0);
    }
    
    if (input === ' ') {
      setIsPaused(prev => !prev);
    }
    
    if (key.upArrow && speedIndex < SPEEDS.length - 1) {
      setSpeedIndex(prev => prev + 1);
    }
    
    if (key.downArrow && speedIndex > 0) {
      setSpeedIndex(prev => prev - 1);
    }
    
    if (input === 'r' || input === 'R') {
      // 重新开始
      setCurrentChunkIndex(0);
      setCurrentContent('');
      setIsComplete(false);
      setIsPaused(false);
      setMessages([{
        id: 'msg_user_1',
        type: 'user',
        content: '请生成一份长文档，观察拆分过程。',
        timestamp: new Date().toISOString(),
        author: 'user'
      }]);
    }
  });
  
  // 流式输出
  useEffect(() => {
    if (isPaused || isComplete) return;
    if (currentChunkIndex >= contentChunks.length) {
      setIsComplete(true);
      
      // 完成后添加到消息列表
      setMessages(prev => {
        const withoutPending = prev.filter(m => m.id !== 'msg_agent_pending');
        return [...withoutPending, {
          id: 'msg_agent_final',
          type: 'agent',
          content: currentContent,
          timestamp: new Date().toISOString(),
          author: 'agent',
          metadata: {
            subtype: 'answer'
          }
        }];
      });
      return;
    }
    
    const timer = setTimeout(() => {
      const newContent = currentContent + contentChunks[currentChunkIndex];
      setCurrentContent(newContent);
      setCurrentChunkIndex(prev => prev + 1);
      
      // 更新 pending 消息
      setMessages(prev => {
        const withoutPending = prev.filter(m => m.id !== 'msg_agent_pending');
        return [...withoutPending, {
          id: 'msg_agent_pending',
          type: 'agent',
          content: newContent,
          timestamp: new Date().toISOString(),
          author: 'agent',
          metadata: {
            subtype: 'answer'
          }
        }];
      });
    }, speed.delay);
    
    return () => clearTimeout(timer);
  }, [currentChunkIndex, currentContent, contentChunks, isPaused, isComplete, speed.delay]);
  
  const progress = Math.round((currentChunkIndex / contentChunks.length) * 100);
  
  return (
    <MessageList
      messages={messages}
      headerProps={{
        version: '1.0.0-interactive',
        workingDir: '/demo',
        agent: 'Siada',
        provider: 'Interactive',
        model: 'test-model'
      }}
      isCollapsed={false}
    />
  );
};

// 启动信息
console.clear();
console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
console.log('🎮 Markdown 拆分交互式测试 Demo');
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
console.log('');
console.log('🎯 测试目标:');
console.log('   • 观察内容达到 50 行时的自动拆分');
console.log('   • 验证拆分片段的无缝拼接');
console.log('   • 检查 Agent 图标只显示一次');
console.log('   • 确认 Markdown 格式完整性');
console.log('');
console.log('⌨️  操作说明:');
console.log('   Space      - 暂停/继续流式输出');
console.log('   ↑/↓        - 调整输出速度（慢速/正常/快速/极速）');
console.log('   R          - 重新开始测试');
console.log('   Q          - 退出程序');
console.log('');
console.log('🚀 启动中...\n');

// 渲染应用
const { unmount, waitUntilExit } = render(<InteractiveSplitDemo />);

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
