# Static Banner Examples - 完整索引

## 📚 文件列表

### 可执行示例（.tsx）

1. **simple-static-banner.tsx** (2.5K)
   - 最简单的 Static 组件示例
   - 适合初学者
   - 每行单一颜色

2. **gradient-static-banner.tsx** (5.0K)
   - 带渐变色效果的横幅
   - 从左到右平滑过渡
   - 包含装饰性边框

3. **static-banner-demo.tsx** (5.5K)
   - 完整的交互式演示
   - 静态横幅 + 动态内容
   - 展示性能优势

4. **test-layout.tsx** (2.3K)
   - 完整布局测试
   - 包含消息列表
   - 交互功能演示

### 文档文件（.md）

1. **README.md** (4.1K)
   - 快速开始指南
   - 每个示例的详细说明
   - 运行方式和技术要点

2. **STATIC_BANNER_EXAMPLES.md** (5.8K)
   - 实现总结和深入解析
   - 学习路径建议
   - 最佳实践和扩展思路

3. **VISUAL_COMPARISON.md** (9.6K)
   - 视觉效果对比
   - 性能分析
   - 自定义建议

4. **INDEX.md** (本文件)
   - 所有文件的索引
   - 快速导航指南

---

## 🚀 快速开始

### 第一次使用？从这里开始：

```bash
# 1. 运行最简单的示例
npm run example:simple

# 2. 查看渐变效果
npm run example:gradient

# 3. 体验完整演示
npm run example:demo
```

### 想深入学习？按此顺序阅读：

1. **README.md** - 了解概览和基础知识
2. **运行 simple-static-banner.tsx** - 实际体验最简单的实现
3. **阅读 STATIC_BANNER_EXAMPLES.md** - 深入理解技术细节
4. **运行 gradient-static-banner.tsx** - 体验进阶效果
5. **阅读 VISUAL_COMPARISON.md** - 理解性能和视觉差异
6. **运行 static-banner-demo.tsx** - 查看完整应用场景

---

## 📖 文档导航

### 想要...

**快速开始？**
→ 查看 [README.md](./README.md)

**理解原理？**
→ 阅读 [STATIC_BANNER_EXAMPLES.md](./STATIC_BANNER_EXAMPLES.md)

**对比效果？**
→ 参考 [VISUAL_COMPARISON.md](./VISUAL_COMPARISON.md)

**查看代码？**
→ 打开任意 .tsx 文件

**自定义实现？**
→ 参考 VISUAL_COMPARISON.md 中的"自定义建议"部分

---

## 🎯 按目标选择示例

### 学习目标

| 目标 | 推荐示例 | 文档 |
|------|---------|------|
| 学习 Static 组件 | simple-static-banner.tsx | README.md |
| 实现渐变色效果 | gradient-static-banner.tsx | STATIC_BANNER_EXAMPLES.md |
| 优化应用性能 | static-banner-demo.tsx | VISUAL_COMPARISON.md |
| 构建完整应用 | test-layout.tsx | README.md |

### 使用场景

| 场景 | 适用示例 | 说明 |
|------|---------|------|
| CLI 工具启动横幅 | gradient-static-banner.tsx | 专业美观 |
| 快速原型开发 | simple-static-banner.tsx | 简单快速 |
| 性能演示 | static-banner-demo.tsx | 展示优势 |
| 生产环境 | gradient-static-banner.tsx | 稳定可靠 |

---

## 🔍 代码特点对比

### Simple Static Banner
```
代码行数: ~70 行
复杂度: ★☆☆☆☆
视觉效果: ★★☆☆☆
学习价值: ★★★★★
生产就绪: ★★★☆☆
```

### Gradient Static Banner
```
代码行数: ~150 行
复杂度: ★★★☆☆
视觉效果: ★★★★★
学习价值: ★★★★☆
生产就绪: ★★★★★
```

### Static Banner Demo
```
代码行数: ~170 行
复杂度: ★★★★☆
视觉效果: ★★★★☆
学习价值: ★★★★★
生产就绪: ★★★☆☆
```

---

## 💡 技术要点速查

### Ink Static 组件
```tsx
import { Static } from '@jrichman/ink';

<Static items={items}>
  {(item, index) => (
    <Box key={index}>{/* ... */}</Box>
  )}
</Static>
```

### 渐变色算法
```javascript
const ratio = charIndex / (totalChars - 1);
const colorIndex = Math.floor(ratio * (colors.length - 1));
const color = colors[colorIndex];
```

### 颜色数组
```javascript
const lineColors = [
  '#5b8cd5', '#6BA5E7', '#79B8FF',
  '#7FC9E8', '#85D89D', '#85E89D'
];
```

---

## 🛠️ 开发工具

### 运行示例
```bash
npm run example:simple    # 简单版本
npm run example:gradient  # 渐变版本
npm run example:demo      # 完整演示
npm run example:layout    # 布局测试
```

### 直接执行
```bash
npx tsx examples/simple-static-banner.tsx
npx tsx examples/gradient-static-banner.tsx
npx tsx examples/static-banner-demo.tsx
npx tsx examples/test-layout.tsx
```

---

## 📊 示例统计

| 类型 | 数量 | 总大小 |
|------|------|--------|
| 可执行示例 (.tsx) | 4 | ~15.8K |
| 文档文件 (.md) | 4 | ~19.5K |
| 总计 | 8 | ~35.3K |

---

## 🎓 学习路径建议

### 初学者路径（2小时）
```
1. 阅读 README.md (15分钟)
2. 运行 simple-static-banner.tsx (5分钟)
3. 阅读 simple-static-banner.tsx 源码 (30分钟)
4. 修改颜色方案并运行 (20分钟)
5. 运行 gradient-static-banner.tsx (5分钟)
6. 对比两个示例的差异 (30分钟)
7. 阅读 STATIC_BANNER_EXAMPLES.md (15分钟)
```

### 进阶路径（4小时）
```
1. 完成初学者路径
2. 深入阅读 STATIC_BANNER_EXAMPLES.md (30分钟)
3. 实现自定义渐变算法 (1小时)
4. 运行 static-banner-demo.tsx (10分钟)
5. 分析性能差异 (30分钟)
6. 阅读 VISUAL_COMPARISON.md (30分钟)
7. 创建自己的横幅组件 (1小时)
```

### 专家路径（8小时）
```
1. 完成进阶路径
2. 集成到实际项目中 (2小时)
3. 优化性能和响应式设计 (2小时)
4. 添加主题切换功能 (1小时)
5. 编写单元测试 (1小时)
6. 文档和代码审查 (1小时)
```

---

## 🤝 贡献指南

想要贡献新的示例？欢迎！

### 示例要求
- ✓ 代码清晰，有详细注释
- ✓ 包含运行说明
- ✓ 遵循现有代码风格
- ✓ 提供效果截图或描述

### 文档要求
- ✓ 使用 Markdown 格式
- ✓ 包含代码示例
- ✓ 清晰的章节结构
- ✓ 中文说明

---

## 📞 获取帮助

遇到问题？

1. **查看文档**：从 README.md 开始
2. **运行示例**：实际操作理解更快
3. **阅读源码**：代码有详细注释
4. **参考对比**：VISUAL_COMPARISON.md 有详细分析

---

## 📝 更新日志

### 2024-01-06
- ✅ 创建 simple-static-banner.tsx
- ✅ 创建 gradient-static-banner.tsx
- ✅ 创建 static-banner-demo.tsx
- ✅ 创建完整文档系统
- ✅ 添加 npm 脚本支持

---

## 📄 许可证

Apache-2.0

---

**提示：** 所有示例都可以直接运行，无需额外配置！开始探索吧 🚀
