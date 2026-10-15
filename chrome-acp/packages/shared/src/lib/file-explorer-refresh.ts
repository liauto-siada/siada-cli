import type { FileChange } from "../acp/types";

export function isDeletedPath(path: string, changes: FileChange[]): boolean {
  return isWithinDeletedSubtree(path, new Set(
    changes.filter(change => change.event === "delete").map(change => change.path)
  ));
}

function isWithinDeletedSubtree(path: string, deleted: Set<string>): boolean {
  let current = path;
  for (;;) {
    if (deleted.has(current)) return true;
    const slash = current.lastIndexOf("/");
    if (slash < 0) return false;
    current = current.slice(0, slash);
  }
}

/** Refresh cached directories only; removed subtrees no longer have a listing. */
export function directoriesToRefresh(changes: FileChange[], loadedPaths: Set<string>): string[] {
  const affected = new Set<string>();
  const deleted = new Set(changes.filter(change => change.event === "delete").map(change => change.path));
  for (const change of changes) {
    const parent = change.path.includes("/")
      ? change.path.slice(0, change.path.lastIndexOf("/"))
      : "";
    if (loadedPaths.has(parent) && !isWithinDeletedSubtree(parent, deleted)) affected.add(parent);
  }
  return [...affected];
}