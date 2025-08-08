"use client"

import * as React from "react"
import * as AvatarPrimitive from "@radix-ui/react-avatar"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

// 定义支持的比例类型
type AspectRatio = "16:9" | "9:16" | "3:4" | "4:3" | "1:1"

// 比例值映射
const ASPECT_RATIOS: Record<AspectRatio, number> = {
  "16:9": 16 / 9,
  "9:16": 9 / 16,
  "3:4": 3 / 4,
  "4:3": 4 / 3,
  "1:1": 1
}

// 最大尺寸限制
const MAX_WIDTH = 705
const MAX_HEIGHT = 457

const avatarVariants = cva(
  "relative flex shrink-0 overflow-hidden",
  {
    variants: {
      aspectRatio: {
        "16:9": "aspect-[16/9] rounded-[20px]",
        "9:16": "aspect-[9/16] rounded-[20px]",
        "3:4": "aspect-[3/4] rounded-[20px]",
        "4:3": "aspect-[4/3] rounded-[20px]",
        "1:1": "aspect-square rounded-[20px]"
      },
      shape: {
        default: "",
        circle: "rounded-full aspect-square"
      }
    },
    defaultVariants: {
      aspectRatio: "1:1",
      shape: "default"
    },
  }
)

// 计算图片最适合的显示比例
function getBestAspectRatio(width: number, height: number): AspectRatio {
  const imageRatio = width / height
  
  // 计算与各个标准比例的差异
  const differences = Object.entries(ASPECT_RATIOS).map(([key, ratio]) => ({
    ratio: key as AspectRatio,
    difference: Math.abs(imageRatio - ratio)
  }))
  
  // 返回差异最小的比例
  return differences.sort((a, b) => a.difference - b.difference)[0].ratio
}

// 计算容器尺寸
function getContainerDimensions(aspectRatio: AspectRatio): { width: number; height: number } {
  const ratio = ASPECT_RATIOS[aspectRatio]
  
  // 根据最大限制计算尺寸
  let width = MAX_WIDTH
  let height = MAX_WIDTH / ratio
  
  if (height > MAX_HEIGHT) {
    height = MAX_HEIGHT
    width = MAX_HEIGHT * ratio
  }
  
  return { width, height }
}

interface AvatarProps extends 
  Omit<React.ComponentProps<typeof AvatarPrimitive.Root>, 'style'>,
  VariantProps<typeof avatarVariants> {
  src?: string
  alt?: string
  fallback?: React.ReactNode
  autoAspectRatio?: boolean
  fixedAspectRatio?: AspectRatio
}

function Avatar({
  className,
  src,
  alt,
  fallback,
  autoAspectRatio = true,
  fixedAspectRatio,
  aspectRatio: variantAspectRatio,
  shape,
  ...props
}: AvatarProps) {
  const [imageAspectRatio, setImageAspectRatio] = React.useState<AspectRatio>("1:1")
  const [imageLoaded, setImageLoaded] = React.useState(false)
  const [imageError, setImageError] = React.useState(false)
  
  // 处理图片加载
  const handleImageLoad = React.useCallback((event: React.SyntheticEvent<HTMLImageElement>) => {
    const img = event.target as HTMLImageElement
    const { naturalWidth, naturalHeight } = img
    
    if (autoAspectRatio && naturalWidth && naturalHeight) {
      const bestRatio = getBestAspectRatio(naturalWidth, naturalHeight)
      setImageAspectRatio(bestRatio)
    }
    
    setImageLoaded(true)
    setImageError(false)
  }, [autoAspectRatio])
  
  const handleImageError = React.useCallback(() => {
    setImageError(true)
    setImageLoaded(false)
  }, [])
  
  // 确定最终使用的比例
  const finalAspectRatio = fixedAspectRatio || variantAspectRatio || imageAspectRatio
  
  // 获取容器尺寸
  const containerDimensions = getContainerDimensions(finalAspectRatio)
  
  return (
    <AvatarPrimitive.Root
      data-slot="avatar"
      className={cn(avatarVariants({ aspectRatio: finalAspectRatio, shape }), className)}
      style={{
        maxWidth: `${containerDimensions.width}px`,
        maxHeight: `${containerDimensions.height}px`,
      }}
      {...props}
    >
      {src && !imageError ? (
        <AvatarPrimitive.Image
          src={src}
          alt={alt}
          data-slot="avatar-image"
          className="size-full object-cover"
          onLoad={handleImageLoad}
          onError={handleImageError}
        />
      ) : null}
      
      <AvatarPrimitive.Fallback
        data-slot="avatar-fallback"
        className={cn(
          "bg-[#A9B2C7] bg-opacity-30 flex size-full items-center justify-center text-muted-foreground",
          shape === "circle" ? "rounded-full" : "rounded-[20px]",
          imageLoaded && !imageError && "hidden"
        )}
      >
        {fallback || (
          <div className={cn(
            "size-full bg-[#A9B2C7] bg-opacity-30",
            shape === "circle" ? "rounded-full" : "rounded-[20px]"
          )} />
        )}
      </AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  )
}

// 保持向后兼容的组件
function AvatarImage({
  className,
  ...props
}: React.ComponentProps<typeof AvatarPrimitive.Image>) {
  return (
    <AvatarPrimitive.Image
      data-slot="avatar-image"
      className={cn("aspect-square size-full object-cover", className)}
      {...props}
    />
  )
}

function AvatarFallback({
  className,
  ...props
}: React.ComponentProps<typeof AvatarPrimitive.Fallback>) {
  return (
    <AvatarPrimitive.Fallback
      data-slot="avatar-fallback"
      className={cn(
        "bg-[#A9B2C7] bg-opacity-30 flex size-full items-center justify-center rounded-[20px]",
        className
      )}
      {...props}
    />
  )
}

export { Avatar, AvatarImage, AvatarFallback, avatarVariants }
export type { AspectRatio }
