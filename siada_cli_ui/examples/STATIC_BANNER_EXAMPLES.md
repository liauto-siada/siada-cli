# Static Banner Examples - 实现总结

## 概述

本项目包含了三个使用 Ink 的 `Static` 组件渲染 ASCII 艺术横幅的示例，演示了不同层次的实现方式和功能。

## 创建的文件

### 1. `simple-static-banner.tsx` - 简单版本
**目的：** 最基础的 Static 组件使用示例

**特点：**
- 代码简洁，易于理解
- 每行使用单一颜色（基于行索引）
- 适合初学者学习 Static 组件的基本用法

**代码示例：**
```tsx
<Static items={bannerLines}>
  {(line, lineIndex) => {
    const color = lineColors[lineIndex];
    return (
      <Box key={lineIndex}>
        {[...line].map((ch, i) => (
          <Text key={i} color={color}>{ch}</Text>
        ))}
      </Box>
    );
  }}
</Static>
```

### 2. `gradient-static-banner.tsx` - 渐变版本
**目的：** 展示更高级的视觉效果

**特点：**
- 从左到右的渐变色效果
- 每个字符根据其在行中的位置计算颜色
- 包含装饰性边框
- 演示了如何实现平滑的颜色过渡

**渐变算法：**
```tsx
// 计算字符在行中的位置比例 (0 -> 1)
const ratio = charIndex / (chars.length - 1);

// 根据比例映射到颜色索引
const colorIndex = Math.floor(ratio * (lineColors.length - 1));

// 应用对应的颜色
<Text color={lineColors[colorIndex]}>{ch}</Text>
```

### 3. `static-banner-demo.tsx` - 完整演示
**目的：** 展示 Static 组件在真实场景中的优势

**特点：**
- 静态横幅 + 动态内容
- 每 2 秒更新计数器和消息
- 证明 Static 组件的内容不会重新渲染
- 展示了性能优化的实际效果

**架构：**
```
┌─────────────────────────────────┐
│  Static Banner (渲染一次)        │
│  - ASCII 艺术                    │
│  - 渐变色效果                    │
└─────────────────────────────────┘
┌─────────────────────────────────┐
│  Dynamic Content (持续更新)      │
│  - 更新计数器                    │
│  - 消息列表                      │
│  - 时间戳                        │
└─────────────────────────────────┘
```

## 使用的技术

### Ink Static 组件

**什么是 Static？**
- Ink 提供的特殊组件
- 用于渲染"不会改变"的内容
- 即使父组件重新渲染，Static 的内容也不会更新

**为什么使用 Static？**
1. **性能优化：** 减少不必要的重新渲染
2. **防止闪烁：** 静态内容保持稳定
3. **内存效率：** 适合大量静态数据（如历史消息）

**API 使用：**
```tsx
import { Static } from '@jrichman/ink';

<Static items={arrayOfItems}>
  {(item, index) => (
    <Box key={index}>
      {/* 渲染逻辑 */}
    </Box>
  )}
</Static>
```

### 颜色渐变算法

本项目使用了 6 种颜色，从蓝色过渡到绿色：

```javascript
const lineColors = [
  '#5b8cd5', // 蓝色
  '#6BA5E7', // 亮蓝色
  '#79B8FF', // 浅蓝色
  '#7FC9E8', // 青色
  '#85D89D', // 浅青绿色
  '#85E89D', // 浅绿色
];
```

**渐变实现步骤：**
1. 计算字符位置比例：`ratio = charIndex / (totalChars - 1)`
2. 映射到颜色数组：`colorIndex = floor(ratio * (colorsLength - 1))`
3. 应用颜色：`<Text color={lineColors[colorIndex]}>`

## 运行示例

### 方式 1：使用 npm 脚本（推荐）

```bash
# 简单版本
npm run example:simple

# 渐变版本
npm run example:gradient

# 完整演示
npm run example:demo
```

### 方式 2：直接运行

```bash
npx tsx examples/simple-static-banner.tsx
npx tsx examples/gradient-static-banner.tsx
npx tsx examples/static-banner-demo.tsx
```

## 学习路径

### 第一步：理解基础
从 `simple-static-banner.tsx` 开始：
- 学习 Static 组件的基本用法
- 理解如何渲染 ASCII 艺术
- 掌握 Ink 的 Box 和 Text 组件

### 第二步：进阶效果
学习 `gradient-static-banner.tsx`：
- 实现颜色渐变算法
- 处理字符级别的样式
- 添加装饰性元素

### 第三步：实际应用
研究 `static-banner-demo.tsx`：
- 结合静态和动态内容
- 理解性能优化
- 构建完整的应用

## 性能对比

### 使用 Static 组件
```
初始渲染：横幅 + 内容
后续更新：仅内容区域重新渲染
横幅区域：保持不变 ✓
```

### 不使用 Static 组件
```
初始渲染：横幅 + 内容
后续更新：横幅 + 内容都重新渲染
横幅区域：每次都重新渲染 ✗
```

**结论：** 使用 Static 组件可以显著减少不必要的渲染，提高性能，特别是在处理大量静态内容时。

## 最佳实践

1. **适用场景识别**
   - ✓ 横幅和标题
   - ✓ 历史消息列表
   - ✓ 帮助文档
   - ✗ 实时更新的内容
   - ✗ 用户交互元素

2. **性能优化**
   - 将静态和动态内容分离
   - 对静态内容使用 Static 组件
   - 避免在 Static 内部使用状态

3. **代码组织**
   - 创建独立的组件
   - 使用 React.memo 进一步优化
   - 保持渲染函数纯净

## 扩展思路

基于这些示例，你可以：

1. **自定义横幅**
   - 替换 ASCII 艺术内容
   - 调整颜色方案
   - 添加动画效果（在非 Static 部分）

2. **集成到应用**
   - 作为应用启动横幅
   - 显示版本和配置信息
   - 结合其他 UI 组件

3. **创建主题**
   - 定义多套颜色方案
   - 支持深色/浅色模式
   - 响应用户偏好

## 相关资源

- [Ink 官方文档](https://github.com/vadimdemedes/ink)
- [Ink Static 组件说明](https://github.com/vadimdemedes/ink#static)
- [React 性能优化](https://react.dev/learn/render-and-commit)
- [终端颜色指南](https://en.wikipedia.org/wiki/ANSI_escape_code)

## 贡献

欢迎提交改进建议和新示例！

## 许可证

Apache-2.0
