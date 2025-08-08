#### 自定义 UI 组件库详细 API 文档

本项目基于 shadcn/ui 进行了大范围定制，包含修改的原有组件和新增的业务组件。
使用的时候一定要确保import正确。

##### 样式基础

- 整体样式经过调整，`index.css` 仅重写了 Tailwind 的默认值
- 没有新的自定义颜色和尺寸定义
- AI 生成代码时正常使用 Tailwind CSS 类名即可

###### 文字大小要求

**仅**允许使用 Tailwind CSS 的以下几个类名之一：`text-xl`、`text-2xl`、`text-3xl`、`text-4xl`、`text-5xl`、`text-6xl`、`text-7xl`、`text-8xl`

请考虑设计美观选择合适的尺寸，以下是关于文字大小（font-size）的类名选择建议：

- **一级标题、重要标题**：使用 `text-8xl`
- **二级标题**：使用 `text-7xl`
- **三级标题**：使用 `text-6xl`
- **小标题**：使用 `text-5xl`
- **正文文本或次要文本**：使用 `text-4xl`
- **次级文本**：使用 `text-3xl`
- **辅助信息类文本**：使用 `text-2xl`
- **小标签类文本**：使用 `text-xl`

### 颜色要求

- 背景色不得与文字颜色显示相近颜色，这样显示会有问题，看不清楚。

###### 背景色

- `bg-slate-50`：一些元素组合构成的区域组件/布局背景强制使用此背景色
- **禁止使用** bg-white 作为背景颜色

###### 文字与图标颜色

**文字和图标颜色**

文字和图标颜色仅允许使用以下类名：

- `text-gray-950`：强调类文本
- `text-gray-900`：主要类文本
- `text-gray-600`：次要类文本
- `text-gray-400`：辅助类文本
- `text-gray-200`：失效类文本

**股票相关文字和图标颜色**（仅限股票相关场景使用）

- `text-green-700`：股票上涨/盈利类文本
- `text-red-800`：股票下跌/亏损类文本

**禁止使用**严禁使用其它类名作为文字或图标的颜色

###### 其他场景颜色

- `bg-blue-700`, `border-blue-700`, `fill-blue-700`, `stroke-blue-700`
- `bg-green-700`, `border-green-700`, `fill-green-700`, `stroke-green-700`
- `bg-red-800`, `border-red-800`, `fill-red-800`, `stroke-red-800`
- `bg-orange-700`, `border-orange-700`, `fill-orange-700`, `stroke-orange-700`
- `bg-indigo-700`, `border-indigo-700`, `fill-indigo-700`, `stroke-indigo-700`
- `bg-yellow-600`, `border-yellow-600`, `fill-yellow-600`, `stroke-yellow-600`
- `bg-slate-700`, `border-slate-700`, `fill-slate-700`, `stroke-slate-700`
- **禁止使用**其它颜色类名作为生成的代码中，除文字与图标外其它场景的颜色

---

##### 组件文档

- 注意，组件的描述是指组件已经实现的功能，有的需要调用API实现，有的不需要调用API就默认已经实现，不需要你再实现。

###### Button

基于 shadcn Button 组件进行了大幅定制的按钮组件，支持多种变体和尺寸。支持点击动画效果、loading状态、图标和开关模式，可自动调整宽度，严禁设置宽度相关样式。

###### 使用场景

- **页面/弹窗主要功能**： 弹窗的确认按钮
- **次要功能**： 弹窗的取消按钮
- **风险操作**： 删除按钮
- **开关控制**： 需要使用开关的场合
- **纯图标按钮**： 圆形图标按钮

```typescript
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "activated" | "primary" | "secondary" | "warning" | "ghost" | "text"
  size?: "xs" | "sm" | "md" | "lg" | "xl"
  asChild?: boolean
  loading?: boolean
  icon?: React.ReactNode
  isToggled?: boolean
}
```

###### 注意事项

**严禁设置宽度相关样式**

- **禁止使用**任何宽度相关的 className，如 `w-*`、`min-w-*`、`max-w-*` 等
- 组件内部已经设置了合适的文字左右内间距，会根据内容自动调整宽度
- 如需控制按钮在容器中的位置，请使用外层容器的布局类名，而不是直接修改按钮宽度

###### Variants

| 变体 | 颜色 | 说明 | 适用场景 |
|------|------|------|----------|
| `activated` | `bg-blue-600` | 激活按钮 | 页面/弹窗中确认开启的按钮 |
| `primary` | `bg-slate-600` | 主要按钮（默认） | 页面/弹窗中的主要功能，例：弹窗的确认按钮 |
| `secondary` | `bg-slate-400` | 次要按钮 | 页面/弹窗中同时存在两个按钮的次要功能，例：弹窗的取消按钮 |
| `warning` | `bg-red-700` | 警示按钮 | 如果某个操作可能存在风险，可以使用警示色来强调，例：删除按钮 |
| `ghost` | `text-gray-900` | 幽灵按钮 | 页面/弹窗中比较次要的/需要弱化按钮，例：播放页的选集按钮 |
| `text` | `text-blue-700` | 文本按钮 | 适用场景：协议入口 |

###### Sizes

| 尺寸 | 高度 |
|------|------|
| `xs` | `h-[80px]` |
| `sm` | `h-[100px]` |
| `md` | `h-[110px]` |
| `lg` | `h-[120px]` |
| `xl` | `h-[140px]` |

###### 使用示例

```tsx
// 图标+文字按钮
<Button variant="primary" size="md" loading={false} icon={<Icon />} onClick={handleClick}>
  确认
</Button>

// 纯图标圆形按钮
<Button size="lg" icon={<Home />} />

// 开关按钮
const [isToggled, setIsToggled] = React.useState(true);
<Button isToggled={isToggled} onClick={() => setIsToggled(!isToggled)}>
  开关按钮
</Button>
```

###### 导入方式

```typescript
import { Button } from "@/components/ui/button"
```

---

###### Badge

标签组件，用于标记和分类。支持多种颜色和样式变体，可用于强调、分类或状态展示。

#### 使用场景

- **内容标记**：影视、新闻内容的标签分类
- **状态展示**：VIP、热门、自制等状态标识
- **信息分类**：普通信息的分类标签

```typescript
interface BadgeProps extends React.ComponentProps<"span"> {
  variant?: "default" | "highlight" | "normal" | "weak"
  color?: "default" | "default1" | "hot" | "vip" | "self" | "normal" | "weak"
  size?: "default" | "small" | "large"
  asChild?: boolean
}
```

#### Variants

| 变体 | 说明 | 适用场景 |
|------|------|----------|
| `default` | 默认格式，黑色背景 | 用于强调重要信息 |
| `highlight` | 强调格式，彩色背景白字 | 影视、新闻封面的重要标签 |
| `normal` | 普通格式，灰色背景 | 普通主题分类 |
| `weak` | 弱化格式，带边框 | 需要弱化显示的标签 |

#### Colors

| 颜色 | 说明 | 搭配变体 |
|------|------|----------|
| `hot` | 红色，表示热点 | 与 `highlight` 搭配 |
| `vip` | 金色，表示VIP | 与 `highlight` 搭配 |
| `self` | 蓝色，表示自制内容 | 与 `highlight` 搭配 |

#### Sizes

| 尺寸 | 字体大小 |
|------|----------|
| `small` | `text-[20px]` |
| `default` | `text-[24px]` |
| `large` | `text-[28px]` |

#### 使用示例

```tsx
// 热门标签
<Badge variant="highlight" color="hot">热门</Badge>

// VIP标签
<Badge variant="highlight" color="vip">VIP</Badge>

// 普通分类标签
<Badge variant="normal">纪录片</Badge>

// 弱化标签
<Badge variant="weak" size="small">标签</Badge>
```

#### 导入方式

```typescript
import { Badge } from "@/components/ui/badge"
```

---

### Bubble

气泡组件，用于展示单行文本信息。圆角椭圆形外观，自适应内容宽度，适合用于标签、提示或装饰性文本展示。

#### 使用场景

- **信息标签**：显示简短的描述性文本
- **状态提示**：当前状态或模式的文字展示
- **装饰元素**：页面中的装饰性文本标识

```typescript
interface BubbleProps {
  content: string    // 气泡显示的文字内容
}
```

#### 使用示例

```tsx
<Bubble content="正在连接中..." />
```

#### 导入方式

```typescript
import Bubble from "@/components/mindui/bubble"
```

---

### TextLink

文字链接组件，提供统一的链接样式。固定蓝色文字，用于页面内的文字链接展示。

#### 使用场景

- **跳转链接**：指向外部网站的文字跳转链接

```typescript
interface TextLinkProps extends React.HTMLAttributes<HTMLAnchorElement> {
  content: string    // 链接显示的文字内容
  href: string       // 链接地址
  className?: string // 样式类名
}
```

#### 使用示例

```tsx
// 外部链接
<TextLink 
  content="访问官网" 
  href="https://example.com" 
  target="_blank"
/>
```

#### 导入方式

```typescript
import TextLink from "@/components/mindui/textLink"
```

---

### HorizontalSelector

水平选择器组件，具有滑动动画效果和多种自定义选项，用于在一组选项中进行选择。支持方向键切换选项、图标显示、VIP标签和禁用状态，只能出现在每张卡的顶部。当出现多个选项时，使用水平选择器组件。

#### 使用场景

- **模式选择**：标准模式、节能模式、超级节能 / 日、月
- **音质选择**：标准音质、极高音质、SQ无损音质、Hi-Res
- **菜单选择**：推荐、官方、精品、华语、摇滚 / 自上次补能、今日行程、小计里程、自定义、陪伴里程
- **循环录制模式选择**：1分钟、2分钟、3分钟

```typescript
interface HorizontalSelectorProps {
  options: Array<{
    label: string          // 显示在选项卡的文本
    value: string          // 组件内部使用的变量值
    disabled?: boolean     // 此当前选项是否被禁用
    icon?: string          // Lucide图标名称
    tag?: boolean          // 是否显示VIP标签
  }>                       // 可选项数组
  value: string            // 被选择选项的value成员值
  onChange: (value: string) => void  // 切换选项时的回调函数，传入参数为更改后新的选项value成员值
  className?: string       // 样式类名，仅用于控制组件内部最外层div元素的样式
  size?: "xs" | "sm" | "md" | "lg" | "xl"  // 尺寸
  color?: "default" | "primary"  // 配色方案
}
```

#### Sizes

| 尺寸 | 高度 |
|------|------|
| `xs` | `h-[80px]` |
| `sm` | `h-[100px]` |
| `md` | `h-[110px]` |
| `lg` | `h-[120px]` |
| `xl` | `h-[140px]` |

#### Color Variants

| 配色 | 说明 |
|------|------|
| `default` | 默认颜色，`bg-netural-50` |
| `primary` | 主要颜色，`bg-indigo-500` |

#### 使用示例

```tsx
const [selectedValue, setSelectedValue] = useState('value1');

<HorizontalSelector
  options={[
    { label: "选项1", value: "value1", tag: true },
    { label: "选项2", value: "value2" },
    { label: "选项3", value: "value3", icon: "House" }
  ]}
  value={selectedValue}
  onChange={setSelectedValue}
  size="md"
  color="primary"
/>
```

#### 导入方式

```typescript
import { HorizontalSelector } from "@/components/mindui/horizontal-selector"
```

---

### Image

图片显示组件，支持不同的适配模式，用于智能处理不同尺寸图片的展示方式。自动检测图片比例，支持标准比例约束，容器自适应，URL失效时自动隐藏。**所有需要展示图片的场景必须使用此组件**。

#### 使用场景

- **电商商品图**：需要严格控制图片展示比例的场景
- **社交媒体卡片**：确保UI一致性的图片展示
- **内容展示**：各种需要图片展示的场景

```typescript
interface ImageProps extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, "src"> {
  url: string                    // 所展示图片的URL地址
  fit?: "natural" | "standard"   // 图片尺寸适配模式，详见下方 Fit Modes 说明
  className?: string             // 样式类名，仅用于控制组件内部最外层div元素的样式
}
```

#### Fit Modes

| 模式 | 说明 |
|------|------|
| `natural` | （默认选项）保持图片原始比例，使宽度撑满容器，然后高度自适应 |
| `standard` | 强制约束图片为标准比例（1:1、4:3、16:9），若图片超出容器则裁切图片 |

#### 使用示例

```tsx
<Image url="/path/to/image.jpg" fit="natural"/>
<Image url="/path/to/image.jpg" fit="standard"/>
```

#### 导入方式

```typescript
import { Image } from "@/components/mindui/image"
```

---

### Progress

进度条组件，用于显示任务或操作的完成进度。支持蓝色和绿色两种配色方案，完全圆角设计。

#### 使用场景

- **常规加载**：数据传输、链接状态等通用场景
- **积极场景**：能量、环保、健康指标等

```typescript
interface ProgressProps extends React.ComponentProps<typeof ProgressPrimitive.Root> {
  value?: number
  variant?: "blue" | "green"
}
```

#### Variants

| 变体 | 说明 | 适用场景 |
|------|------|----------|
| `blue` | `bg-blue-700` | 常规加载、数据传输、链接状态等通用场景 |
| `green` | `bg-green-700` | 能量、环保、健康指标等积极场景 |

#### 使用示例

```tsx
const [progress, setProgress] = useState(0);
<Progress value={progress} variant="green" className="h-[8px] w-full" />
<Progress value={75} variant="blue" className="h-[12px] w-[300px]" />
```

#### 导入方式

```typescript
import { Progress } from "@/components/ui/progress"
```

---

### Checkbox

定制化的复选框组件。自定义对钩图标，支持禁用状态。

#### 使用场景

- **表单选择**：多选项表单
- **设置选项**：功能开关配置

```typescript
interface CheckboxProps extends React.ComponentProps<typeof CheckboxPrimitive.Root> {
  // 继承所有 Radix Checkbox 属性
}
```

#### 使用示例

```tsx
<Checkbox checked={isChecked} onCheckedChange={setIsChecked} />
<Checkbox disabled />
<Checkbox defaultChecked />
```

#### 导入方式

```typescript
import { Checkbox } from "@/components/ui/checkbox"
```

---

### ScrollArea

滚动区域组件，提供自定义滚动条样式。滚动时滚动条变宽，静止时变窄，支持自动隐藏和平滑过渡动画。

#### 使用场景

- **长内容展示**：需要滚动查看的内容区域
- **列表展示**：各种需要滚动的列表组件

```typescript
interface ScrollAreaProps {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
}
```

#### 使用示例

```tsx
<ScrollArea className="h-[400px] w-full">
  <div className="p-4">
    {/* 滚动内容 */}
    <p>长内容...</p>
  </div>
</ScrollArea>
```

#### 导入方式

```typescript
import { ScrollArea } from "@/components/ui/scroll-area"
```

---

### Separator

定制化的分割线组件。支持水平和垂直方向，垂直显示时左右距离其他元素相同间距且保持垂直居中，横向显示时上下距离其他元素相同间距。

#### 使用场景

- **内容分隔**：垂直排列内容之间的分隔
- **布局分隔**：水平排列内容之间的分隔

```typescript
interface SeparatorProps extends React.ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root> {
  orientation?: "horizontal" | "vertical"
}
```

#### Orientation

| 方向 | 说明 | 用途 |
|------|------|------|
| `horizontal` | 水平分隔线（默认） | 用于垂直排列内容之间的分隔 |
| `vertical` | 垂直分隔线 | 用于水平排列内容之间的分隔 |

#### 使用示例

```tsx
// 水平分隔线（默认）
<Separator />

// 垂直分隔线
<Separator orientation="vertical" />
```

#### 导入方式

```typescript
import { Separator } from "@/components/ui/separator"
```

---

### Loading

加载动画组件。旋转动画图标，必须居中显示。

#### 使用场景

- **页面加载**：页面初始化加载状态
- **数据加载**：等待数据请求完成的状态展示

```typescript
// 无特殊 props，纯展示组件
```

#### 使用示例

```tsx
<Loading />
```

#### 导入方式

```typescript
import { Loading } from "@/components/mindui/loading"
```

---

### AreaChart

面积图组件，支持趋势展示和响应式布局，用于显示数据随时间变化的趋势。智能趋势判断，自动比较首末数值显示不同颜色，渐变填充，包含参考线，响应式布局根据容器宽度自动调整显示元素。

#### 使用场景

- **数据趋势分析**：显示数据随时间变化的趋势
- **性能监控**：系统指标的趋势展示
- **业务数据**：销售额、用户增长等业务指标趋势

```typescript
interface AreaChartProps {
  data: DataPoint[]          // 数据数组，每个对象包含横轴键和数据键
  dataKey: string            // 指定用作Y轴数据的键名
  name?: string              // 图表名称，用于图例显示
  fillOpacity?: number       // 填充透明度 (0-1)，默认0.6
  connectNulls?: boolean     // 是否连接空值点，默认false
  xAxisKey?: string          // 指定用作X轴数据的键名，默认"name"
  margin?: {                 // 图表边距配置
    top?: number
    right?: number
    bottom?: number
    left?: number
  }
  className?: string         // 样式类名
}

interface DataPoint {
  [key: string]: string | number
}
```

#### 使用示例

```tsx
const chartData = [
  { name: "1月", price: 2400 },
  { name: "2月", price: 1398 },
  { name: "3月", price: 9800 },
];

// 基础用法 - 组件会自动占满容器尺寸
<div className="h-[400px] w-full">
  <AreaChart 
    data={chartData} 
    dataKey="price" 
    xAxisKey="name"
  />
</div>

// 自定义透明度和边距
<div className="h-[300px] w-[600px]">
  <AreaChart 
    data={chartData} 
    dataKey="price" 
    xAxisKey="name"
    fillOpacity={0.8}
    margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
  />
</div>
```

#### 导入方式

```typescript
import AreaChart from "@/components/mindui/area-chart"
```

---

### PieChart

饼图组件，支持环形图和完整饼图展示，用于显示数据的比例分布。智能响应式布局，数据验证过滤无效数据，百分比显示，悬停效果，支持环形图。

#### 使用场景

- **数据比例分布**：各类别数据的占比展示
- **统计图表**：用户分布、销售占比等统计数据
- **仪表盘展示**：系统资源使用情况等

```typescript
interface PieChartProps {
  data: PieChartData[]       // 饼图数据数组
  showLegend?: boolean       // 是否显示图例，默认true
  innerRadius?: number | string  // 内半径，设置为0显示完整饼图，设置百分比显示环形图
  outerRadius?: number | string  // 外半径，默认"100%"
  paddingAngle?: number      // 扇形间隔角度，默认0
  startAngle?: number        // 起始角度，默认90
  endAngle?: number          // 结束角度，默认-270
  className?: string         // 样式类名
  colors?: string[]          // 自定义颜色数组
  legendFormatter?: (value: string, name: string) => string  // 图例格式化函数
  legendPosition?: "bottom" | "right"  // 图例位置，默认"bottom"
}

interface PieChartData {
  name: string               // 数据项名称
  value: number              // 数据项数值
  color?: string             // 可选的自定义颜色
}
```

#### 使用示例

```tsx
const pieData = [
  { name: "分类A", value: 400 },
  { name: "分类B", value: 300 },
  { name: "分类C", value: 300 },
];

// 完整饼图
<div className="h-[350px] w-full">
  <PieChart data={pieData} innerRadius={0} />
</div>

// 环形图（默认）
<div className="h-[350px] w-full">
  <PieChart 
    data={pieData} 
    innerRadius="70%" 
    outerRadius="100%"
  />
</div>
```

#### 导入方式

```typescript
import PieChart from "@/components/mindui/pie-chart"
```

---

### BarChart

柱状图组件，支持单/多数据系列、横向/纵向布局，用于数据对比和分析。智能柱子尺寸根据数据系列数量自动调整，响应式布局，多系列时自动显示图例，圆角样式。

#### 使用场景

- **数据对比分析**：不同类别数据的对比
- **时间序列数据**：纵向柱状图展示时间变化
- **分类排名数据**：横向柱状图展示排名情况
- **多指标对比**：多系列柱状图同时展示多个指标

```typescript
interface BarChartProps {
  data: DataPoint[]          // 柱状图数据数组
  dataKeys: string | string[]  // 单个或多个数据键，支持多系列展示
  selectedData?: string      // 选中的数据项
  xAxisKey?: string          // X轴数据键名，默认"name"
  orientation?: "vertical" | "horizontal"  // 图表方向，默认"vertical"
  margin?: {                 // 图表边距配置
    top?: number
    right?: number
    bottom?: number
    left?: number
  }
  colors?: string[]          // 自定义颜色数组
  showGrid?: boolean         // 是否显示网格，默认true
  showTooltip?: boolean      // 是否显示提示框，默认true
  showLegend?: boolean       // 是否显示图例，默认true
  showXAxis?: boolean        // 是否显示X轴，默认true
  showYAxis?: boolean        // 是否显示Y轴，默认true
  className?: string         // 样式类名
  barSize?: number           // 自定义柱子宽度
  barGap?: number            // 柱子间距，默认4
  barCategoryGap?: number    // 分类间距，默认10
}

interface DataPoint {
  [key: string]: string | number
}
```

#### 使用示例

```tsx
const barData = [
  { name: "1月", A: 4000, B: 2400, C: 1600 },
  { name: "2月", A: 3000, B: 1398, C: 1602 },
];

// 纵向单系列柱状图
<div className="h-[350px] w-full">
  <BarChart 
    data={barData} 
    dataKeys="A" 
    xAxisKey="name"
    orientation="vertical"
  />
</div>

// 纵向多系列柱状图
<div className="h-[500px] w-full">
  <BarChart 
    data={barData} 
    dataKeys={["A", "B", "C"]} 
    xAxisKey="name"
    orientation="vertical"
    showLegend={true}
  />
</div>
```

#### 导入方式

```typescript
import BarChart from "@/components/mindui/bar-chart"
```

---

### LineChart

折线图组件，支持单/多条折线展示，用于显示数据趋势和变化。多条折线支持数据对比，响应式布局根据容器宽度自动调整显示元素，平滑折线，图例智能显示。

#### 使用场景

- **趋势分析**：显示数据随时间的变化趋势
- **多指标对比**：同时展示多个指标的变化情况
- **性能监控**：系统指标、业务数据的实时监控
- **财务报表**：收入、支出等财务数据的趋势展示
- **用户行为**：用户活跃度、转化率等指标分析

```typescript
interface LineChartProps {
  data: DataPoint[]          // 折线图数据数组
  dataKeys: string | string[]  // 单个或多个数据键，支持多条折线
  xAxisKey?: string          // X轴数据键名，默认"name"
  margin?: {                 // 图表边距配置
    top?: number
    right?: number
    bottom?: number
    left?: number
  }
  colors?: string[]          // 自定义颜色数组
  showGrid?: boolean         // 是否显示网格，默认true
  showTooltip?: boolean      // 是否显示提示框，默认true
  showLegend?: boolean       // 是否显示图例，默认true
  showXAxis?: boolean        // 是否显示X轴，默认true
  showYAxis?: boolean        // 是否显示Y轴，默认true
  className?: string         // 样式类名
  strokeWidth?: number       // 自定义线条宽度
  dot?: boolean              // 是否显示数据点，默认false
}

interface DataPoint {
  [key: string]: string | number
}
```

#### 使用示例

```tsx
const lineData = [
  { name: "1月", A: 4000, B: 2400, C: 1600 },
  { name: "2月", A: 3000, B: 1398, C: 1602 },
];

// 单条折线图
<div className="h-[350px] w-full">
  <LineChart 
    data={lineData} 
    dataKeys="A" 
    xAxisKey="name"
    colors={["#0A5BFC"]}
  />
</div>

// 多条折线图
<div className="h-[350px] w-full">
  <LineChart 
    data={lineData} 
    dataKeys={["A", "B", "C"]} 
    xAxisKey="name"
    showLegend={true}
  />
</div>
```

#### 导入方式

```typescript
import { LineChart } from "@/components/mindui/line-chart"
```

---

### RadialBarChart

径向条形图组件，用于显示单一数据的进度或完成度，具有圆形进度条的视觉效果。圆形进度展示，响应式设计支持任意容器尺寸，居中显示数值，自适应字体。

#### 使用场景

- **能耗监控**：电量使用、能源消耗等指标展示
- **完成度展示**：任务完成进度、目标达成率等
- **性能指标**：系统负载、存储使用率等
- **健康数据**：运动目标、健康指标等
- **仪表盘**：各种单一数值的可视化展示

```typescript
interface RadialBarChartProps {
  value: number               // 当前数值
  max?: number               // 最大值，默认200
  unit?: string              // 数值单位（如"kwh"、"%"等）
  className?: string         // 样式类名，仅用于控制组件内部最外层div元素的样式
}
```

#### 使用示例

```tsx
// 基础用法
<RadialBarChart value={120} unit="kwh" max={200} />

// 百分比展示
<RadialBarChart value={75} unit="%" max={100} />

// 自定义容器尺寸
<div className="h-64 w-64">
  <RadialBarChart value={85} unit="分" max={100} />
</div>
```

#### 导入方式

```typescript
import { RadialBarChart } from "@/components/mindui/radial-bar-chart"
```

---

### Gauge

仪表盘组件，提供类似汽车仪表盘的圆弧形数据展示，支持高度自定义的外观和功能。高度自定义支持自定义颜色、厚度、角度范围，响应式设计基于容器尺寸自动调整，弯曲文本支持沿仪表盘弧线显示，智能缩放所有元素根据容器尺寸智能缩放。

#### 使用场景

- **车载仪表**：速度表、转速表、油量表等
- **系统监控**：CPU使用率、内存占用、网络流量等
- **业务指标**：销售达成率、用户满意度、KPI完成度等
- **环境监测**：温度、湿度、压力等物理量显示
- **游戏界面**：血量、魔法值、经验值等状态显示

```typescript
interface GaugeProps {
  value: number              // 当前数值
  max?: number              // 最大值，默认100
  label?: React.ReactNode   // 自定义标签内容，默认显示value的四舍五入值
  unit?: string             // 数值单位
  thicknessRatio?: number   // 厚度比例（0-1），默认0.2 (20%)
  color?: string            // 主色调
  trackColor?: string       // 轨道颜色
  unitColor?: string        // 单位文字颜色
  className?: string        // 样式类名
  startAngle?: number       // 起始角度，默认225
  endAngle?: number         // 结束角度，默认为startAngle-360
  showLabels?: boolean      // 是否显示标签，默认true
  curvedText?: string       // 弯曲文本内容，沿仪表盘弧线显示
}
```

#### 使用示例

```tsx
// 基础速度仪表
<div className="h-64 w-64">
  <Gauge value={75} max={120} unit="km/h" />
</div>

// 带弯曲文本的仪表
<div className="h-72 w-72">
  <Gauge 
    value={85} 
    max={100} 
    unit="%" 
    curvedText="系统负载监控"
  />
</div>

// 自定义角度范围（半圆）
<div className="h-48 w-96">
  <Gauge 
    value={60} 
    max={100} 
    unit="分"
    startAngle={180}
    endAngle={0}
    thicknessRatio={0.15}
  />
</div>
```

#### 导入方式

```typescript
import { Gauge } from "@/components/mindui/gauge"
```

---

### Calendar

日历组件，支持简单模式和农历模式，提供日期选择功能和智能响应式布局。双历显示农历模式下同时显示公历日期和农历日期。严禁定时刷新，日历组件内部已支持刷新。

#### 使用场景

- **日期选择**：需要用户选择日期的表单场景
- **日历展示**：显示日历信息，支持农历显示
- **日期导航**：提供日期浏览和选择功能

```typescript
interface CalendarProps {
  type?: "simple" | "lunar"           // 日历类型，默认"simple"
  selected?: Date                     // 当前选中的日期
  onSelect?: (date: Date | undefined) => void  // 日期选择回调函数
  className?: string                  // 样式类名
  showOutsideDays?: boolean          // 是否显示月份外的日期，默认false
  weekStartsOn?: 0 | 1 | 2 | 3 | 4 | 5 | 6  // 一周开始日期（0=周日，1=周一），默认1
}
```

#### Types

| 类型 | 说明 | 特点 |
|------|------|------|
| `simple` | 简单模式（默认） | 仅显示公历日期，圆形日期按钮 |
| `lunar` | 农历模式 | 显示公历+农历日期，椭圆形日期按钮 |

#### 使用示例

```tsx
const [selectedDate, setSelectedDate] = useState<Date | undefined>(new Date());

// 简单模式
<Calendar
  type="simple"
  selected={selectedDate}
  onSelect={setSelectedDate}
/>

// 农历模式
<Calendar
  type="lunar"
  selected={selectedDate}
  onSelect={setSelectedDate}
  weekStartsOn={0}
/>
```

#### 导入方式

```typescript
import { Calendar } from "@/components/mindui/calendar"
```

---

## 使用指南

### 优先级顺序

在编写页面时，每次进行组件选择时，对于匹配度较高的使用场景，请按以下优先级顺序选择：

1. **自定义组件库中的组件**（最高优先级）
2. **shadcn/ui 原组件**
2. **原生 React 或 Radix 组件**（最低优先级）