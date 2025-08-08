import React, { useState, useEffect, useRef, useCallback } from "react";
import { cn } from "@/lib/utils";

interface ImageProps
  extends Omit<React.ImgHTMLAttributes<HTMLImageElement>, "src"> {
  /** 图片URL */
  url: string;
  /**
   * 图片适配模式
   * - "natural": 保持图片原始比例，自然适配
   * - "standard": 约束到标准比例（1:1、4:3、16:9）
   */
  fit?: "natural" | "standard";
  className?: string;
}

// 标准比例值
const STANDARD_RATIOS = [1, 4 / 3, 16 / 9];

const MAX_HEIGHT = 1050;
const RATIO_TOLERANCE = 0.1; // 10% 误差

// 工具函数 - 提取到组件外部避免重复创建
const findClosestRatio = (actualRatio: number) => {
  let closestRatio = STANDARD_RATIOS[0];
  let minDifference = Infinity;

  STANDARD_RATIOS.forEach((ratio) => {
    const difference = Math.abs((actualRatio - ratio) / ratio);
    if (difference < minDifference) {
      minDifference = difference;
      closestRatio = ratio;
    }
  });

  return { ratio: closestRatio, difference: minDifference };
};

const isValidRatio = (width: number, height: number): boolean => {
  if (width <= 0 || height <= 0) return false;
  const actualRatio = width / height;
  const { difference } = findClosestRatio(actualRatio);
  return difference <= RATIO_TOLERANCE;
};

export const Image = React.forwardRef<HTMLImageElement, ImageProps>(
  ({ url, fit = "natural", className, ...props }, ref) => {
    const [isVisible, setIsVisible] = useState(false);
    const [imageStyle, setImageStyle] = useState<React.CSSProperties>({});
    const imgRef = useRef<HTMLImageElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);

    // 计算图片样式
    const calculateImageStyle = useCallback(
      (
        naturalWidth: number,
        naturalHeight: number,
        containerWidth: number,
        containerHeight: number,
      ) => {
        // 检查输入有效性
        if (naturalWidth <= 0 || naturalHeight <= 0 || containerWidth <= 0) {
          return null;
        }

        // 在标准比例模式下，容器高度也必须有效
        if (fit === "standard" && containerHeight <= 0) {
          return null;
        }

        if (fit === "standard") {
          // 标准比例模式：约束到标准比例并适配容器
          if (!isValidRatio(naturalWidth, naturalHeight)) {
            return null; // 比例不符合要求
          }

          const actualRatio = naturalWidth / naturalHeight;
          const { ratio } = findClosestRatio(actualRatio);

          // 按照目标比例适配容器，保证不超出边界
          let finalWidth = containerWidth;
          let finalHeight = containerWidth / ratio;

          // 如果高度超出，改为用满高度
          if (finalHeight > containerHeight) {
            finalHeight = containerHeight;
            finalWidth = containerHeight * ratio;
          }

          return {
            width: finalWidth,
            height: finalHeight,
            objectFit: "cover" as const,
          };
        } else {
          // 自然模式：保持图片原始比例
          const aspectRatio = naturalWidth / naturalHeight;
          const targetHeight = containerWidth / aspectRatio;

          if (targetHeight > MAX_HEIGHT) {
            return null; // 高度超过限制
          }

          return {
            width: containerWidth,
            height: targetHeight,
            objectFit: "contain" as const,
          };
        }
      },
      [fit],
    );

    // 处理图片加载完成
    const handleImageLoad = useCallback(() => {
      const img = imgRef.current;
      const container = containerRef.current;

      if (!img || !container) {
        setIsVisible(false);
        return;
      }

      const { naturalWidth, naturalHeight } = img;
      const containerWidth = container.offsetWidth;
      const containerHeight = container.offsetHeight;

      const style = calculateImageStyle(
        naturalWidth,
        naturalHeight,
        containerWidth,
        containerHeight,
      );

      if (style) {
        setImageStyle(style);
        setIsVisible(true);
      } else {
        setIsVisible(false);
      }
    }, [calculateImageStyle]);

    // 处理图片加载失败
    const handleImageError = () => {
      setIsVisible(false);
      setImageStyle({});
    };

    // 合并 ref
    const mergedRef = useCallback(
      (el: HTMLImageElement | null) => {
        imgRef.current = el;

        if (typeof ref === "function") {
          ref(el);
        } else if (ref) {
          ref.current = el;
        }
      },
      [ref],
    );

    // URL 或配置变化时重置状态
    useEffect(() => {
      setIsVisible(false);
      setImageStyle({});
    }, [url, fit]);

    return (
      <div
        ref={containerRef}
        className={cn(className, "flex h-full w-full items-center overflow-hidden rounded-xl")}
      >
        <img
          ref={mergedRef}
          src={url}
          onLoad={handleImageLoad}
          onError={handleImageError}
          style={{
            ...imageStyle,
            display: isVisible ? "block" : "none",
          }}
          alt=""
          {...props}
        />
      </div>
    );
  },
);

Image.displayName = "Image";
