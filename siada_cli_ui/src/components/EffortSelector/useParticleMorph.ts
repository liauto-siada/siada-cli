/**
 * useParticleMorph — terminal particle field that morphs between bitmap shapes.
 *
 * Ported from canvas particle systems: every particle eases (easeInOutCubic
 * with per-particle stagger) from its current position to a target point
 * sampled from the active pattern, then idles with a dual-sine drift and a
 * brightness twinkle around its target.
 */
import { useEffect, useMemo, useRef, useState } from 'react';

export interface Cell {
  ch: string;
  color: string;
}

/** grid[y][x] — null means blank. */
export type Grid = (Cell | null)[][];

const FRAME_MS = 100;
const MORPH_MS = 700;
/** Max per-particle start delay as a fraction of the morph (wave feel). */
const STAGGER = 0.35;
const IDLE_AMP = 0.5;
/** First fraction of the morph spent exploding outward before converging. */
const EXPLODE_RATIO = 0.25;
/** How far particles scatter: current offset from center × this factor. Kept
 * moderate so the approach stays visible inside the small canvas. */
const SCATTER_FACTOR = 2.5;
/** Initial spawn area: this multiple of the canvas size around its center. */
const SPAWN_SPREAD = 3;

const COLOR_BASE = '#87D7FF';
const COLOR_DIM = '#33505F';
const COLOR_FLIGHT = '#FFFFFF';

interface Particle {
  x: number;
  y: number;
  fromX: number;
  fromY: number;
  /** Mid-phase waypoint: pushed far outside the canvas before converging. */
  scatterX: number;
  scatterY: number;
  targetX: number;
  targetY: number;
  seed: number;
  speed: number;
}

interface Point {
  x: number;
  y: number;
}

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function easeOutCubic(t: number): number {
  return 1 - Math.pow(1 - t, 3);
}

/** Sample non-space cells of a pattern into centered points fitting the box. */
function samplePattern(pattern: string[], width: number, height: number): Point[] {
  const rows = pattern.length;
  const cols = Math.max(0, ...pattern.map(r => r.length));
  if (rows === 0 || cols === 0) return [];
  const scale = Math.min(1, width / cols, height / rows);
  const step = Math.max(1, Math.round(1 / scale));
  const points: Point[] = [];
  for (let r = 0; r < rows; r += step) {
    for (let c = 0; c < cols; c += step) {
      if ((pattern[r][c] ?? ' ') !== ' ') points.push({ x: c, y: r });
    }
  }
  // Center the shape inside the canvas.
  const offX = Math.round((width - cols) / 2);
  const offY = Math.round((height - rows) / 2);
  return points.map(p => ({ x: p.x + offX, y: p.y + offY }));
}

function shuffled<T>(items: T[]): T[] {
  const arr = [...items];
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }
  return arr;
}

export function useParticleMorph(pattern: string[], width: number, height: number): Grid {
  const points = useMemo(
    () => samplePattern(pattern, width, height),
    [pattern, width, height],
  );
  const particlesRef = useRef<Particle[]>([]);
  const morphStartedAtRef = useRef<number>(0);
  const [grid, setGrid] = useState<Grid>([]);

  // Retarget particles onto the new shape and start a morph.
  useEffect(() => {
    const particles = particlesRef.current;
    const cx = width / 2;
    const cy = height / 2;
    // Grow/shrink the swarm to match the point count. New particles spawn far
    // outside the canvas so the first formation reads as a wide convergence.
    while (particles.length < points.length) {
      particles.push({
        x: cx + (Math.random() - 0.5) * width * SPAWN_SPREAD,
        y: cy + (Math.random() - 0.5) * height * SPAWN_SPREAD,
        fromX: 0,
        fromY: 0,
        scatterX: 0,
        scatterY: 0,
        targetX: 0,
        targetY: 0,
        seed: Math.random() * 1000,
        speed: 0.6 + Math.random() * 0.8,
      });
    }
    particles.length = points.length;

    const targets = shuffled(points);
    particles.forEach((p, i) => {
      p.fromX = p.x;
      p.fromY = p.y;
      // Explode phase waypoint: push the current position away from center.
      p.scatterX = cx + (p.x - cx) * SCATTER_FACTOR + (Math.random() - 0.5) * width;
      p.scatterY = cy + (p.y - cy) * SCATTER_FACTOR + (Math.random() - 0.5) * height;
      p.targetX = targets[i].x;
      p.targetY = targets[i].y;
    });
    morphStartedAtRef.current = Date.now();
  }, [points, width, height]);

  // Frame loop: advance physics, rebuild the grid.
  useEffect(() => {
    const timer = setInterval(() => {
      const now = Date.now();
      const t = now / 1000;
      const elapsed = now - morphStartedAtRef.current;
      const morphing = elapsed < MORPH_MS;

      const next: Grid = Array.from({ length: height }, () => Array(width).fill(null));
      for (const p of particlesRef.current) {
        let ch: string;
        let color: string;
        if (morphing) {
          const v = elapsed / MORPH_MS;
          const delay = ((p.seed % 25) / 25) * STAGGER;
          const w = Math.max(0, Math.min(1, (v - delay) / (1 - delay)));
          if (w < EXPLODE_RATIO) {
            // Explode phase: scatter outward quickly
            const e = easeOutCubic(w / EXPLODE_RATIO);
            p.x = p.fromX + (p.scatterX - p.fromX) * e;
            p.y = p.fromY + (p.scatterY - p.fromY) * e;
          } else {
            // Converge phase: sweep in from off-canvas to the target point
            const e = easeInOutCubic((w - EXPLODE_RATIO) / (1 - EXPLODE_RATIO));
            p.x = p.scatterX + (p.targetX - p.scatterX) * e;
            p.y = p.scatterY + (p.targetY - p.scatterY) * e;
          }
          ch = w < 1 ? '*' : '•';
          color = w < 1 ? COLOR_FLIGHT : COLOR_BASE;
        } else {
          // Idle drift: two detuned sines keep the motion organic.
          const a = t * p.speed + p.seed;
          const u = t * (p.speed * 0.6 + 0.15) + p.seed * 1.7;
          p.x = p.targetX + (Math.sin(a) * 0.5 + Math.sin(u) * 0.4) * IDLE_AMP;
          p.y = p.targetY + (Math.cos(a * 0.8) * 0.5 + Math.sin(u * 1.3) * 0.4) * IDLE_AMP * 0.6;
          const tw = 0.75 + 0.25 * Math.sin(t * p.speed * 0.8 + p.seed * 2.3);
          ch = tw > 0.88 ? '•' : '·';
          color = tw > 0.88 ? COLOR_BASE : COLOR_DIM;
        }
        const cx = Math.round(p.x);
        const cy = Math.round(p.y);
        if (cx >= 0 && cx < width && cy >= 0 && cy < height) {
          next[cy][cx] = { ch, color };
        }
      }
      setGrid(next);
    }, FRAME_MS);
    return () => clearInterval(timer);
  }, [width, height]);

  return grid;
}
