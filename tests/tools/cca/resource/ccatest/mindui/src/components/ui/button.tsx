import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"
import "./button.css"
import { LoadingIcon } from "@/components/mindui/loading"
import TapBox from "@/gesture_animation/GestureBox"
/* 
### Button (button.tsx)

基于 shadcn Button 组件进行了大幅定制，支持多种变体和尺寸。

#### Props
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "activated" | "primary" | "secondary" | "warning" | "ghost" | "text"
  size?: "xs" | "sm" | "md" | "lg" | "xl"
  asChild?: boolean
  loading?: boolean
  // 图标，如果有图标则会在文字前显示，纯图标按钮都为圆形
  icon?: React.ReactNode;
  // 是否为开关按钮，默认状态根据传入的 isToggled 是否为 true 决定，当设置了 isToggled 时，variant 的设置会失效，按钮会根据当前状态自动切换样式，开启时使用 activated 变体，关闭时使用 secondary 变体
  isToggled?: boolean; 
}

#### Variants（变体）- 基础颜色（包含透明度） - 使用场景
- activated: 激活按钮 - 蓝色 100% - 页面/弹窗中确认开启的按钮  例：设置内功能开启按钮
- primary: 主要按钮 - 深灰色 80% - 页面/弹窗中的主要功能    例：弹窗的确认按钮
- secondary: 次要按钮 - 浅灰色 30% -  页面/弹窗中同时存在两个按钮的次要功能    例：弹窗的取消按钮
- warning: 警示按钮 - 红色 100% - 如果某个操作可能存在风险，可以使用警示色来强调。例如"删除"
- ghost: 幽灵按钮 - 浅灰色 30% 描边（宽度 2px） - 页面/弹窗中比较次要的/需要弱化按钮    例：播放页的选集按钮
- text: 文本按钮 - 蓝色 100% - 适用场景：协议入口

#### Sizes（尺寸,已经包含内边距，圆角，文字大小，因此样式不需要重新设置，宽度可以根据实际需要设置样式）
- xs: 高度80px
- sm: 高度100px
- md: 高度110px
- lg: 高度120px
- xl: 高度140px

#### 特殊状态
- loading: 显示旋转loading图标
- 点击动画: 点击时缩放到90%，持续200ms，同时日间加#222732 10% 蒙层，夜间加#FFFFFF 10% 蒙层
- 禁用状态: 除危险按钮外，文字颜色使用对应日夜间文本失效色值；【警示按钮不可用】同日夜间次要按钮不可用样式

#### 使用示例
图标+文字按钮：
<Button variant="primary" size="md" loading={false} icon={<Icon />} onClick={handleClick}>确认</Button>
纯图标圆形按钮：
<Button size="lg" icon={<Home />} />
开关按钮：
const [isToggled1, setIsToggled1] = React.useState(true);
<Button isToggled={isToggled1} onClick={() => setIsToggled1(!isToggled1)}>默认开启状态的开关按钮</Button>
*/

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap focus-visible:outline-none disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0 transition-all duration-300",
  {
    variants: {
      variant: {
        // 激活按钮 
        activated: [
          "bg-(--color-button-activated) text-(--color-button-text-activated)",
          "disabled:bg-(--color-button-activated-disable) disabled:text-(--color-button-text-activated-disable)"
        ],
        
        // 主要按钮
        primary: [
          "bg-(--color-button-primary) text-(--color-button-text-primary)",
          "disabled:bg-(--color-button-primary-disable) disabled:text-(--color-button-text-primary-disable)"
        ],
        
        // 次要按钮
        secondary: [
          "bg-(--color-button-secondary) text-(--color-button-text-secondary)",
          "disabled:bg-(--color-button-secondary-disable) disabled:text-(--color-button-text-secondary-disable)"
        ],
        
        // 警示按钮
        warning: [
          "bg-(--color-button-warning) text-(--color-button-text-warning)",
          "disabled:bg-(--color-button-warning-disable) disabled:text-(--color-button-text-warning-disable)"
        ],
        
        // 幽灵按钮（描边：2）
        ghost: [
          "text-(--color-button-text-secondary) border-2 border-(--color-button-secondary)",
          "disabled:text-(--color-button-text-secondary-disable)"
        ],
        
        // 文本按钮
        text: [
          "text-(--color-button-text-link)",
          "disabled:text-(--color-button-text-link-disable)",
          "active:text-(--color-button-text-link-tap)",
        ],
      },
      size: {
        // 按钮尺寸
        xs: "h-[80px] px-[30px] rounded-[10px] text-[28px] font-medium gap-[10px] [&_svg]:h-[40px]",
        sm: "h-[100px] px-[40px] rounded-[15px] text-[32px] font-medium gap-[15px] [&_svg]:h-[48px]",
        md: "h-[110px] px-[40px] rounded-[15px] text-[32px] font-medium gap-[15px] [&_svg]:h-[48px]",
        lg: "h-[120px] px-[50px] rounded-[15px] text-[36px] font-medium gap-[20px] [&_svg]:h-[52px]",
        xl: "h-[140px] px-[50px] rounded-[15px] text-[36px] font-medium gap-[20px] [&_svg]:h-[52px]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  // 是否处于加载状态
  loading?: boolean;
  // 图标元素
  icon?: React.ReactNode;
  // 是否为开关按钮，默认状态是否为开启
  isToggled?: boolean; 
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ 
    className, 
    variant = "primary", 
    size = "md", 
    asChild = false, 
    loading = false,
    isToggled,
    disabled,
    icon,
    children,
    onClick,
    ...props 
  }, ref) => {
    // 根据切换状态决定当前变体
    const currentVariant = isToggled !== undefined ? (isToggled ? "activated" : "secondary") : variant;
    const DivRef = React.useRef<HTMLDivElement>(null);
    const [compWidth, setCompWidth] = React.useState<number>(0);

    React.useEffect(() => {
      if (DivRef.current) {
        setCompWidth(DivRef.current.offsetWidth);
      }
    }, [children, icon, size]);
    // 根据按钮变体选择对应的加载图标
    const getLoadingIconColor = () => {
      switch (variant) {
        case "primary":
          return "var(--color-button-text-primary)";
        case "activated":
          return "var(--color-button-text-activated)";
        case "warning":
          return "var(--color-button-text-warning)";
        case "secondary":
        case "ghost":
          return "var(--color-button-text-secondary)";
        case "text":
          return "var(--color-button-text-link)";
        default:
          return "var(--color-button-text-primary)";
      }
    };

    // 根据按钮尺寸选择对应的图标大小
    const getLoadingIconSize = () => {
      const paddingRatio = 0.77
      switch (size) {
        case "xs":
          return 40 * paddingRatio;
        case "sm":
        case "md":
          return 48 * paddingRatio;
        case "lg":
        case "xl":
          return 52 * paddingRatio;
        default:
          return 48 * paddingRatio;
      }
    };
    // 根据按钮尺寸选择对应的间距大小
    const getGapSize = () => {
      switch (size) {
        case "xs":
          return "gap-[10px]";
        case "sm":
        case "md":
          return "gap-[15px]";
        case "lg":
        case "xl":
          return "gap-[20px]";
        default:
          return "gap-[15px]";
      }
    };
    // 根据按钮尺寸选择对应的高度
    const getWidth = () => {
      switch (size) {
        case "xs":
          return "w-[80px]";
        case "sm":
          return "w-[100px]";
        case "md":
          return "w-[110px]";
        case "lg":
          return "w-[120px]";
        case "xl":
          return "w-[140px]";
        default:
          return "w-[110px]";
      }
    };
    // 根据按钮尺寸选择对应的高度
    const getHeight = () => {
      switch (size) {
        case "xs":
          return "h-[80px]";
        case "sm":
          return "h-[100px]";
        case "md":
          return "h-[110px]";
        case "lg":
          return "h-[120px]";
        case "xl":
          return "h-[140px]";
        default:
          return "h-[110px]";
      }
    };
    // 根据按钮尺寸选择对应的圆角尺寸
    const getBorderRadius = () => {
      switch (size) {
        case "xs":
          return "rounded-[10px]";
        default:
          return "rounded-[15px]";
      }
    };

    // 根据按钮尺寸选择对应的缩放尺寸
    const getScale = () => {
      var wholeWidth = compWidth
      switch (size) {
        case "xs":
          wholeWidth += 60;
          break
        case "sm":
        case "md":
          wholeWidth += 80;
          break
        case "lg":
        case "xl":
          wholeWidth += 100;
          break
        default:
          wholeWidth += 80;
      }
      if (wholeWidth <= 150) {
        return 0.85
      } else if (wholeWidth >= 600) {
        return 0.95
      } else {
        return 0.85 + (wholeWidth - 150) * (0.1 / 450)
      }
    };

    const Comp = asChild ? Slot : "button"
    return (
      <TapBox
        borderRadius={children ? getBorderRadius() : "rounded-full"}
        disabled={disabled || loading}
        scale={getScale()}
        mask={variant !== "text"} // 文本按钮不需要背景点击蒙层
        onClick={onClick}
        className={cn(
          className,
          `${getHeight()}`,
        )}
        {...props}
      >
        <Comp
          className={cn(
            buttonVariants({ variant: currentVariant, size }),
            "w-full",
            // 加载状态时禁用指针事件
            loading && "pointer-events-none",
            // 如果是纯图标按钮，则设置圆形样式
            !children && `rounded-full ${getWidth()}`,
          )}
          ref={ref}
          disabled={disabled}
          {...props}
        >
          {loading ? (
            <div className="relative">
              <div className={`invisible flex ${getGapSize()}`}>
                {icon}
                {children}
              </div>
              <div className="absolute inset-0 flex items-center justify-center">
                <LoadingIcon size={getLoadingIconSize()} color={getLoadingIconColor()} />
              </div>
            </div>
          ) : (
            <div ref={DivRef} className={`flex ${getGapSize()} w-full justify-center items-center`}>
              {icon}
              {children}
            </div>
          )}
        </Comp>
      </TapBox>
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
