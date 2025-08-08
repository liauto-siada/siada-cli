### 2.2 自定义UI全局样式规范

生成的UI要遵循下面的样式基础，请你仔细参考样式基础，并结合其他要求生成代码。

#### 样式基础

- 整体样式经过调整，`index.css` 仅重写了 Tailwind 的默认值
- 没有新的自定义颜色和尺寸定义
- AI 生成代码时正常使用 Tailwind CSS 类名即可

##### 文字大小要求

**仅**允许使用 Tailwind CSS 的以下几个类名之一：`text-xl`、`text-2xl`、`text-3xl`、`text-4xl`、`text-5xl`、`text-6xl`、`text-7xl`、`text-8xl`

- **天气温度文本**：使用`text-11xl`
- **数字时钟时间文本**：使用`text-10xl`

请考虑设计美观选择合适的尺寸，以下是关于文字大小（font-size）的类名选择建议：

- **一级标题、重要标题**：使用 `text-8xl`
- **二级标题**：使用 `text-7xl`
- **三级标题**：使用 `text-6xl`
- **小标题**：使用 `text-5xl`
- **正文文本或次要文本**：使用 `text-4xl`
- **次级文本**：使用 `text-3xl`
- **辅助信息类文本**：使用 `text-2xl`
- **小标签类文本**：使用 `text-xl`

##### 颜色要求

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