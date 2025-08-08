import * as React from "react"
import * as ProgressPrimitive from "@radix-ui/react-progress"
import { cva } from "class-variance-authority"

import { cn } from "@/lib/utils"
/* 
### Progress (progress.tsx)

基于 Radix UI Progress 组件进行定制，用于显示任务或操作的完成进度。

#### Props
interface ProgressProps extends React.ComponentProps<typeof ProgressPrimitive.Root> {
  value?: number // 进度值，范围 0-100
  variant?: "blue" | "green" // 进度条颜色变体
}

#### Variants（变体）- 颜色 - 使用场景
- blue: 蓝色进度条 - 常规加载、数据传输、链接状态等通用场景，默认蓝色
- green: 绿色进度条 - 能量、环保、健康指标等积极场景

#### 样式特点
- 背景色: #C4CCD8 (浅灰色背景)
- 高度: 需要根据实际需求设置 (例如: h-[8px])，默认 15px
- 宽度: 需要根据实际需求设置 (例如: w-[600px])，默认 100%
- 圆角: 完全圆角 (rounded-full)

#### 使用示例
const [progress, setProgress] = useState(0);
<Progress value={progress} variant="green" className="h-[8px] w-full" />
*/
const progressVariants = cva("",
  {
    variants: {
      variant: {
        // 蓝色 - 常规加载、数据传输、链接状态
        blue: [
          "bg-blue-700",
        ],
        // 绿色 - 能量、环保、健康指标等积极场景
        green: [
          "bg-green-700",
        ],
      },
    },
    defaultVariants: {
      variant: "blue",
    },
  }
)

function Progress({
  className,
  value,
  variant = "blue", 
  ...props
}: React.ComponentProps<typeof ProgressPrimitive.Root> & {
  variant?: "blue" | "green"
}) {
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      className={cn(
        "bg-[#C4CCD8] dark:bg-[#202020] relative h-[15px] w-full overflow-hidden rounded-full",
        className
      )}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className={cn(
          progressVariants({ variant }),
          "h-full w-full flex-1 transition-all"
        )}
        style={{ transform: `translateX(-${100 - (value || 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  )
}

export { Progress }
