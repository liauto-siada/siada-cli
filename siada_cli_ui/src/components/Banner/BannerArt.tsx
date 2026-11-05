import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Text, getBoundingBox, useStdout, type DOMElement } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { useMouseTracking } from '../../hooks/useMouseTracking.js';
import { BannerMotion, BANNER_FRAME_MS, type BannerPoint } from './bannerMotion.js';
import { displayWidth } from '../../utils/terminalWidth.js';

interface BannerArtProps { columns: number; interactive?: boolean }

function BannerArtFrame({ motion, colors, rootRef }: {
  motion: BannerMotion;
  colors: string[][];
  rootRef?: React.RefObject<DOMElement | null>;
}) {
  const width = Math.max(0, ...motion.lines.map(line => displayWidth(line.join(''))));
  return <Box ref={rootRef} flexDirection="column" flexShrink={0} width={width}>
    {motion.lines.map((line, y) => <Box key={y} height={1} flexShrink={0}>
      {line.map((character, x) => <Text key={x} color={colors[y][x]} bold>{character}</Text>)}
    </Box>)}
  </Box>;
}

/** Hit-test only the visible art, including every ancestor's scroll/clip bounds. */
function localPoint(root: DOMElement | null, point: BannerPoint, rows: number): BannerPoint | null {
  if (!root || point.y < 0 || point.y >= rows) return null;
  const bounds = getBoundingBox(root);
  if (point.x < bounds.x || point.x >= bounds.x + bounds.width ||
    point.y < bounds.y || point.y >= bounds.y + bounds.height) return null;
  let parent = root.parentNode;
  while (parent) {
    if (parent.nodeName === 'ink-box') {
      const clip = getBoundingBox(parent);
      const overflow = parent.style.overflow ?? 'visible';
      if ((parent.style.overflowX ?? overflow) !== 'visible' &&
        (point.x < clip.x || point.x >= clip.x + clip.width)) return null;
      if ((parent.style.overflowY ?? overflow) !== 'visible' &&
        (point.y < clip.y || point.y >= clip.y + clip.height)) return null;
    }
    parent = parent.parentNode;
  }
  return { x: Math.floor(point.x - bounds.x), y: Math.floor(point.y - bounds.y) };
}

function AnimatedBannerArt({ columns }: { columns: number }) {
  const { stdout } = useStdout();
  const root = useRef<DOMElement>(null);
  const motion = useMemo(() => new BannerMotion(columns), [columns]);
  const [colors, setColors] = useState(motion.baseColors);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pointer = useRef<BannerPoint | null>(null);
  useMouseTracking();

  useEffect(() => {
    pointer.current = null;
    setColors(motion.reset());
    return () => {
      if (timer.current !== null) clearTimeout(timer.current);
      timer.current = null;
    };
  }, [motion]);

  const stop = () => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    pointer.current = null;
    setColors(motion.reset());
  };
  const tick = () => {
    timer.current = null;
    if (pointer.current) motion.move(localPoint(root.current, pointer.current, stdout.rows ?? 24), Date.now());
    const next = motion.tick(Date.now());
    setColors(next.colors);
    if (next.animating) timer.current = setTimeout(tick, BANNER_FRAME_MS);
  };
  useKeypress(key => {
    if (key.name !== 'mousemove') {
      // Never animate while selecting text, scrolling, or typing.
      if (pointer.current || timer.current !== null) stop();
      return;
    }
    const match = /^\x1b\[<(\d+);(\d+);(\d+)M$/.exec(key.sequence);
    if (!match) return;
    const button = Number(match[1]);
    if ((button & 3) !== 3 || key.shift || key.alt || key.ctrl) {
      stop();
      return;
    }
    const screenPoint = { x: Number(match[2]) - 1, y: Number(match[3]) - 1 };
    const point = localPoint(root.current, screenPoint, stdout.rows ?? 24);
    pointer.current = point ? screenPoint : null;
    motion.move(point, Date.now());
    if (motion.hasEffect && timer.current === null) timer.current = setTimeout(tick, BANNER_FRAME_MS);
  });
  return <BannerArtFrame motion={motion} colors={colors} rootRef={root} />;
}

/** Keep frame updates inside the artwork rather than rerendering banner metadata. */
export const BannerArt = React.memo(function BannerArt({ columns, interactive = false }: BannerArtProps) {
  const { stdout } = useStdout();
  const motion = useMemo(() => new BannerMotion(columns), [columns]);
  if (interactive && stdout.isTTY && !process.env.NO_COLOR && process.env.TERM !== 'dumb') {
    return <AnimatedBannerArt key={columns} columns={columns} />;
  }
  return <BannerArtFrame motion={motion} colors={motion.baseColors} />;
});