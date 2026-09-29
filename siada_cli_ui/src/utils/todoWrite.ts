import type { TodoItem } from '../hooks/useAcp/types.js';

const ICON_TO_STATUS: Record<string, TodoItem['status']> = {
  '○': 'pending',
  '◐': 'in_progress',
  '✓': 'completed',
  '?': 'pending',
};

/** Parse the formatter's snapshot (also stored verbatim in resumed history). */
export function parseTodoWriteContent(content: string): TodoItem[] | null {
  const trimmed = content.trim();
  if (!trimmed) return null;
  if (trimmed === 'Clearing todo list') return [];

  const todos: TodoItem[] = [];
  for (const line of trimmed.split('\n')) {
    const stripped = line.trim();
    if (!stripped || /^\[\d+\/\d+ completed\]$/.test(stripped)) continue;
    const match = stripped.match(/^([○◐✓?])\s{1,3}(.+)$/);
    if (!match) {
      if (todos.length > 0) continue;
      return null;
    }
    todos.push({ content: match[2].trimEnd(), status: ICON_TO_STATUS[match[1]] ?? 'pending' });
  }
  return todos.length ? todos : null;
}
