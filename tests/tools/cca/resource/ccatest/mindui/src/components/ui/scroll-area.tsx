"use client";

import * as React from "react";
import * as ScrollAreaPrimitive from "./radix-scroll-area";
import { motion } from "framer-motion";

interface ScrollAreaProps {
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  orientation?: "horizontal" | "vertical";
  bounce?: boolean;
}

const SCROLLBAR_HIDE_DELAY = 1500;
const THUMB_PRESS_DELAY = 100;
const THUMB_WIDTH = { normal: 10, active: 20 };

const ScrollArea = React.forwardRef<
  React.ComponentRef<typeof ScrollAreaPrimitive.Root>,
  ScrollAreaProps
>(
  (
    {
      children,
      className = "",
      style,
      orientation = "vertical",
      bounce = false,
      ...props
    },
    ref,
  ) => {
    const [showScrollbar, setShowScrollbar] = React.useState(false);
    const [isThumbActive, setIsThumbActive] = React.useState(false);
    const [isDragging, setIsDragging] = React.useState(false);
    const [thumbSize, setThumbSize] = React.useState(0);
    const [thumbOffset, setThumbOffset] = React.useState(0);
    const [hasScrollableContent, setHasScrollableContent] =
      React.useState(false);
    const [dragStart, setDragStart] = React.useState<{
      pos: number;
      scrollRatio: number;
    } | null>(null);

    const scrollTimeoutRef = React.useRef<NodeJS.Timeout | undefined>(
      undefined,
    );
    const thumbPressTimeoutRef = React.useRef<NodeJS.Timeout | undefined>(
      undefined,
    );
    const viewportRef = React.useRef<HTMLDivElement>(null);
    const scrollbarRef = React.useRef<HTMLDivElement>(null);
    const thumbRef = React.useRef<HTMLDivElement>(null);

    const isVertical = orientation === "vertical";

    const updateThumb = React.useCallback(() => {
      const viewport = viewportRef.current;
      if (!viewport) return;

      const viewportSize = isVertical
        ? viewport.clientHeight
        : viewport.clientWidth;
      const contentSize = isVertical
        ? viewport.scrollHeight
        : viewport.scrollWidth;
      const scrollPos = isVertical ? viewport.scrollTop : viewport.scrollLeft;

      const canScroll = contentSize > viewportSize;
      setHasScrollableContent(canScroll);

      if (!canScroll) {
        setThumbSize(0);
        return;
      }

      const thumbLength = Math.max(
        20,
        (viewportSize / contentSize) * viewportSize,
      );
      const maxOffset = viewportSize - thumbLength;
      const scrollRatio = scrollPos / (contentSize - viewportSize);
      const offset = scrollRatio * maxOffset;

      setThumbSize(thumbLength);
      setThumbOffset(offset);
    }, [isVertical]);

    const hideScrollbar = React.useCallback(() => {
      if (scrollTimeoutRef.current) {
        clearTimeout(scrollTimeoutRef.current);
      }
      scrollTimeoutRef.current = setTimeout(() => {
        setShowScrollbar(false);
      }, SCROLLBAR_HIDE_DELAY);
    }, []);

    const handleScroll = React.useCallback(() => {
      setShowScrollbar(true);
      updateThumb();
      hideScrollbar();
    }, [updateThumb, hideScrollbar]);

    const handleThumbPointerDown = React.useCallback(
      (e: React.PointerEvent) => {
        e.preventDefault();
        e.stopPropagation();

        const viewport = viewportRef.current;
        const thumbElement = thumbRef.current;
        if (!viewport || !thumbElement) return;

        setShowScrollbar(true);
        if (scrollTimeoutRef.current) {
          clearTimeout(scrollTimeoutRef.current);
        }

        thumbElement.setPointerCapture(e.pointerId);

        const startPos = isVertical ? e.clientY : e.clientX;
        const maxScroll =
          (isVertical ? viewport.scrollHeight : viewport.scrollWidth) -
          (isVertical ? viewport.clientHeight : viewport.clientWidth);
        const currentScroll = isVertical
          ? viewport.scrollTop
          : viewport.scrollLeft;
        const currentScrollRatio =
          maxScroll > 0 ? currentScroll / maxScroll : 0;

        setDragStart({ pos: startPos, scrollRatio: currentScrollRatio });

        thumbPressTimeoutRef.current = setTimeout(() => {
          setIsThumbActive(true);
          setIsDragging(true);
        }, THUMB_PRESS_DELAY);
      },
      [isVertical],
    );

    const handleThumbPointerMove = React.useCallback(
      (e: React.PointerEvent) => {
        if (!dragStart || !viewportRef.current) return;

        const viewport = viewportRef.current;
        const currentPos = isVertical ? e.clientY : e.clientX;
        const delta = currentPos - dragStart.pos;
        const trackLength =
          (isVertical ? viewport.clientHeight : viewport.clientWidth) -
          thumbSize;

        if (trackLength <= 0) return;

        const deltaRatio = delta / trackLength;
        const newScrollRatio = Math.max(
          0,
          Math.min(1, dragStart.scrollRatio + deltaRatio),
        );
        const maxScroll =
          (isVertical ? viewport.scrollHeight : viewport.scrollWidth) -
          (isVertical ? viewport.clientHeight : viewport.clientWidth);

        if (isVertical) {
          viewport.scrollTop = newScrollRatio * maxScroll;
        } else {
          viewport.scrollLeft = newScrollRatio * maxScroll;
        }

        updateThumb();
      },
      [dragStart, thumbSize, isVertical, updateThumb],
    );

    const handleThumbPointerUp = React.useCallback(
      (e: React.PointerEvent) => {
        const thumbElement = thumbRef.current;
        if (thumbElement) thumbElement.releasePointerCapture(e.pointerId);

        if (thumbPressTimeoutRef.current) {
          clearTimeout(thumbPressTimeoutRef.current);
        }

        setIsThumbActive(false);
        setIsDragging(false);
        setDragStart(null);

        hideScrollbar();
      },
      [hideScrollbar],
    );

    const handleScrollbarClick = React.useCallback(
      (e: React.PointerEvent) => {
        if (!scrollbarRef.current || !viewportRef.current || !thumbRef.current)
          return;

        const target = e.target as Element;
        if (thumbRef.current.contains(target) || thumbRef.current === target)
          return;

        const viewport = viewportRef.current;
        const scrollbarRect = scrollbarRef.current.getBoundingClientRect();
        const clickPos = isVertical
          ? e.clientY - scrollbarRect.top
          : e.clientX - scrollbarRect.left;
        const trackLength = isVertical
          ? scrollbarRect.height
          : scrollbarRect.width;
        const clickRatio = Math.max(0, Math.min(1, clickPos / trackLength));

        const maxScroll =
          (isVertical ? viewport.scrollHeight : viewport.scrollWidth) -
          (isVertical ? viewport.clientHeight : viewport.clientWidth);
        const targetScroll = clickRatio * maxScroll;
        const currentScroll = isVertical
          ? viewport.scrollTop
          : viewport.scrollLeft;
        const distance = Math.abs(targetScroll - currentScroll);
        const pageSize = isVertical
          ? viewport.clientHeight
          : viewport.clientWidth;

        let finalScroll = targetScroll;
        if (distance > pageSize) {
          const direction = targetScroll > currentScroll ? 1 : -1;
          const nextScroll = currentScroll + direction * pageSize;
          finalScroll =
            direction > 0
              ? Math.min(nextScroll, targetScroll)
              : Math.max(nextScroll, targetScroll);
        }

        if (isVertical) {
          viewport.scrollTop = finalScroll;
        } else {
          viewport.scrollLeft = finalScroll;
        }

        setShowScrollbar(true);
        hideScrollbar();
      },
      [isVertical, hideScrollbar],
    );

    React.useEffect(() => {
      updateThumb();
      const handleResize = () => updateThumb();
      window.addEventListener("resize", handleResize);
      return () => window.removeEventListener("resize", handleResize);
    }, [updateThumb]);

    React.useEffect(() => {
      updateThumb();
    }, [children, updateThumb]);

    React.useEffect(() => {
      return () => {
        if (scrollTimeoutRef.current) {
          clearTimeout(scrollTimeoutRef.current);
        }
        if (thumbPressTimeoutRef.current) {
          clearTimeout(thumbPressTimeoutRef.current);
        }
      };
    }, []);

    const shouldShowScrollbar = showScrollbar && hasScrollableContent;
    const thumbWidth = isThumbActive ? THUMB_WIDTH.active : THUMB_WIDTH.normal;

    return (
      <ScrollAreaPrimitive.Root
        ref={ref}
        className={`relative overflow-hidden ${className}`}
        style={style}
        {...props}
      >
        <ScrollAreaPrimitive.Viewport
          ref={viewportRef}
          className="hide-scrollbar h-full w-full rounded"
          style={{ WebkitOverflowScrolling: bounce ? "touch" : undefined }}
          onScroll={handleScroll}
        >
          {children}
        </ScrollAreaPrimitive.Viewport>

        <motion.div
          ref={scrollbarRef}
          className={`absolute z-10 flex touch-none select-none ${
            isVertical ? "top-0 right-0 h-full" : "bottom-0 left-0 w-full"
          }`}
          initial={false}
          animate={{
            opacity: shouldShowScrollbar ? 1 : 0,
            [isVertical ? "x" : "y"]: shouldShowScrollbar ? 0 : 20,
            width: isVertical ? thumbWidth : "100%",
            height: isVertical ? "100%" : thumbWidth,
          }}
          transition={{
            opacity: { duration: 0.2, ease: [0.61, 1, 0.88, 1] },
            width: { type: "spring", stiffness: 405.823, damping: 26.873 },
            height: { type: "spring", stiffness: 405.823, damping: 26.873 },
          }}
          style={{
            pointerEvents: shouldShowScrollbar || isDragging ? "auto" : "none",
          }}
          onPointerDown={handleScrollbarClick}
        >
          <ScrollAreaPrimitive.Scrollbar
            orientation={orientation}
            forceMount
            className="relative h-full w-full"
            style={{ background: "transparent" }}
          >
            <motion.div
              ref={thumbRef}
              className="absolute rounded-full bg-[#C4D0DF] dark:bg-[#1D1E20]"
              animate={{
                width: isVertical ? thumbWidth : thumbSize,
                height: isVertical ? thumbSize : thumbWidth,
              }}
              transition={{
                width: { type: "spring", stiffness: 405.823, damping: 26.873 },
                height: { type: "spring", stiffness: 405.823, damping: 26.873 },
              }}
              style={{
                top: isVertical ? thumbOffset : 0,
                left: isVertical ? 0 : thumbOffset,
                cursor: isDragging ? "grabbing" : "grab",
              }}
              onPointerDown={handleThumbPointerDown}
              onPointerMove={handleThumbPointerMove}
              onPointerUp={handleThumbPointerUp}
              onPointerCancel={handleThumbPointerUp}
            />
          </ScrollAreaPrimitive.Scrollbar>
        </motion.div>
      </ScrollAreaPrimitive.Root>
    );
  },
);

ScrollArea.displayName = "ScrollArea";

export { ScrollArea };
