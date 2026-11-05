# Siada CLI UI Examples

这个目录包含了各种示例，演示如何使用 Ink 组件库和 Siada CLI UI 的功能。

## 快速开始

```bash
# 查看所有可用的示例
npm run | grep example

# 运行简单静态横幅
npm run example:simple

# 运行带渐变色的横幅
npm run example:gradient

# 运行完整演示（带动态更新）
npm run example:demo

# 测试完整布局
npm run example:layout
```

## 静态横幅示例

### 1. 简单静态横幅 (`simple-static-banner.tsx`)

最基础的示例，展示如何使用 Ink 的 `Static` 组件渲染 ASCII 艺术横幅。

**特性：**
- 使用 `Static` 组件，只渲染一次
- 每行使用单一颜色
- 简单易懂的代码结构

**运行：**
```bash
# 方式 1：直接运行
npx tsx examples/simple-static-banner.tsx

# 方式 2：使用 npm 脚本
npm run example:simple
```

### 2. 渐变静态横幅 (`gradient-static-banner.tsx`)

增强版本，展示带有渐变色效果的 ASCII 艺术横幅。

**特性：**
- 使用 `Static` 组件优化性能
- 从左到右的渐变色效果（蓝色 → 青色 → 绿色）
- 每个字符根据位置应用不同颜色
- 包含装饰性边框

**运行：**
```bash
# 方式 1：直接运行
npx tsx examples/gradient-static-banner.tsx

# 方式 2：使用 npm 脚本
npm run example:gradient
```

### 3. 动态内容演示 (`static-banner-demo.tsx`)

完整的演示应用，展示静态横幅与动态内容的结合。

**特性：**
- 静态横幅（使用 `Static` 组件）
- 动态更新的内容区域
- 展示 `Static` 组件的性能优势
- 每 2 秒更新一次计数器和消息列表

**运行：**
```bash
# 方式 1：直接运行
npx tsx examples/static-banner-demo.tsx

# 方式 2：使用 npm 脚本
npm run example:demo
```

按 `Ctrl+C` 退出演示。

### 4. 布局测试 (`test-layout.tsx`)

测试完整的 MainLayout 组件，包括消息列表和交互功能。

**运行：**
```bash
# 方式 1：直接运行
npx tsx examples/test-layout.tsx

# 方式 2：使用 npm 脚本
npm run example:layout
```

## Ink Static 组件说明

`Static` 组件是 Ink 提供的一个特殊组件，用于渲染不需要更新的内容：

```tsx
import { Static } from '@jrichman/ink';

<Static items={arrayOfItems}>
  {(item, index) => (
    <Box key={index}>
      {/* 渲染每个项目 */}
    </Box>
  )}
</Static>
```

**优势：**
1. **性能优化**：只渲染一次，不会随着父组件更新而重新渲染
2. **内存效率**：适合渲染大量静态内容（如历史消息、横幅等）
3. **避免闪烁**：防止静态内容在更新时产生闪烁效果

**适用场景：**
- ASCII 艺术横幅
- 应用标题和版本信息
- 历史消息列表
- 帮助文档和说明文本

## 代码结构

所有示例都遵循以下结构：

```tsx
// 1. 导入依赖
import React from 'react';
import { render, Box, Text, Static } from '@jrichman/ink';

// 2. 定义数据（横幅内容、颜色等）
const bannerLines = [...];
const lineColors = [...];

// 3. 创建组件
const MyComponent: React.FC = () => {
  return (
    <Box>
      <Static items={bannerLines}>
        {(line, index) => (
          // 渲染逻辑
        )}
      </Static>
    </Box>
  );
};

// 4. 渲染应用
render(<MyComponent />);
```

## 技术要点

### 渐变色实现

```tsx
// 计算从左到右的渐变比例
const ratio = charIndex / (chars.length - 1);

// 根据比例选择颜色索引
const colorIndex = Math.floor(ratio * (lineColors.length - 1));

// 应用颜色
<Text color={lineColors[colorIndex]}>{char}</Text>
```

### Static vs 普通渲染

| 特性 | Static 组件 | 普通组件 |
|------|------------|---------|
| 渲染次数 | 只渲染一次 | 每次更新都渲染 |
| 性能 | 高效 | 可能影响性能 |
| 适用场景 | 静态内容 | 动态内容 |
| 内存占用 | 低 | 相对较高 |

## 相关文档

- [Ink 官方文档](https://github.com/vadimdemedes/ink)
- [React 文档](https://react.dev/)
- [Siada CLI 主项目](../README.md)

## 贡献

欢迎提交新的示例！请确保：
1. 代码清晰，有适当的注释
2. 包含使用说明
3. 遵循现有的代码风格
