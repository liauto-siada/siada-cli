# MindUI 卡片构建系统

## 项目概述

这是一个基于 Vite + React + TypeScript 的卡片组件构建系统，专门用于构建和打包AI生成的React卡片组件。系统支持多卡片并行构建，每个卡片会生成独立的目录结构和zip包。

## 项目结构

```
mindui-components/
├── src/
│   ├── cards/              # 存放精品卡片组件
│   ├── components/         # 共享组件库
│   │   ├── icons/          # 图标组件
│   │   ├── mindui/         # MindUI核心组件
│   │   └── ui/             # UI基础组件
│   ├── assets/             # 静态资源
│   ├── carapi_js/          # 车端API接口
│   ├── comppreview/        # 组件预览
│   ├── drawable/           # 绘图资源
│   ├── gesture_animation/  # 手势动画
│   ├── hooks/              # React钩子
│   ├── image/              # 图片资源
│   ├── lib/                # 工具库
│   ├── templates/          # 模板库
│   ├── test/               # 测试文件
│   ├── App.tsx             # 应用主组件
│   └── main.tsx            # 主入口文件
├── plaza/                  # 已构建卡片展示区
│   └── product/            # 产品卡片
│       ├── BubbleBattle/   # 泡泡对战卡片
│       ├── WhackAMole/     # 打地鼠卡片
│       └── ...             # 其他卡片
├── scripts/                # 构建脚本
│   └── build.js            # 卡片构建脚本
├── README.md               # 项目说明
├── package.json            # 项目配置
└── vite.config.ts          # Vite构建配置
```

## 核心特性

- **多卡片构建**: 支持构建多个卡片组件
- **独立目录**: 每个卡片生成独立的目录结构
- **自动打包**: 自动生成zip包，便于部署和分发
- **模板库**: 提供多种卡片模板供开发使用
- **组件库**: 丰富的UI组件库支持

## 使用方法

### 构建单个卡片

```bash
node scripts/build.js <CardName>
```

### 示例

```bash
# 构建Star卡片
node scripts/build.js Star

# 构建TechNewsList卡片
node scripts/build.js TechNewsList
```

## 构建流程

1. **验证卡片文件** - 检查`src/cards/<CardName>.tsx`文件是否存在
2. **更新HTML模板** - 创建新的HTML文件指向指定卡片
3. **清理构建产物** - 删除旧的`dist`目录
4. **执行Vite构建** - 运行构建生成产物
5. **重组目录结构** - 创建卡片专用子目录，移动所有文件
6. **创建ZIP文件** - 将卡片目录打包成ZIP文件
7. **生成构建报告** - 记录构建信息

## 构建产物

构建完成后，每个卡片的目录结构如下：

```
dist/CardName/
├── index.html          # 主HTML文件
├── assets/             # 资源文件
│   ├── js/             # JavaScript文件
│   └── css/            # CSS样式文件
├── polyfills/          # 兼容性填充
│   └── assets/js/      # 兼容性JS文件
└── shared/             # 共享资源
    └── css/            # 共享样式文件

packages/
└── CardName.zip        # 卡片ZIP包
```

## 可用的npm脚本

```bash
# 开发相关
npm run dev          # 启动开发服务器
npm run build        # 构建项目
npm run preview      # 预览构建结果
npm run lint         # 代码检查
```

## 精品卡编写规则

1. 放在src/cards目录下
2. 在index.html里引用，并执行npm run dev看效果，并保证npm run build编译通过

## 游戏卡编写规则

1. 放在src/cards目录下，建game目录
2. 在index.html里引用，并执行npm run dev看效果，并保证npm run build编译通过
3. 游戏模板参考main_game.tsx这个外层容器和src/templates/game/OneButtonGame.tsx、src/templates/game/MultiButtonGame.tsx这2个游戏模板编写，其中main_game.tsx是外层包含标题、弹窗在内的容器，OneButtonGame是简单按钮控制游戏，MultiButtonGame是复杂按钮控制游戏。