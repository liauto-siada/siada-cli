import * as React from "react"
import * as SliderPrimitive from "@radix-ui/react-slider"
import { cn } from "@/lib/utils"
import { BatteryFull, BatteryLow, Sun } from "lucide-react"

import { cva } from "class-variance-authority"

const sliderVariants = cva("relative flex items-center", {
  variants: {
    size: {
      xs: "h-[80px] rounded-[20px] text-[28px] font-medium",
      sm: "h-[100px] rounded-[20px] text-[32px] font-medium",
      md: "h-[110px] rounded-[20px] text-[32px] font-medium",
      lg: "h-[120px] rounded-[20px] text-[36px] font-medium",
      xl:  "h-[140px] rounded-[20px] text-[36px] font-medium",
    },
  },
  defaultVariants: {
    size: "md",
  },
})

const rootVariants = cva("relative flex cursor-pointer touch-none select-none items-center", {
  variants: {
    size: {
      xs: "h-[80px] rounded-[20px] text-[28px] font-medium",
      sm: "h-[100px] rounded-[20px] text-[32px] font-medium",
      md: "h-[110px] rounded-[20px] text-[32px] font-medium",
      lg: "h-[120px] rounded-[20px] text-[36px] font-medium",
      xl:  "h-[140px] rounded-[20px] text-[36px] font-medium",
    },
  },
})

const trackVariants = cva("relative bg-gray-300", {
  variants: {
    size: {
      xs: "h-[80px] px-[50px] rounded-[20px] text-[28px] font-medium",
      sm: "h-[100px] px-[50px] rounded-[20px] text-[32px] font-medium",
      md: "h-[110px] px-[50px] rounded-[20px] text-[32px] font-medium",
      lg: "h-[120px] px-[60px] rounded-[20px] text-[36px] font-medium",
      xl: "h-[140px] px-[60px] rounded-[20px] text-[36px] font-medium",
    },
  },
})

const thumbVariants = cva("bg-white text-black flex items-center justify-center shadow-sm overflow-hidden whitespace-nowrap text-ellipsis", {
  variants: {
    size: {
      xs: "h-[65px] w-[120px] px-[50px] rounded-[20px] text-[28px] font-medium",
      sm: "h-[85px] w-[140px] px-[50px] rounded-[20px] text-[32px] font-medium",
      md: "h-[90px] w-[160px] px-[50px] rounded-[20px] text-[32px] font-medium",
      lg: "h-[100px] w-[170px] px-[60px] rounded-[20px] text-[36px] font-medium",
      xl: "h-[120px] w-[180px] px-[60px] rounded-[20px] text-[36px] font-medium",
    },
  },
})

type SliderMode = "blur" | "precise"
type SliderSize = "xs" | "sm" | "md" | "lg" | "xl"

export function BrightnessSlider({
  className,
  defaultValue = [50],
  value,
  onValueChange,
  mode = "blur",
  size = "md",
  iconStart,
  iconEnd,
  formatLabel,
  ...props
}: React.ComponentProps<typeof SliderPrimitive.Root> & {
  formatLabel?: (value: number | number[]) => React.ReactNode
  mode?: SliderMode
  size?: SliderSize
  iconStart?: React.ReactNode
  iconEnd?: React.ReactNode
}) {
  const sliderValue = Array.isArray(value) ? value[0] : Array.isArray(defaultValue) ? defaultValue[0] : 50
  // const percentage = `${sliderValue}%`

  // ==== blur 模式保持不变 ====
  if (mode === "blur") {
    return (
      <div className={cn("relative flex items-center justify-start w-full", sliderVariants({ size }), className)}>
        <div className="relative w-full">
          <SliderPrimitive.Root
            defaultValue={defaultValue}
            value={value}
            onValueChange={onValueChange}
            step={1}
            className={cn(rootVariants({ size }), "w-full")}
            {...props}
          >
            <SliderPrimitive.Track className={cn(trackVariants({ size }), "overflow-hidden rounded-[inherit] w-full")}>
              <div className="absolute left-4 top-1/2 -translate-y-1/2 z-10">
                {iconStart ?? <Sun className="text-gray-500" size={28} />}
                {/* <Sun className="text-gray-500" size={28} /> */}
              </div>
              <SliderPrimitive.Range className="absolute h-full bg-white" />
            </SliderPrimitive.Track>
          </SliderPrimitive.Root>
        </div>
      </div>
    )
  }

  // ==== precise 模式 ====
  return (
    <div className={cn("relative flex items-center justify-start w-full", sliderVariants({ size }), className)}>
      <SliderPrimitive.Root
        defaultValue={defaultValue}
        value={value}
        onValueChange={onValueChange}
        step={1}
        className={cn(rootVariants({ size }), "w-full")}
        {...props}
      >
        <SliderPrimitive.Track 
          className={cn(trackVariants({ size }), 
          "overflow-hidden relative w-full")}
          style={{ paddingLeft: '50px', paddingRight: '50px' }}
        >
          <div className="absolute left-4 top-1/2 -translate-y-1/2 z-10">
            {iconStart ?? <BatteryLow className="text-gray-500" size={28} />}
            {/* <BatteryLow className="text-gray-500" size={28} /> */}
          </div>
          <div className="absolute right-4 top-1/2 -translate-y-1/2 z-10">
            {iconEnd ?? <BatteryFull className="text-gray-500" size={28} />}
            {/* <BatteryFull className="text-gray-500" size={28} /> */}
          </div>
          <SliderPrimitive.Range className="absolute h-full bg-gray-300 rounded-[inherit]" />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb className={thumbVariants({ size })}>
          {formatLabel ? formatLabel(value ?? defaultValue) : value ?? defaultValue}
        </SliderPrimitive.Thumb>
      </SliderPrimitive.Root>
    </div>
  )
}
