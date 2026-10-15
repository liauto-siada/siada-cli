import type { SubAgentMessageEntry } from '../hooks/useAcp/types.js';

/** Streaming snapshots replace their entry without changing conversation order. */
export function mergeSubAgentEntry(
  entries: SubAgentMessageEntry[],
  entry: SubAgentMessageEntry,
): SubAgentMessageEntry[] {
  const index = entry.id ? entries.findIndex(previous => previous.id === entry.id) : -1;
  if (index < 0) return [...entries, entry];
  // A delayed in-flight snapshot must not reopen completed reasoning.
  if (entries[index].isComplete && entry.isComplete === false) return entries;
  const next = [...entries];
  next[index] = entry;
  return next;
}