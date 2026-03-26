#!/usr/bin/env node
/**
 * Markdown Split Simple Demo
 * 
 * 简化版的 Markdown 拆分测试 Demo
 * 直接显示拆分前后的对比效果
 * 
 * 运行方式:
 * npx tsx examples/demo-markdown-split-simple.tsx
 */

import React, { useState, useEffect } from 'react';
import { render, Box, Text } from '@jrichman/ink';
import { MessageList } from '../src/components/Chat/MessageList.js';
import { Message } from '../src/types/index.js';

// 生成测试用长文本 - 增强版，生成更详细的内容
const generateTestContent = (targetLines: number): string => {
  const lines: string[] = [];
  
  lines.push('# Markdown 拆分测试文档\n\n');
  lines.push('本文档用于测试 MessageList 的拆分功能。目标行数：' + targetLines + ' 行。\n\n');
  lines.push('拆分功能会在内容达到 50 行时自动触发，将内容分为 Static 和 Pending 两部分。\n\n');
  
  let currentLines = 6;
  let sectionNum = 1;
  
  while (currentLines < targetLines) {
    lines.push(`## ${sectionNum}. 第 ${sectionNum} 部分\n\n`);
    lines.push(`### ${sectionNum}.1 内容说明\n\n`);
    lines.push(`这是第 ${sectionNum} 部分的详细内容。当内容超过 50 行时，会触发智能拆分。\n`);
    lines.push(`拆分会在段落边界（双换行符）或单换行符处进行，确保 Markdown 格式完整。\n\n`);
    lines.push(`拆分后的效果：\n`);
    lines.push(`- 前面的内容移入 Static 区域，不再重新渲染\n`);
    lines.push(`- 后面的内容保持在 Pending 区域，继续动态更新\n`);
    lines.push(`- 视觉上无缝拼接，不会有多余的空行\n\n`);
    currentLines += 12;
    
    // 添加代码块
    if (currentLines < targetLines - 15) {
      lines.push(`### ${sectionNum}.2 代码示例\n\n`);
      lines.push('```typescript\n');
      lines.push(`// 第 ${sectionNum} 部分的示例代码\n`);
      lines.push('interface MessageSplit {\n');
      lines.push('  beforeText: string;  // 移入 Static 的部分\n');
      lines.push('  afterText: string;   // 保留在 Pending 的部分\n');
      lines.push('  splitPoint: number;  // 拆分点位置\n');
      lines.push('}\n\n');
      lines.push(`function splitAt${sectionNum}(content: string): MessageSplit {\n`);
      lines.push('  const threshold = 50;\n');
      lines.push('  const splitPoint = findLastSafeSplitPoint(content);\n');
      lines.push('  return {\n');
      lines.push('    beforeText: content.substring(0, splitPoint),\n');
      lines.push('    afterText: content.substring(splitPoint),\n');
      lines.push('    splitPoint\n');
      lines.push('  };\n');
      lines.push('}\n');
      lines.push('```\n\n');
      currentLines += 20;
    }
    
    // 添加特性列表
    if (currentLines < targetLines - 10) {
      lines.push(`### ${sectionNum}.3 关键特性\n\n`);
      lines.push('1. **智能拆分**：自动检测长度并在安全位置拆分\n');
      lines.push('2. **格式保护**：不会破坏代码块和 Markdown 结构\n');
      lines.push('3. **无缝拼接**：拆分片段之间视觉上完全连续\n');
      lines.push('4. **性能优化**：减少重渲染次数，提升流畅度\n\n');
      currentLines += 7;
    }
    
    // 添加表格
    if (currentLines < targetLines - 12 && sectionNum % 2 === 0) {
      lines.push(`### ${sectionNum}.4 性能对比\n\n`);
      lines.push('| 场景 | 拆分前 | 拆分后 | 提升 |\n');
      lines.push('|------|--------|--------|------|\n');
      lines.push('| 50行 | 50行重渲染 | 10行重渲染 | 5x |\n');
      lines.push('| 100行 | 100行重渲染 | 10行重渲染 | 10x |\n');
      lines.push('| 200行 | 200行重渲染 | 10行重渲染 | 20x |\n\n');
      currentLines += 8;
    }
    
    // 添加总结
    lines.push(`### ${sectionNum}.5 小结\n\n`);
    lines.push(`第 ${sectionNum} 部分介绍了拆分功能的核心概念和实现方式。`);
    lines.push(`通过智能拆分，我们可以显著提升长消息的渲染性能。\n\n`);
    lines.push('---\n\n');
    currentLines += 6;
    
    sectionNum++;
  }
  
  // 添加文档结尾
  lines.push('## 文档总结\n\n');
  lines.push('本测试文档包含了 ' + targetLines + ' 行左右的内容，用于验证拆分功能。\n\n');
  lines.push('**观察要点：**\n');
  lines.push('- 行数达到 50 时应该触发拆分\n');
  lines.push('- 拆分后无闪烁现象\n');
  lines.push('- Agent 图标只显示一次\n');
  lines.push('- 片段之间无多余空行\n\n');
  lines.push('测试完成！✅\n');
  
  return lines.join('');
};

// 测试场景
interface TestScenario {
  name: string;
  description: string;
  messages: Message[];
  lineCount: number;
  shouldSplit: boolean;
}

const scenarios: TestScenario[] = [
  {
    name: '场景 1: 短消息',
    description: '30 行内容，不触发拆分',
    lineCount: 30,
    shouldSplit: false,
    messages: []
  },
  {
    name: '场景 2: 临界消息',
    description: '50 行内容，刚好达到阈值',
    lineCount: 50,
    shouldSplit: false,
    messages: []
  },
  {
    name: '场景 3: 长消息',
    description: '80 行内容，触发拆分',
    lineCount: 80,
    shouldSplit: true,
    messages: []
  },
  {
    name: '场景 4: 超长消息',
    description: '150 行内容，明显拆分',
    lineCount: 150,
    shouldSplit: true,
    messages: []
  }
];

// 初始化场景消息 - 使用新的内容生成函数
scenarios.forEach(scenario => {
  const content = generateTestContent(scenario.lineCount);
  
  scenario.messages = [
    {
      id: `msg_user_${scenario.lineCount}`,
      type: 'user',
      content: `请生成约 ${scenario.lineCount} 行的技术文档，包含多个部分、代码示例和详细说明。`,
      timestamp: new Date().toISOString(),
      author: 'user'
    },
    {
      id: `msg_agent_${scenario.lineCount}`,
      type: 'agent',
      content: content,
      timestamp: new Date().toISOString(),
      author: 'agent',
      metadata: {
        subtype: 'answer'
      }
    }
  ];
});

// Demo 组件
const SimpleSplitDemo: React.FC = () => {
  const [currentScenario, setCurrentScenario] = useState(0);
  const [autoPlay, setAutoPlay] = useState(true);
  
  const scenario = scenarios[currentScenario];
  const actualLines = scenario.messages[1]?.content.split('\n').length || 0;
  
  // 自动切换场景
  useEffect(() => {
    if (!autoPlay) return;
    
    const timer = setTimeout(() => {
      if (currentScenario < scenarios.length - 1) {
        setCurrentScenario(prev => prev + 1);
      } else {
        setAutoPlay(false);
      }
    }, 5000); // 每个场景显示 5 秒
    
    return () => clearTimeout(timer);
  }, [currentScenario, autoPlay]);
  
  return (
    <MessageList
      messages={scenario.messages}
      headerProps={{
        version: '1.0.0-demo',
        workingDir: '/demo',
        agent: 'Siada',
        provider: 'Test',
        model: 'demo-model'
      }}
      isCollapsed={false}
    />
  );
};

// 启动信息
console.log('\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
console.log('🚀 Markdown 拆分测试 Demo (简化版)');
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
console.log('');
console.log('📋 测试场景:');
scenarios.forEach((s, i) => {
  console.log(`   ${i + 1}. ${s.name} - ${s.description}`);
});
console.log('');
console.log('⏱️  每个场景自动演示 5 秒');
console.log('🔍 观察点: 拆分阈值 50 行，触发后观察片段分离');
console.log('');

// 渲染应用
const { unmount, waitUntilExit } = render(<SimpleSplitDemo />);

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
