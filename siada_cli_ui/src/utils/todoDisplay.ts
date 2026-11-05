import type { TodoItem } from '../hooks/useAcp/types.js';

export const MAX_VISIBLE_TODOS = 3;

/** Prefer the running task, then pending work, then the last completed task. */
export function getTodoFocusIndex(items: TodoItem[]) {
  let focus = items.findIndex(item => item.status === 'in_progress');
  if (focus < 0) focus = items.findIndex(item => item.status === 'pending');
  return focus < 0 ? items.length - 1 : focus;
}

/** Keep the current task and its neighbors in the original plan order. */
export function getTodoVisibleRange(items: TodoItem[], activeIndex = -1) {
  const count = Math.min(items.length, MAX_VISIBLE_TODOS);
  let focus = activeIndex < 0 ? getTodoFocusIndex(items) : activeIndex;
  focus = Math.max(0, Math.min(focus, items.length - 1));
  const start = Math.max(0, Math.min(focus - 1, items.length - count));
  return { start, end: start + count };
}