import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const iconButtonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap transition-all duration-300 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        // 常态 - 使用次要按钮颜色 #A9B2C7 30%
        default: [
          "bg-[#A9B2C7]/30 text-black hover:bg-[#A9B2C7]/40",
          "disabled:bg-[#A9B2C7]/30 disabled:text-black disabled:hover:bg-[#A9B2C7]/30"
        ],
      },
      size: {
        // 纯图标按钮尺寸
        "120": "w-[120px] h-[120px] rounded-[20px] [&_svg]:size-[64px]",
        "140": "w-[140px] h-[140px] rounded-[20px] [&_svg]:size-[74px]",
        
        // 图标+文案按钮尺寸 - 对应默认尺寸(1-5)
        // 默认尺寸（1）：icon与文字间距：10PX 按钮圆角：10PX 最小边距：30PX
        xs: "h-[80px] px-[30px] rounded-[10px] text-[28px] font-medium gap-[10px] [&_svg]:size-[28px]",
        // 默认尺寸（2）：icon与文字间距：15PX 按钮圆角：15PX 最小边距：40PX  
        sm: "h-[100px] px-[40px] rounded-[15px] text-[32px] font-medium gap-[15px] [&_svg]:size-[32px]",
        // 默认尺寸（3）：icon与文字间距：15PX 按钮圆角：15PX 最小边距：40PX
        md: "h-[110px] px-[40px] rounded-[15px] text-[32px] font-medium gap-[15px] [&_svg]:size-[32px]",
        // 默认尺寸（4）：icon与文字间距：20PX 按钮圆角：15PX 最小边距：50PX
        lg: "h-[120px] px-[50px] rounded-[15px] text-[36px] font-medium gap-[20px] [&_svg]:size-[36px]",
        // 默认尺寸（5）：icon与文字间距：20PX 按钮圆角：15PX 最小边距：50PX
        xl: "h-[140px] px-[50px] rounded-[15px] text-[36px] font-medium gap-[20px] [&_svg]:size-[36px]",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "120",
    },
  }
)

export interface IconButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof iconButtonVariants> {
  asChild?: boolean;
  // 是否处于加载状态
  loading?: boolean;
  // 图标元素
  icon?: React.ReactNode;
  // 文案内容（用于图标+文案按钮）
  children?: React.ReactNode;
}

const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ 
    className, 
    variant = "default",
    size = "120", 
    asChild = false, 
    loading = false,
    onClick,
    disabled,
    icon,
    children,
    ...props 
  }, ref) => {
    // 点击动画状态
    const [isClicking, setIsClicking] = React.useState(false);
    
    const handleClick = (event: React.MouseEvent<HTMLButtonElement>) => {
      if (disabled || loading) return;
      
      // 触发点击动画 - 缩小90%
      setIsClicking(true);
      setTimeout(() => setIsClicking(false), 200);
      
      // 调用外部onClick
      onClick?.(event);
    };

    // 加载图标组件
    const LoadingIcon = () => {
      // 根据尺寸调整loading图标大小
      const iconSize = size === "120" ? "size-[64px]" : 
                       size === "140" ? "size-[74px]" : 
                       size === "xs" ? "size-[28px]" :
                       size === "sm" || size === "md" ? "size-[32px]" :
                       "size-[36px]";
      
      return (
        <svg 
          className={cn("animate-spin", iconSize)} 
          viewBox="0 0 24 24" 
          fill="none" 
          xmlns="http://www.w3.org/2000/svg"
        >
          <circle 
            cx="12" 
            cy="12" 
            r="10" 
            stroke="currentColor" 
            strokeWidth="2" 
            strokeLinecap="round" 
            strokeDasharray="31.416" 
            strokeDashoffset="31.416"
          >
            <animate 
              attributeName="stroke-dasharray" 
              dur="2s" 
              values="0 31.416;15.708 15.708;0 31.416;0 31.416" 
              repeatCount="indefinite"
            />
            <animate 
              attributeName="stroke-dashoffset" 
              dur="2s" 
              values="0;-15.708;-31.416;-31.416" 
              repeatCount="indefinite"
            />
          </circle>
        </svg>
      );
    };

    // 判断是否为纯图标按钮
    const isIconOnly = size === "120" || size === "140";

    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(
          iconButtonVariants({ variant, size, className }),
          // 点击动画 - 缩小90%
          isClicking && "scale-90",
          // 加载状态时禁用指针事件
          loading && "pointer-events-none"
        )}
        ref={ref}
        onClick={handleClick}
        disabled={disabled || loading}
        {...props}
      >
        {loading ? (
          <LoadingIcon />
        ) : isIconOnly ? (
          // 纯图标按钮只显示图标
          icon
        ) : (
          // 图标+文案按钮显示图标和文案
          <>
            {icon}
            {children}
          </>
        )}
      </Comp>
    )
  }
)
IconButton.displayName = "IconButton"

export { IconButton, iconButtonVariants } 