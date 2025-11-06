from agents import function_tool, RunContextWrapper

from siada.foundation.code_agent_context import CodeAgentContext
from siada.tools.coder.observation.observation import FunctionCallResult


CARD_GEN_DOCS = """
Card Generation Tool

根据用户需求生成车机卡片的 React TypeScript 代码。

## 功能说明
此工具用于生成符合车机环境要求的前端卡片代码，支持以下特性：
- 基于 React 19 + TypeScript 开发
- 使用 Tailwind CSS 进行样式设计
- 集成 shadcn/ui 和 MindUI 组件库
- 适配车机显示环境（813px 宽度）

## 目标
- 第一要求是不违反卡片的规则和限制
- 第二要求是美观性

## 代码生成要求

### 基础结构要求
- 必须生成完整的 React 组件代码
- 主组件名称应与文件名保持一致（如 HoroscopeCard.tsx 导出 HoroscopeCard）
- 使用 `export default 组件名` 导出主组件
- 代码必须以 `import {{ StrictMode, useState }} from 'react'` 开头
- 请注意生成代码中不要出现语法错误

### 布局规范
- 主组件根元素宽度设置为 `w-[813px]`
- 第一层 div 必须使用 `<div className="w-[813px] p-0 rounded-[20px]">`
- 严禁设置 `overflow-hidden` 或写死高度
- 内容区域不设置内间距，由外层容器处理
- 不允许弹窗或者跳转页面，所有交互在当前视图内完成
- 长文本请添加 `break-words` 或按需使用 `line-clamp-*`，避免撑破容器

### 样式要求
- 优先使用 shadcn/ui 组件：从 "@/components/ui" 导入
- 使用 MindUI 组件：从 "@/components/mindui" 导入
- 样式使用 Tailwind CSS 工具类
- 区块背景色强制使用 `bg-slate-50`
- 区块标题：`text-6xl text-gray-950 font-semibold`
- 区块内容：`text-3xl text-gray-600`
- 不用过于鲜艳的颜色和过于复杂的颜色组合，除非有特殊的需要，例如消消乐游戏这类卡片

### 数据处理
- 初始状态使用空数据（""、[]、{{}}、0 等）
- 保持数据结构完整，仅将内容设为空值
- 不显示加载提示文字
- 支持从空数据直接过渡到 API 数据

### 车控特定要求
- 如涉及车控功能，需预留 API 调用接口
- 按钮宽度不超过区块宽度
- 功能描述文字可换行显示
- 区块内容垂直左对齐，使用 `flex flex-col items-start`

## 输出格式
工具必须返回完整的 TypeScript React 代码，包含：
1. 必要的 import 语句
2. 主组件定义
3. 数据结构定义（如需要）
4. 组件导出语句

## 注意事项
- 严禁在代码前后添加任何解释文字或 markdown 标记
- 确保代码语法正确，可直接编译运行
- 遵循车机环境的性能和显示限制
- 保持代码简洁，避免过度复杂的逻辑
- 注意不要引入不存在的变量，和没有导入的方法，这会导致编译报错

## 示例（仅参考格式，不参考内容）
```
import { StrictMode, useState } from 'react'
import { createRoot } from 'react-dom/client'
import '../index.css'
import { NewsTemplates } from '../templates/newsTemplates/newsTemplates'
import { ScrollArea } from '@/components/ui/scroll-area'
import { GetLixiangStudentInfo } from "../carapi_js/CloudAPI/LixiangStudentAPI"

// 资讯卡片组件定义
const TechInfoCard = () => {
    return (
        <NewsTemplates 
            data={{
                text: "最新科技动态",
                apiUrl: "实际url"
            }}
        />
    );
};

export default TechInfoCard

// App应用
const App = () => {
  return (
    <div className="w-[933px] h-[1360px] bg-slate-200 rounded-[20px] py-[60px] relative">
      {/* 标题区域 */}
        <h1 className="px-[60px] text-[52px] leading-none font-bold text-gray-950 mb-[138px]">科技动态</h1>

      {/* 内容区域 */}
      <div className="pl-[60px] pr-[20px] h-[1050px]">
        <ScrollArea className="h-full w-full">
            <TechInfoCard />
        </ScrollArea>
      </div>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
```

## 参数说明
Args:
    code: (required) 完整的 React TypeScript 卡片代码，必须以 `import {{ StrictMode, useState }} from 'react'` 开头，以 createRoot 函数及内容结尾（参考示例内的结尾）
    file_path: (required) 卡片文件的保存路径，通常为 .tsx 文件
"""

GAME_CARD_SUPPLEMENT = """
### 游戏卡限制
如果生成的是一张游戏卡片的代码，需要遵守以下原则
"""

@function_tool(
    name_override="card_gen", description_override=CARD_GEN_DOCS
)
async def card_gen(
    context: RunContextWrapper[CodeAgentContext],
    code: str,
    file_path: str
) -> FunctionCallResult:
    print(code)
    print(file_path)
    with open(file_path, "w") as f:
        f.write(code)
    return FunctionCallResult("code generated for card")
