/**
 * File system utilities for real-time file watching and browsing
 *
 * Uses @parcel/watcher for efficient, scalable file watching.
 * This is the same library used by VS Code, Parcel, Nx, and Nuxt.
 *
 * Benefits over chokidar:
 * - Native C++ implementation with throttling/coalescing in C++
 * - Automatic Watchman integration for large repos
 * - Uses FSEvents on macOS, inotify on Linux efficiently
 * - Handles tens of thousands of files without exhausting inotify limits
 */

import { readdirSync, readFileSync, statSync, watch, type FSWatcher } from "node:fs";
import { homedir } from "node:os";
import { resolve, relative, sep, basename, extname, join } from "node:path";
import type * as ParcelWatcher from "@parcel/watcher";
import { log } from "./logger.js";

// Ignored patterns for file watching (glob patterns for @parcel/watcher).
// Patterns match on relative paths from the watched root.
// The first pattern matches all hidden files/dirs (.git, .vscode, .idea, etc.)
const WATCHER_IGNORE_PATTERNS: string[] = [
  // Hidden files and directories (covers .git, .vscode, .idea, .cache, .next, etc.)
  "**/.*",
  "**/.*/**",
  // Package managers
  "**/node_modules/**",
  // Build outputs
  "**/dist/**",
  "**/build/**",
  "**/out/**",
  "**/coverage/**",
  // Lock files
  "**/*.lock",
  "**/bun.lockb",
  "**/package-lock.json",
  "**/yarn.lock",
  "**/pnpm-lock.yaml",
  // Temporary directories
  "**/__pycache__/**",
  "**/tmp/**",
  "**/temp/**",
];

// Ignored names for directory listing (simple string/extension matching)
const IGNORED_NAMES = new Set([
  "node_modules",
  ".git",
  "dist",
  "build",
  ".next",
  "coverage",
  ".acp-proxy",
  ".DS_Store",
  "thumbs.db",
  "bun.lockb",
  "package-lock.json",
]);

// Ignored extensions for directory listing
const IGNORED_EXTENSIONS = new Set([".lock"]);

// File size limits
const MAX_TEXT_SIZE = 100 * 1024; // 100KB
const MAX_IMAGE_SIZE = 1 * 1024 * 1024; // 1MB

// Image extensions
const IMAGE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp"]);

// Binary extensions (don't try to read as text)
const BINARY_EXTENSIONS = new Set([
  ".exe", ".dll", ".so", ".dylib", ".bin", ".dat",
  ".zip", ".tar", ".gz", ".rar", ".7z",
  ".pdf", ".doc", ".docx", ".xls", ".xlsx",
  ".mp3", ".mp4", ".avi", ".mov", ".mkv",
  ".ttf", ".otf", ".woff", ".woff2",
]);

export interface FileItem {
  name: string;
  path: string; // relative path
  type: "file" | "dir";
  size?: number;
  mtime?: number;
}

export interface FileContent {
  path: string;
  content: string; // text or base64 for images
  size: number;
  truncated: boolean;
  binary: boolean;
  mimeType?: string;
}

/**
 * File change event from @parcel/watcher
 * Event types:
 * - "create": file or directory was created
 * - "update": file was modified
 * - "delete": file or directory was deleted
 */
export interface FileChange {
  event: "create" | "update" | "delete";
  path: string; // relative path
}

/**
 * Validate and resolve a path, preventing path traversal attacks
 * Returns null if the path is outside the root directory
 */
export function safePath(root: string, userPath: string): string | null {
  const resolvedRoot = resolve(root);
  const resolved = resolve(root, userPath);

  // Must be within root directory (or be the root itself)
  if (resolved !== resolvedRoot && !resolved.startsWith(resolvedRoot + sep)) {
    return null;
  }
  return resolved;
}

/**
 * List contents of a directory (lazy loading - one level only)
 */
export function listDir(root: string, dirPath: string): FileItem[] | null {
  const fullPath = safePath(root, dirPath);
  if (!fullPath) return null;

  try {
    const entries = readdirSync(fullPath, { withFileTypes: true });
    const items: FileItem[] = [];

    for (const entry of entries) {
      // Skip hidden files and ignored patterns
      if (entry.name.startsWith(".")) continue;
      if (IGNORED_NAMES.has(entry.name)) continue;
      const ext = extname(entry.name).toLowerCase();
      if (IGNORED_EXTENSIONS.has(ext)) continue;

      const entryPath = resolve(fullPath, entry.name);
      const relativePath = relative(root, entryPath);

      try {
        const stats = statSync(entryPath);
        items.push({
          name: entry.name,
          path: relativePath,
          type: entry.isDirectory() ? "dir" : "file",
          size: entry.isFile() ? stats.size : undefined,
          mtime: stats.mtimeMs,
        });
      } catch {
        // Skip files we can't stat
      }
    }

    // Sort: directories first, then alphabetically
    items.sort((a, b) => {
      if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
      return a.name.localeCompare(b.name);
    });

    return items;
  } catch {
    return null;
  }
}

/**
 * Read file content with size limits and type detection
 */
export function readFile(root: string, filePath: string): FileContent | null {
  const fullPath = safePath(root, filePath);
  if (!fullPath) return null;

  try {
    const stats = statSync(fullPath);
    if (!stats.isFile()) return null;

    const ext = extname(fullPath).toLowerCase();
    const isImage = IMAGE_EXTENSIONS.has(ext);
    const isBinary = BINARY_EXTENSIONS.has(ext);

    // Binary files (non-image)
    if (isBinary) {
      return {
        path: filePath,
        content: `[Binary file: ${basename(fullPath)}, ${formatSize(stats.size)}]`,
        size: stats.size,
        truncated: false,
        binary: true,
      };
    }

    // Image files
    if (isImage) {
      if (stats.size > MAX_IMAGE_SIZE) {
        return {
          path: filePath,
          content: `[Image too large: ${formatSize(stats.size)}, max ${formatSize(MAX_IMAGE_SIZE)}]`,
          size: stats.size,
          truncated: true,
          binary: true,
        };
      }
      const buffer = readFileSync(fullPath);
      const mimeType = getMimeType(ext);
      return {
        path: filePath,
        content: buffer.toString("base64"),
        size: stats.size,
        truncated: false,
        binary: true,
        mimeType,
      };
    }

    // Text files
    const truncated = stats.size > MAX_TEXT_SIZE;
    const buffer = readFileSync(fullPath);
    const content = truncated
      ? buffer.subarray(0, MAX_TEXT_SIZE).toString("utf-8") + "\n\n[... truncated]"
      : buffer.toString("utf-8");

    return {
      path: filePath,
      content,
      size: stats.size,
      truncated,
      binary: false,
    };
  } catch {
    return null;
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
}

function getMimeType(ext: string): string {
  const types: Record<string, string> = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".bmp": "image/bmp",
  };
  return types[ext] || "application/octet-stream";
}

// ============ File Watcher (@parcel/watcher, fs.watch fallback) ============

export type FileChangeHandler = (changes: FileChange[]) => void;

/**
 * Lazily loaded @parcel/watcher module (null when unavailable).
 *
 * @parcel/watcher ships platform-specific native binaries (@parcel/watcher-
 * <os>-<arch>). The production tarball is built on one platform and reused
 * everywhere, so the native binary for the current platform may be absent.
 * Loading must be optional so the proxy still works on any platform — we
 * fall back to a pure-JS recursive fs.watch implementation.
 */
let parcelWatcher: typeof ParcelWatcher | null = null;
let parcelWatcherLoaded = false;

async function loadParcelWatcher(): Promise<typeof ParcelWatcher | null> {
  if (parcelWatcherLoaded) {
    return parcelWatcher;
  }
  parcelWatcherLoaded = true;
  try {
    parcelWatcher = await import("@parcel/watcher");
    log.debug("Using @parcel/watcher for file watching");
  } catch (err) {
    parcelWatcher = null;
    log.warn("@parcel/watcher unavailable, falling back to fs.watch", {
      error: String(err),
    });
  }
  return parcelWatcher;
}

/**
 * State for a watched directory. Two backends share this interface:
 * - native: @parcel/watcher subscription (preferred)
 * - fallback: recursive fs.watch FSWatcher map (pure JS, cross-platform)
 *
 * @parcel/watcher handles multiple subscriptions internally, but we still
 * track handlers for our own reference counting.
 */
interface WatcherState {
  handlers: Set<FileChangeHandler>;
  native?: ParcelWatcher.AsyncSubscription;
  fallbackWatchers?: Map<string, FSWatcher>; // dir -> FSWatcher (fallback only)
}

const watchers = new Map<string, WatcherState>();

/**
 * Start watching a directory for file changes.
 *
 * Prefers @parcel/watcher (native OS APIs: FSEvents / inotify /
 * ReadDirectoryChangesW, C++ throttling, Watchman integration). When the
 * native binary is unavailable for the current platform, falls back to a
 * recursive fs.watch so the proxy keeps working on any platform.
 *
 * Uses reference counting - multiple clients can subscribe to the same root.
 * Returns an unsubscribe function to remove this specific handler.
 */
export async function startWatcher(root: string, handler: FileChangeHandler): Promise<() => void> {
  const existing = watchers.get(root);

  if (existing) {
    // Add handler to existing watcher
    existing.handlers.add(handler);
    return createUnsubscribe(existing.handlers, handler, root);
  }

  // Refuse to watch the home directory itself: it contains enormous and
  // TCC-protected trees (Photos Library, Library/...) that exhaust file
  // descriptors or stall the scan. Old sessions with cwd=$HOME hit this;
  // the file explorer simply gets no live updates for them.
  if (resolve(root) === homedir()) {
    log.warn("Refusing to watch the home directory; live file changes disabled", { root });
    return () => {};
  }

  const handlers = new Set<FileChangeHandler>([handler]);
  const pw = await loadParcelWatcher();

  if (pw) {
    const subscription = await pw.subscribe(
      root,
      (err, events) => {
        if (err) {
          log.error("File watcher error", { root, error: String(err) });
          return;
        }

        // Convert @parcel/watcher events to our FileChange format
        // Events already have: { type: 'create' | 'update' | 'delete', path: string (absolute) }
        const changes: FileChange[] = events.map((event) => ({
          event: event.type,
          path: relative(root, event.path),
        }));

        // Notify all handlers
        for (const h of handlers) {
          h(changes);
        }
      },
      {
        ignore: WATCHER_IGNORE_PATTERNS,
      }
    );

    watchers.set(root, { handlers, native: subscription });
    log.debug("File watcher started (native)", { root });
  } else {
    const fallbackWatchers = startFallbackWatchers(root, handlers);
    watchers.set(root, { handlers, fallbackWatchers });
    log.debug("File watcher started (fs.watch fallback)", { root });
  }

  return createUnsubscribe(handlers, handler, root);
}

/**
 * Pure-JS recursive watcher fallback using fs.watch.
 *
 * fs.watch's `recursive: true` is only supported on macOS/Windows; on Linux
 * it throws, so we walk the tree and watch each directory ourselves, adding
 * watchers for newly created directories as they appear. Events are
 * throttled/coalesced per path before dispatching as FileChange.
 */
function startFallbackWatchers(
  root: string,
  handlers: Set<FileChangeHandler>
): Map<string, FSWatcher> {
  const fsws = new Map<string, FSWatcher>();
  // pending coalescing: path -> event type (create beats update)
  const pending = new Map<string, FileChange["event"]>();
  let flushTimer: NodeJS.Timeout | null = null;
  const FLUSH_MS = 150;

  const flush = (): void => {
    if (pending.size === 0) {
      return;
    }
    const changes: FileChange[] = [];
    for (const [rel, event] of pending) {
      changes.push({ event, path: rel });
    }
    pending.clear();
    for (const h of handlers) {
      h(changes);
    }
  };

  const scheduleFlush = (): void => {
    if (flushTimer) {
      return;
    }
    flushTimer = setTimeout(() => {
      flushTimer = null;
      flush();
    }, FLUSH_MS);
  };

  const isIgnoredRel = (rel: string): boolean => {
    if (!rel) {
      return false;
    }
    const segs = rel.split(sep);
    for (const s of segs) {
      if (!s) {
        continue;
      }
      if (s.startsWith(".") || s === "node_modules" || s === "__pycache__") {
        return true;
      }
      if (s === "dist" || s === "build" || s === "out" || s === "coverage") {
        return true;
      }
    }
    return false;
  };

  const addDir = (dir: string): void => {
    if (fsws.has(dir)) {
      return;
    }
    let w: FSWatcher;
    try {
      w = watch(dir, (eventType, filename) => {
        if (!filename) {
          return;
        }
        const name = filename.toString();
        // Skip events about the watched directory itself (macOS reports a
        // rename on the parent when the watched dir is created/removed). We
        // only care about changes *inside* the root, not the root entry.
        if (name === basename(dir)) {
          return;
        }
        const abs = join(dir, name);
        const rel = relative(root, abs);
        if (isIgnoredRel(rel)) {
          return;
        }
        // fs.watch gives rename/change only; map to create/update/delete.
        let st: ReturnType<typeof statSync> | null = null;
        try {
          st = statSync(abs);
        } catch {
          // ENOENT → deleted between event and stat
          pending.set(rel, pending.get(rel) ?? "delete");
          scheduleFlush();
          return;
        }
        if (st.isDirectory()) {
          // New directory: start watching it too, report as create.
          addDir(abs);
          pending.set(rel, pending.get(rel) ?? "create");
          scheduleFlush();
          return;
        }
        const prev = pending.get(rel);
        // rename + exists → create (or update if already tracked); change → update
        pending.set(rel, prev === "create" ? "create" : eventType === "rename" ? "create" : "update");
        scheduleFlush();
      });
    } catch (err) {
      log.warn("fs.watch failed for directory", { dir, error: String(err) });
      return;
    }
    // Async watcher errors (e.g. EMFILE once the fd limit is exhausted)
    // must never kill the whole proxy: drop this watcher and keep serving.
    w.on("error", (err) => {
      log.warn("fs.watch error, dropping watcher for directory", { dir, error: String(err) });
      fsws.delete(dir);
      try {
        w.close();
      } catch {
        // already closed
      }
    });
    fsws.set(dir, w);
    // Watch existing subdirectories.
    let entries: import("node:fs").Dirent[];
    try {
      entries = readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      if (!e.isDirectory()) {
        continue;
      }
      const child = join(dir, e.name);
      if (isIgnoredRel(relative(root, child))) {
        continue;
      }
      addDir(child);
    }
  };

  addDir(root);
  return fsws;
}

/**
 * Create an unsubscribe function for a handler.
 * Uses fire-and-forget pattern for async cleanup since unsubscribe
 * callbacks are expected to be synchronous by most APIs.
 */
function createUnsubscribe(
  handlers: Set<FileChangeHandler>,
  handler: FileChangeHandler,
  root: string
): () => void {
  return () => {
    handlers.delete(handler);
    if (handlers.size === 0) {
      // Fire-and-forget: cleanup runs async but we don't block the caller
      stopWatcher(root).catch((err) => {
        log.error("Failed to stop file watcher", { root, error: String(err) });
      });
    }
  };
}

/**
 * Stop watching a directory (removes all handlers)
 */
export async function stopWatcher(root: string): Promise<void> {
  const state = watchers.get(root);
  if (state) {
    if (state.native) {
      await state.native.unsubscribe();
    }
    if (state.fallbackWatchers) {
      for (const w of state.fallbackWatchers.values()) {
        w.close();
      }
      state.fallbackWatchers.clear();
    }
    watchers.delete(root);
    log.debug("File watcher stopped", { root });
  }
}

/**
 * Stop all watchers
 */
export async function stopAllWatchers(): Promise<void> {
  const roots = Array.from(watchers.keys());
  await Promise.all(roots.map((root) => stopWatcher(root)));
}

