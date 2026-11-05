import { getBoundingBox, type DOMElement } from '@jrichman/ink';

interface Point { x: number; y: number }
const controls = new WeakMap<NodeJS.WriteStream, Set<DOMElement>>();

/** Share control hit targets with chat selection, scoped to the rendering terminal. */
export function registerMermaidControls(stdout: NodeJS.WriteStream, node: DOMElement): () => void {
  let nodes = controls.get(stdout);
  if (!nodes) { nodes = new Set(); controls.set(stdout, nodes); }
  nodes.add(node);
  return () => {
    nodes.delete(node);
    if (!nodes.size) controls.delete(stdout);
  };
}

export function isVisibleMermaidTarget(stdout: NodeJS.WriteStream, node: DOMElement | null, point: Point): boolean {
  const { x, y } = point;
  if (!node || x < 0 || x >= (stdout.columns ?? 80) || y < 0 || y >= (stdout.rows ?? 24)) return false;
  const bounds = getBoundingBox(node);
  if (x < bounds.x || x >= bounds.x + bounds.width || y < bounds.y || y >= bounds.y + bounds.height) return false;
  for (let parent = node.parentNode; parent; parent = parent.parentNode) {
    const clip = getBoundingBox(parent);
    if ((parent.style.overflowY === 'scroll' || parent.style.overflowY === 'hidden') &&
      (y < clip.y || y >= clip.y + clip.height)) return false;
    if ((parent.style.overflowX === 'scroll' || parent.style.overflowX === 'hidden') &&
      (x < clip.x || x >= clip.x + clip.width)) return false;
  }
  return true;
}

export function isMermaidControlAt(stdout: NodeJS.WriteStream, point: Point): boolean {
  for (const node of controls.get(stdout) ?? []) {
    if (isVisibleMermaidTarget(stdout, node, point)) return true;
  }
  return false;
}