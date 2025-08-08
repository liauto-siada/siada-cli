import React from "react";
import { cn } from "@/lib/utils";
import { cva } from "class-variance-authority";
import * as LucideIcons from "lucide-react";
import { motion } from "motion/react";
import vipTagSvg from "@/assets/img_audiobook_tag_vip.svg";
import "./horizontal-selector.css";

const selectorVariants = cva(
  "relative flex cursor-pointer touch-none select-none items-center w-full font-medium",
  {
    variants: {
      size: {
        xs: "h-[80px] p-[6px] rounded-[15px]",
        sm: "h-[100px] p-[7px] rounded-[15px]",
        md: "h-[110px] p-[8px] rounded-[15px]",
        lg: "h-[120px] p-[9px] rounded-[15px]",
        xl: "h-[140px] p-[10px] rounded-[20px]",
      },
    },
    defaultVariants: {
      size: "md",
    },
  },
);

// 按钮变体，移除颜色相关的类
const buttonVariants = cva(
  "flex items-center justify-center z-10 rounded-[10px] font-medium focus:outline-none",
  {
    variants: {
      size: {
        xs: "h-[65px] text-[20px]",
        sm: "h-[85px] text-[24px]",
        md: "h-[90px] text-[28px]",
        lg: "h-[100px] text-[32px]",
        xl: "h-[120px] text-[36px]",
      },
    },
  },
);

const sliderBackgroundVariants = cva("absolute rounded-[10px]", {
  variants: {
    size: {
      xs: "h-[65px]",
      sm: "h-[85px]",
      md: "h-[90px]",
      lg: "h-[100px]",
      xl: "h-[120px]",
    },
    color: {
      default: "bg-[rgba(255,255,255,0.4)] dark:bg-[#2C2E33]",
      primary: "bg-blue-600",
    },
  },
  defaultVariants: {
    color: "default",
  },
});

export type SizeVariant = "xs" | "sm" | "md" | "lg" | "xl";
export type ColorVariant = "default" | "primary";

export interface Option {
  label: string;
  value: string;
  disabled?: boolean;
  icon?: string;
  tag?: boolean;
}

export interface HorizontalSelectorProps {
  options: Option[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
  size?: SizeVariant;
  color?: ColorVariant;
}

interface DynamicLucideIconProps {
  iconName: string;
  className?: string;
}

const DynamicLucideIcon = ({ iconName, className }: DynamicLucideIconProps) => {
  const IconComponent = LucideIcons[
    iconName as keyof typeof LucideIcons
  ] as React.ComponentType<{ className?: string }>;

  if (!IconComponent) {
    console.warn(`Lucide icon "${iconName}" does not exist`);
    return null;
  }

  return <IconComponent className={className} />;
};

export default function HorizontalSelector({
  options,
  value,
  onChange,
  className,
  size = "xl",
  color = "default",
}: HorizontalSelectorProps) {
  const selectorRef = React.useRef<HTMLDivElement>(null);
  const selectedIndex = React.useMemo(
    () => options.findIndex((option) => option.value === value),
    [options, value],
  );

  const [sliderPosition, setSliderPosition] = React.useState({
    x: 0,
    width: 0,
  });

  // 触摸和鼠标滑动状态
  const [touchStart, setTouchStart] = React.useState<{
    x: number;
    y: number;
  } | null>(null);
  const [isSwiping, setIsSwiping] = React.useState(false);
  const [dragPosition, setDragPosition] = React.useState<{
    x: number;
  } | null>(null);

  // 当前被按下的按钮索引（包括点击和滑动过程中的按下）
  const [pressedButtonIndex, setPressedButtonIndex] = React.useState<
    number | null
  >(null);

  // 缩放动画状态 - 用于控制缩放动画的时机
  const [shouldScale, setShouldScale] = React.useState(false);

  // 获取按钮文本颜色的函数 - 使用 CSS 变量
  const getButtonTextColor = React.useCallback(
    (optionValue: string, isDisabled: boolean) => {
      if (isDisabled) {
        return "var(--horizontal-selector-disabled)";
      }

      const isSelected = value === optionValue;

      if (color === "primary") {
        return isSelected
          ? "var(--horizontal-selector-primary-selected)"
          : "var(--horizontal-selector-primary-unselected)";
      } else {
        // default color
        return isSelected
          ? "var(--horizontal-selector-default-selected)"
          : "var(--horizontal-selector-default-unselected)";
      }
    },
    [value, color],
  );

  // 计算当前拖拽位置是否与选中按钮位置相同
  const isAtSelectedPosition = React.useCallback(
    (dragX: number) => {
      if (selectedIndex === -1) return false;

      const selector = selectorRef.current;
      if (!selector) return false;

      const selectorRect = selector.getBoundingClientRect();
      const paddingLeft =
        parseInt(getComputedStyle(selector).paddingLeft, 10) || 0;
      const buttonWidth =
        (selectorRect.width - paddingLeft * 2) / options.length;
      const selectedButtonX = paddingLeft + selectedIndex * buttonWidth;

      // 允许一定的误差范围（比如5px）
      const tolerance = 5;
      return Math.abs(dragX - selectedButtonX) <= tolerance;
    },
    [selectedIndex, options.length],
  );

  // 更新滑块位置
  React.useEffect(() => {
    const updateSliderPosition = () => {
      const selector = selectorRef.current;
      if (!selector || selectedIndex === -1) return;

      const buttons = selector.querySelectorAll("button");
      const selectedButton = buttons[selectedIndex] as HTMLElement;
      if (!selectedButton) return;

      const selectorRect = selector.getBoundingClientRect();
      const buttonRect = selectedButton.getBoundingClientRect();
      const paddingLeft =
        parseInt(getComputedStyle(selector).paddingLeft, 10) || 0;
      const translateX = buttonRect.left - selectorRect.left - paddingLeft;

      // 使用 setState 来触发 Framer Motion 动画
      setSliderPosition({
        x: translateX,
        width: buttonRect.width,
      });
    };

    // 使用 requestAnimationFrame 确保 DOM 已更新
    const rafId = requestAnimationFrame(updateSliderPosition);
    return () => cancelAnimationFrame(rafId);
  }, [selectedIndex]);

  const handleOptionClick = React.useCallback(
    (optionValue: string, disabled?: boolean) => {
      if (!disabled) {
        onChange(optionValue);
      }
    },
    [onChange],
  );

  const handleKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;

      event.preventDefault();
      const enabledOptions = options.filter((option) => !option.disabled);
      const currentEnabledIndex = enabledOptions.findIndex(
        (option) => option.value === value,
      );

      if (currentEnabledIndex === -1) return;

      const direction = event.key === "ArrowLeft" ? -1 : 1;
      const nextIndex = Math.max(
        0,
        Math.min(enabledOptions.length - 1, currentEnabledIndex + direction),
      );

      if (nextIndex !== currentEnabledIndex) {
        onChange(enabledOptions[nextIndex].value);
      }
    },
    [options, value, onChange],
  );

  // 统一的事件开始处理函数
  const handlePointerStart = React.useCallback(
    (event: React.TouchEvent | React.MouseEvent) => {
      let clientX: number, clientY: number;

      if ("touches" in event) {
        // 触摸事件
        const touch = event.touches[0];
        clientX = touch.clientX;
        clientY = touch.clientY;
      } else {
        // 鼠标事件
        clientX = event.clientX;
        clientY = event.clientY;
      }

      setTouchStart({ x: clientX, y: clientY });
      setIsSwiping(false);
    },
    [],
  );

  // 计算按钮索引的辅助函数
  const getButtonIndexFromPosition = React.useCallback(
    (clientX: number) => {
      const selector = selectorRef.current;
      if (!selector) return null;

      const selectorRect = selector.getBoundingClientRect();
      const relativeX = clientX - selectorRect.left;
      const paddingLeft =
        parseInt(getComputedStyle(selector).paddingLeft, 10) || 0;
      const buttonWidth =
        (selectorRect.width - paddingLeft * 2) / options.length;

      // 检查是否在控件范围内
      if (
        relativeX >= paddingLeft &&
        relativeX <= selectorRect.width - paddingLeft
      ) {
        const buttonIndex = Math.floor((relativeX - paddingLeft) / buttonWidth);
        return Math.max(0, Math.min(options.length - 1, buttonIndex));
      }
      return null;
    },
    [options],
  );

  // 通用拖动处理函数
  const handleDragMove = React.useCallback(
    (clientX: number, clientY: number, preventDefault?: () => void) => {
      if (!touchStart) return;

      const deltaX = clientX - touchStart.x;
      const deltaY = clientY - touchStart.y;

      // 检查是否开始滑动（水平距离大于30px且水平移动大于垂直移动）
      if (Math.abs(deltaX) > 30 && Math.abs(deltaX) > Math.abs(deltaY)) {
        setIsSwiping(true);
        if (preventDefault) {
          preventDefault(); // 防止页面滚动
        }

        const buttonIndex = getButtonIndexFromPosition(clientX);
        if (buttonIndex !== null) {
          const selector = selectorRef.current;
          if (selector) {
            // 获取目标按钮的实际宽度
            const buttons = selector.querySelectorAll("button");
            const targetButton = buttons[buttonIndex] as HTMLElement;
            if (targetButton) {
              const buttonRect = targetButton.getBoundingClientRect();
              const selectorRect = selector.getBoundingClientRect();
              const paddingLeft =
                parseInt(getComputedStyle(selector).paddingLeft, 10) || 0;
              const translateX =
                buttonRect.left - selectorRect.left - paddingLeft;

              // 只更新拖动位置，不改变宽度
              setDragPosition({
                x: translateX,
              });
              setPressedButtonIndex(buttonIndex);

              // 检查是否在选中按钮位置，如果是则触发缩放
              if (isAtSelectedPosition(translateX)) {
                setShouldScale(true);
              } else {
                setShouldScale(false);
              }
            }
          }
        }
      }
    },
    [touchStart, getButtonIndexFromPosition, isAtSelectedPosition],
  );

  // 统一的事件处理函数
  const handlePointerMove = React.useCallback(
    (event: React.TouchEvent | React.MouseEvent) => {
      let clientX: number, clientY: number;
      let preventDefault: (() => void) | undefined;

      if ("touches" in event) {
        // 触摸事件
        const touch = event.touches[0];
        clientX = touch.clientX;
        clientY = touch.clientY;
        preventDefault = () => event.preventDefault();
      } else {
        // 鼠标事件
        clientX = event.clientX;
        clientY = event.clientY;
      }

      handleDragMove(clientX, clientY, preventDefault);
    },
    [handleDragMove],
  );

  // 统一的事件结束处理函数
  const handlePointerEnd = React.useCallback(() => {
    if (dragPosition && pressedButtonIndex !== null) {
      // 直接使用当前按下的按钮索引
      onChange(options[pressedButtonIndex].value);
    }

    setTouchStart(null);
    setIsSwiping(false);
    setPressedButtonIndex(null);

    // 拖拽结束后恢复原来大小
    setShouldScale(false);

    // 延迟清空 dragPosition，让位置动画平滑过渡
    setTimeout(() => {
      setDragPosition(null);
    }, 5); // 给足够时间让位置动画完成
  }, [dragPosition, pressedButtonIndex, options, onChange]);

  // 全局事件处理
  React.useEffect(() => {
    const handleGlobalMouseMove = (event: MouseEvent) => {
      if (touchStart) {
        handleDragMove(event.clientX, event.clientY);
      }
    };

    const handleGlobalMouseUp = (event: MouseEvent) => {
      // 确保在区域外抬手时也能正确清理状态
      if (touchStart || isSwiping || pressedButtonIndex !== null) {
        handlePointerEnd();
        // 清理点击状态
        setPressedButtonIndex(null);
      }
    };

    const handleGlobalTouchMove = (event: TouchEvent) => {
      if (touchStart) {
        const touch = event.touches[0];
        handleDragMove(touch.clientX, touch.clientY);
      }
    };

    const handleGlobalTouchEnd = (event: TouchEvent) => {
      // 确保在区域外抬手时也能正确清理状态
      if (touchStart || isSwiping || pressedButtonIndex !== null) {
        handlePointerEnd();
        // 清理点击状态
        setPressedButtonIndex(null);
      }
    };

    if (touchStart) {
      document.addEventListener("mousemove", handleGlobalMouseMove);
      document.addEventListener("mouseup", handleGlobalMouseUp);
      document.addEventListener("touchmove", handleGlobalTouchMove, {
        passive: false,
      });
      document.addEventListener("touchend", handleGlobalTouchEnd);
    }

    return () => {
      document.removeEventListener("mousemove", handleGlobalMouseMove);
      document.removeEventListener("mouseup", handleGlobalMouseUp);
      document.removeEventListener("touchmove", handleGlobalTouchMove);
      document.removeEventListener("touchend", handleGlobalTouchEnd);
    };
  }, [
    touchStart,
    isSwiping,
    pressedButtonIndex,
    options,
    dragPosition,
    onChange,
    handleDragMove,
    handlePointerEnd,
  ]);

  return (
    <div
      ref={selectorRef}
      className={cn(
        selectorVariants({ size }),
        "bg-slate-300 shadow-sm dark:bg-[#222428]",
        className,
      )}
      onKeyDown={handleKeyDown}
      onTouchStart={handlePointerStart}
      onTouchMove={handlePointerMove}
      onTouchEnd={handlePointerEnd}
      onMouseDown={handlePointerStart}
      onMouseMove={handlePointerMove}
      onMouseUp={handlePointerEnd}
      tabIndex={0}
      role="radiogroup"
      aria-label="Horizontal Selector"
    >
      {/* 滑块背景 - 在按钮下方 */}
      <motion.div
        className={cn(sliderBackgroundVariants({ size, color }))}
        animate={{
          x: dragPosition ? dragPosition.x : sliderPosition.x,
          width: sliderPosition.width,
          scale: shouldScale ? 0.9 : 1,
          opacity: shouldScale ? 0.7 : 1,
        }}
        transition={{
          x: {
            type: "spring",
            stiffness: 299.619,
            damping: 34.45,
            mass: 1,
          },
          scale: {
            type: "spring",
            stiffness: 405.823,
            damping: 26.87,
            mass: 1,
          },
          opacity: {
            type: "spring",
            stiffness: 405.823,
            damping: 26.87,
            mass: 1,
          },
        }}
      />

      {/* 按钮容器 - 在滑块上方 */}
      <div className="pointer-events-none relative z-10 flex w-full">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={cn(
              buttonVariants({ size }),
              "pointer-events-auto relative flex-1 whitespace-nowrap transition-colors",
              option.disabled && "cursor-not-allowed opacity-50",
            )}
            onClick={() => handleOptionClick(option.value, option.disabled)}
            onMouseDown={() => {
              if (!option.disabled) {
                setPressedButtonIndex(options.indexOf(option));
                // 如果点击的是当前选中的按钮，触发缩放
                if (value === option.value) {
                  setShouldScale(true);
                }
              }
            }}
            onMouseUp={() => {
              if (!option.disabled) {
                setTimeout(() => {
                  setPressedButtonIndex(null);
                  // 松开后恢复原来大小
                  setShouldScale(false);
                }, 5);
              }
            }}
            onTouchStart={() => {
              if (!option.disabled) {
                setPressedButtonIndex(options.indexOf(option));
                // 如果触摸的是当前选中的按钮，触发缩放
                if (value === option.value) {
                  setShouldScale(true);
                }
              }
            }}
            onTouchEnd={() => {
              if (!option.disabled) {
                setTimeout(() => {
                  setPressedButtonIndex(null);
                  // 松开后恢复原来大小
                  setShouldScale(false);
                }, 5);
              }
            }}
            disabled={option.disabled}
            role="radio"
            aria-checked={value === option.value}
            tabIndex={-1}
          >
            <motion.div
              className="flex items-center justify-center gap-3"
              animate={{
                scale: pressedButtonIndex === options.indexOf(option) ? 0.9 : 1,
                color: getButtonTextColor(option.value, !!option.disabled),                
              }}
              transition={{
                scale: {
                  type: "spring",
                  stiffness: 405.823,
                  damping: 26.87,
                  mass: 1,
                },
                color: {
                  ease: [0.61, 1, 0.88, 1],
                  duration: 0.3,
                },
              }}
            >
              {option.icon && (
                <DynamicLucideIcon
                  iconName={option.icon}
                  className="h-[36px] w-[36px] flex-shrink-0"
                />
              )}
              <div className="relative flex justify-center">
                <span>{option.label}</span>
                {option.tag && (
                  <img
                    src={vipTagSvg}
                    alt="VIP"
                    className="pointer-events-none absolute top-0 left-full h-[16px] w-[49px] flex-shrink-0"
                  />
                )}
              </div>
            </motion.div>
          </button>
        ))}
      </div>
    </div>
  );
}
