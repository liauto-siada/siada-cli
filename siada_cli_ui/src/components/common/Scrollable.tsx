/**
 * Scrollable
 *
 * A minimal scroll container for Ink (@jrichman/ink).
 *
 * - Uses <Box overflowY="scroll" scrollTop={...}> to render a scrollable viewport.
 * - Uses measure APIs (getInnerHeight/getScrollHeight) to keep scrollTop in bounds.
 * - Supports keyboard scrolling via Shift+Up/Down by default.
 * - Optional auto-stick-to-bottom behavior when new children are added.
 */

import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import {
  Box,
  getInnerHeight,
  getScrollHeight,
  type DOMElement,
} from '@jrichman/ink';
import { useKeypress, type Key } from '../../hooks/useKeypress.js';

export interface ScrollableProps {
  children?: React.ReactNode;
  width?: number;
  height?: number | string;
  maxHeight?: number;
  /** Whether this scrollable region should respond to scroll keys */
  hasFocus: boolean;
  /** Auto-scroll to bottom when children count changes and we're currently at bottom */
  scrollToBottom?: boolean;
  flexGrow?: number;
  /** Optional scrollbar thumb color */
  scrollbarThumbColor?: string;
}

export const Scrollable: React.FC<ScrollableProps> = ({
  children,
  width,
  height,
  maxHeight,
  hasFocus,
  scrollToBottom,
  flexGrow,
  scrollbarThumbColor,
}) => {
  const [scrollTop, setScrollTop] = useState(0);
  const ref = useRef<DOMElement>(null);

  const [size, setSize] = useState({ innerHeight: 0, scrollHeight: 0 });
  const sizeRef = useRef(size);
  useEffect(() => {
    sizeRef.current = size;
  }, [size]);

  const childrenCountRef = useRef(0);

  // Measure on every render; update scrollTop when the viewport or content changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    if (!ref.current) return;

    const innerHeight = Math.round(getInnerHeight(ref.current));
    const scrollHeight = Math.round(getScrollHeight(ref.current));

    const isAtBottom =
      scrollTop >= size.scrollHeight - size.innerHeight - 1; // -1 is tolerance

    if (size.innerHeight !== innerHeight || size.scrollHeight !== scrollHeight) {
      setSize({ innerHeight, scrollHeight });

      // Preserve sticking-to-bottom behavior when resizing / content reflow.
      if (isAtBottom) {
        setScrollTop(Math.max(0, scrollHeight - innerHeight));
      } else {
        // Clamp scrollTop into new bounds
        setScrollTop((current) =>
          Math.max(0, Math.min(current, Math.max(0, scrollHeight - innerHeight))),
        );
      }
    }

    const childCountCurrent = React.Children.count(children);
    if (scrollToBottom && childrenCountRef.current !== childCountCurrent) {
      // Only autoscroll if user is at bottom.
      if (isAtBottom) {
        setScrollTop(Math.max(0, scrollHeight - innerHeight));
      }
    }

    childrenCountRef.current = childCountCurrent;
  });

  const scrollBy = useCallback((delta: number) => {
    const { scrollHeight, innerHeight } = sizeRef.current;
    setScrollTop((current) => {
      const next = Math.min(
        Math.max(0, current + delta),
        Math.max(0, scrollHeight - innerHeight),
      );
      return next;
    });
  }, []);

  useKeypress(
    (key: Key) => {
      // Shift+Up/Down scrolls the history pane.
      if (key.shift && key.name === 'up') {
        scrollBy(-1);
        return;
      }
      if (key.shift && key.name === 'down') {
        scrollBy(1);
      }
    },
    { isActive: hasFocus },
  );

  const thumbColor = scrollbarThumbColor;

  // Extra inner box prevents the parent from shrinking based on children's content.
  // Also adds right padding to make room for the scrollbar.
  return (
    <Box
      ref={ref}
      width={width}
      height={height}
      maxHeight={maxHeight}
      flexDirection="column"
      overflowY="scroll"
      overflowX="hidden"
      scrollTop={scrollTop}
      flexGrow={flexGrow}
      scrollbarThumbColor={thumbColor}
    >
      <Box flexShrink={0} paddingRight={1} flexDirection="column">
        {children}
      </Box>
    </Box>
  );
};
