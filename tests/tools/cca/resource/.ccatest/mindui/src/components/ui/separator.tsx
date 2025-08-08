"use client"

import * as React from "react"
import * as SeparatorPrimitive from "@radix-ui/react-separator"

import { cn } from "@/lib/utils"
/* 
### Separator (separator.tsx)

基于 Radix UI Separator 组件进行定制，用于在内容之间创建视觉分隔。

#### 方向说明
- **horizontal**: 水平分隔线 - 用于垂直排列内容之间的分隔
- **vertical**: 垂直分隔线 - 用于水平排列内容之间的分隔

#### 样式特点
- **颜色**: rgba(0, 0, 0, 0.05) - 半透明黑色，适应各种背景
- **水平线**: 高度 2px，宽度 100%
- **垂直线**: 宽度 2px，高度 100%

#### 使用示例
水平分隔线（默认）：
<Separator />

垂直分隔线：
<Separator orientation="vertical" />
*/
const Separator = React.forwardRef<
  React.ElementRef<typeof SeparatorPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SeparatorPrimitive.Root>
>(
  (
    { className, orientation = "horizontal", decorative = true, ...props },
    ref
  ) => (
    <SeparatorPrimitive.Root
      ref={ref}
      decorative={decorative}
      orientation={orientation}
      className={cn(
        "shrink-0 bg-[#000000]/5 dark:bg-[#FFFFFF]/5",
        orientation === "horizontal" ? "h-[2px] w-full" : "h-full w-[2px]",
        className
      )}
      {...props}
    />
  )
)
Separator.displayName = SeparatorPrimitive.Root.displayName

export { Separator }
