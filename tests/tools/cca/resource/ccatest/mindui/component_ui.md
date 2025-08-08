# MindUI 组件文档

## 已封装好的组件

- **Button** - 按钮组件
- **HorizontalSelector** - 水平选择器
- **Image** - 图片组件
- **Progress** - 进度条
- **Checkbox** - 复选框
- **ScrollArea** - 滚动区域
- **Separator** - 分隔符
- **Loading** - 加载组件
- **AreaChart** - 面积图
- **PieChart** - 饼图
- **BarChart** - 柱状图
- **LineChart** - 折线图
- **Gauge** - 仪表盘
- **RadialBarChart** - 径向柱状图
- **Calendar** - 日历
- **Badge** - 标签
- **TextLink** -文字链接
- **Bubble** -气泡
- **Timeline** - 时间线
- **Combo** - 游戏场景，连击动效
- **Plus1** - 游戏场景，+1动效
- **Markdown** - 富文本组件
- **ShowingBox** - 游戏场景，出现消失动效

## 已封装好的模板

### Game.tsx - 游戏模板

**模板描述：** 专为游戏场景设计的模板，具有以下特性：

- **游戏内容区域：** 813 × 813 像素，支持完全自定义
- **交互按钮：** 可根据需求自定义样式和功能
- **其他元素：** 采用固定布局，确保界面一致性
- **使用组件范围：** Button

该模板适用于各类小游戏的快速开发，提供了灵活的内容区域和可定制的交互元素。

### ListTemplates.tsx - 列表模板

**模板描述：** 专为列表展示场景设计的模板，具有以下特性：

- **列表项组件：** 提供 6 种不同样式的列表项（ListItem1、ListItem2、ListItem3）
- **分隔符支持：** 自动在列表项之间添加分隔线，保持视觉层次
- **灵活布局：** 支持动态数量的列表项渲染

**列表项组件：**
- **ListItemTitle** 只包含大标题 (使用的其他组件：无)
- **ListItemTitleAndSubTitle** 包含大标题、副标题或摘要内容 (使用的其他组件：无)
- **ListItemTitleAndUList** 包含大标题和无序列表内容 (使用的其他组件：无)
- **ListItemTitleDetailWithTagAuthorSubtitle** 包含大标题、描述、标签、作者、副标题 (使用的其他组件：Badge)
- **ListItemTitleWithImageTagDate** 包含大标题、图片、标签、日期 (使用的其他组件：Image, Badge)
- **ListItemTitleWithAuthorSubtitle** 包含大标题、作者、副标题 (使用的其他组件：Badge)


该模板适用于新闻列表、文章目录、信息展示等各类列表场景的快速开发。

## 已封装好的图标组件

**图标组件使用方法：**

1. **导入组件**

   ```tsx
   import { 
     SeatHeating,
     FrontWindshieldHeating,
   } from '@/components/icons/icons/index';
   ```

2. **组件用法**

   直接以组件方式使用：

   ```tsx
   <FrontWindshieldHeating />
   ```

   可传入 `color` 和 `size` 参数调整颜色和大小（默认当前颜色，72px）：

   ```tsx
   <SeatHeating color="#EA5C4A" size={100} />
   ```

**图标列表：**

- **AcSwitch** - AC 开关
- **AirVolumn** - 风量
- **CirculationInside** - 内循环
- **CirculationMode** - 循环模式
- **AtmosphereLight** - 氛围灯亮度
- **BackWindowHeating** - 后窗加热
- **Cold** - 制冷
- **CirculationOutside** - 外循环
- **Defrost** - 除霜
- **FrontWindshieldHeating** - 除雾 前挡风玻璃加热
- **EcoSwitch** - 节能开关
- **MirrorHeating** - 后视镜加热
- **SeatVentilation** - 座椅通风
- **SeatHeating** - 座椅加热
- **ReadingLight** - 阅读灯
- **SeatMassage** - 座椅按摩
- **SteeringwheelAuto** - 方向盘/座椅加热自动调节
- **Fragrance** - 香氛
- **SteeringwheelHeating** - 方向盘加热
- **WindFeet** - 吹脚
- **WindFace** - 吹脸
- **SyncSwitch** - SYNC 开关
- **Switch** - 空调开关
- **Plus** - 加号
- **Minus** - 减号
- **Car** - 汽车 作为默认图标

## Update
### 2025-07-21
Gauge 的 color 参数 更新为 color?: 'blue' | 'green' | 'yellow' | 'red' | 'gray';
RadialBarChart 的 barColor 参数 更新为 barColor?: 'blue' | 'green' | 'yellow' | 'red' | 'gray';

index.css 中基础颜色增加深色模式对应的色值，基础文本颜色的深色模式，按设计稿，透明度与浅色模式不相同。
增加几种新的基础颜色
- **--color-slate-200** - 卡片背景颜色
- **--color-slate-50** - 容器背景颜色
- **--color-slate-100** - 游戏说明弹窗背景颜色

Badge 组件 color 去除 default1 样式，default 样式由黑色更新为橙色