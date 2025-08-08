import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"
// @ts-ignore
import "../../index.css"

const badgeVariants = cva(
  "inline-flex items-center justify-center border px-[20px] font-medium w-fit whitespace-nowrap shrink-0 [&>svg]:size-3 gap-1 [&>svg]:pointer-events-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive transition-[color,box-shadow] overflow-hidden w-auto h-auto",
  {
    variants: {
      variant: {
        // 默认格式：用于强调
        default:
          "border-transparent text-[#572F17] dark:text-[#CB8962] font-semibold !leading-[1.5] py-[7px]",
        // 强调格式：强调某一信息，用于影视、新闻封面
        highlight:
          "border-transparent font-bold text-white !leading-none py-[8px]",
        // 普通格式：用于普通主题
        normal: "border-transparent text-gray-500 !leading-[2.4]",
        // 弱格式：用于弱化主题
        weak: "border-gray-100 text-gray-500 border-2 !leading-[2.4]",
      },
      color: {
        default: "bg-[#D8C8C1] dark:bg-[#4D3F39]",
        // 用于highlight强调格式，表示热点，在variant为highlight时使用此color
        hot: "bg-[#FD2414]",
        // 用于highlight强调格式，表示VIP，在variant为highlight时使用此color
        vip: "bg-[#EBAC18]",
        // 用于highlight强调格式，表示自制内容，在variant为highlight时使用此color
        self: "bg-[#0A5BFC]",
        // 用于normal普通格式，表示普通内容，在variant为normal时使用此color
        normal: "bg-gray-50",
        // 用于weak弱化格式，表示弱化内容，在variant为weak时使用此color
        weak: "bg-opacity-100",
      },
      size: {
        default: "text-[24px] rounded-[10px]",
        small: "text-[20px] rounded-[10px]",
        large: "text-[28px] rounded-[14px]",
      },
    },
    defaultVariants: {
      variant: "default",
      color: "default",
      size: "default",
    },
  }
)

function Badge({
  className,
  variant = "default",
  color = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"span"> &
  VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : "span"
  // 防止模型生成不对，强制color值
  let realColor = color
  if (variant === "weak") {
    realColor = "weak"
  } else if (variant === "normal") {
    realColor = "normal"
  }

  return (
    <Comp
      data-slot="badge"
      className={cn(badgeVariants({ variant, color: realColor, size }), className)}
      {...props}
    />
  )
}

export { Badge, badgeVariants }
