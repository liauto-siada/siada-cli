import * as React from "react"
import * as SwitchPrimitive from "@radix-ui/react-switch"
import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import { cva, type VariantProps } from "class-variance-authority"

const SwitchVariants = cva(
  "peer relative inline-flex items-center rounded-sm border border-transparent shadow-xs transition-all outline-none focus-visible:ring-[3px] focus-visible:border-ring focus-visible:ring-ring/50",
  {
    variants: {
      size: {
        xs: "h-[80px] max-w-[233px] px-[30px] rounded-[20px] text-[28px] font-medium",
        sm: "h-[100px] max-w-[266px] px-[40px] rounded-[20px] text-[32px] font-medium",
        md: "h-[110px] max-w-[266px] px-[40px] rounded-[20px] text-[32px] font-medium",
        lg: "h-[120px] max-w-[310px] px-[50px] rounded-[20px] text-[36px] font-medium",
        xl:  "h-[140px] max-w-[310px] px-[50px] rounded-[20px] text-[36px] font-medium",
      },
    },
    defaultVariants: {
      size: "md",
    },
  }
)

const ThumbVariants = cva(
  "pointer-events-none block absolute left-1/2 ring-0 transition-transform",
  {
    variants: {
      size: {
        xs: "h-[40px] w-[20px] rounded-[5px]",
        sm: "h-[60px] w-[20px] rounded-[5px]",
        md: "h-[70px] w-[20px] rounded-[5px]",
        lg: "h-[80px] w-[20px] rounded-[5px]",
        xl:  "h-[100px] w-[20px] rounded-[5px]",
      },
    },
    defaultVariants: {
      size: "md",
    },
  }
)

const LoadingVariants = (size: SwitchProps["size"]) => {
  switch (size) {
    case "xs":
      return 80;
    case "sm":
      return 100;
    case "md":
      return 110;
    case "lg":
      return 120;
    case "xl":
      return 140;
    default:
      return 110;
  }
}

export interface SwitchProps
  extends React.ComponentProps<typeof SwitchPrimitive.Root> {
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
  disabled?: boolean
  loading?: boolean
  size?: "xs" | "sm" | "md" | "lg" | "xl"
}

function Switch({
  className,
  checked,
  onCheckedChange,
  disabled = false,
  loading = false,
  size = "md",
  ...props
}: SwitchProps & { size?: "xs" | "sm" | "md" | "lg" | "xl" }) {
  const isInteractive = !disabled && !loading
  const effectiveDisabled = disabled || loading

  return (
<SwitchPrimitive.Root
  checked={checked}
  onCheckedChange={val => {
    if (!isInteractive) return
    onCheckedChange?.(val)
  }}
  disabled={effectiveDisabled}
  data-slot="switch"
  className={cn(
    "w-full",
    SwitchVariants({ size }),
    checked ? "bg-blue-600" : "bg-gray-300 opacity-70",
    className
  )}
  {...props}
>
  {/* 原始 Thumb */}
  {!loading && (
    <SwitchPrimitive.Thumb
      data-slot="switch-thumb"
      className={cn(
        //"pointer-events-none block h-3 w-1 rounded-[0.5px] ring-0 transition-transform",
        ThumbVariants({ size }),
        "left-[12%] top-1/2 -translate-y-1/2",
        checked 
          ? "left-[88%] -translate-x-full" 
          : "left-[12%] -translate-x-0",
        effectiveDisabled && "opacity-50 cursor-not-allowed",
        loading ? "bg-transparent" : "bg-background dark:bg-foreground"
      )}
      style={{ transition: 'none'}}
    />
  )}

  {/* 加载动画层 */}
  {loading && (
    <div
      className={cn(
        "absolute inset-0 flex items-center justify-center",
        checked ? "translate-x-[30%]" : "-translate-x-[30%]",
        "transition-transform duration-200 ease-out"
      )}
    >
      <Loader2 className="animate-spin text-white opacity-50" 
      style={{
        height: `${LoadingVariants(size) * 0.5}px`, // 根据需要比例缩放
        width: `${LoadingVariants(size) * 0.5}px`,
      }}
      strokeWidth={4} />
    </div>
  )}
</SwitchPrimitive.Root>
  )
}

export { Switch }
