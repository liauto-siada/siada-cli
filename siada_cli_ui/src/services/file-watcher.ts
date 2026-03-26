/**
 * File Watcher Service
 * Monitors file system changes in the working directory
 */

import { watch, FSWatcher, WatchEventType } from 'fs';
import { EventEmitter } from 'events';
import { stat, readdir } from 'fs/promises';
import { join, relative } from 'path';
import { logger } from '../utils/logger.js';

export interface FileWatcherOptions {
  ignore?: (string | RegExp)[];
  recursive?: boolean;
  debounceDelay?: number;
}

export interface FileChangeEvent {
  type: 'create' | 'modify' | 'delete';
  path: string;
  relativePath: string;
  timestamp: Date;
}

/**
 * File Watcher - monitors file system changes
 */
export class FileWatcher extends EventEmitter {
  private watcher: FSWatcher | null = null;
  private watchedPath: string;
  private options: Required<FileWatcherOptions>;
  private debounceTimers: Map<string, NodeJS.Timeout> = new Map();
  private fileCache: Map<string, number> = new Map(); // path -> mtime

  constructor(
    watchPath: string,
    options: FileWatcherOptions = {}
  ) {
    super();
    this.watchedPath = watchPath;
    this.options = {
      ignore: options.ignore || [
        /node_modules/,
        /\.git/,
        /\.DS_Store/,
        /\.pyc$/,
        /__pycache__/,
        /\.egg-info/,
        /dist/,
        /build/,
      ],
      recursive: options.recursive ?? true,
      debounceDelay: options.debounceDelay || 300,
    };
  }

  /**
   * Start watching
   */
  async start(): Promise<void> {
    if (this.watcher) {
      throw new Error('Watcher already started');
    }

    logger.info('Starting file watcher', { path: this.watchedPath });

    try {
      // Initialize file cache
      await this.initializeFileCache();

      // Start watching
      this.watcher = watch(
        this.watchedPath,
        { recursive: this.options.recursive },
        (eventType, filename) => {
          if (filename) {
            this.handleFileChange(eventType, filename);
          }
        }
      );

      this.watcher.on('error', (error) => {
        logger.error('File watcher error', error);
        this.emit('error', error);
      });

      this.emit('started');
      logger.info('File watcher started');
    } catch (error) {
      logger.error('Failed to start file watcher', error);
      throw error;
    }
  }

  /**
   * Initialize file cache with current file states
   */
  private async initializeFileCache(): Promise<void> {
    try {
      await this.scanDirectory(this.watchedPath);
      logger.debug('File cache initialized', { count: this.fileCache.size });
    } catch (error) {
      logger.warn('Failed to initialize file cache', error as Error);
    }
  }

  /**
   * Recursively scan directory and cache file states
   */
  private async scanDirectory(dirPath: string): Promise<void> {
    try {
      const entries = await readdir(dirPath, { withFileTypes: true });

      for (const entry of entries) {
        const fullPath = join(dirPath, entry.name);
        const relativePath = relative(this.watchedPath, fullPath);

        // Check if should ignore
        if (this.shouldIgnore(relativePath)) {
          continue;
        }

        if (entry.isFile()) {
          try {
            const stats = await stat(fullPath);
            this.fileCache.set(relativePath, stats.mtimeMs);
          } catch (error) {
            // Ignore errors for individual files
          }
        } else if (entry.isDirectory() && this.options.recursive) {
          await this.scanDirectory(fullPath);
        }
      }
    } catch (error) {
      // Ignore directory access errors
    }
  }

  /**
   * Handle file change event
   */
  private handleFileChange(eventType: WatchEventType, filename: string): void {
    // Clear existing debounce timer
    const existingTimer = this.debounceTimers.get(filename);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }

    // Set new debounce timer
    const timer = setTimeout(() => {
      this.debounceTimers.delete(filename);
      this.processFileChange(eventType, filename);
    }, this.options.debounceDelay);

    this.debounceTimers.set(filename, timer);
  }

  /**
   * Process file change after debounce
   */
  private async processFileChange(eventType: WatchEventType, filename: string): Promise<void> {
    try {
      // Check if should ignore
      if (this.shouldIgnore(filename)) {
        return;
      }

      const fullPath = join(this.watchedPath, filename);
      const changeType = await this.determineChangeType(fullPath, filename);

      if (changeType) {
        const event: FileChangeEvent = {
          type: changeType,
          path: fullPath,
          relativePath: filename,
          timestamp: new Date(),
        };

        logger.debug('File change detected', event);
        this.emit('change', event);
        this.emit(changeType, event);
      }
    } catch (error) {
      logger.error('Error processing file change', { error, filename });
    }
  }

  /**
   * Determine the type of file change
   */
  private async determineChangeType(
    fullPath: string,
    relativePath: string
  ): Promise<'create' | 'modify' | 'delete' | null> {
    try {
      const stats = await stat(fullPath);
      const cachedMtime = this.fileCache.get(relativePath);

      if (!cachedMtime) {
        // New file
        this.fileCache.set(relativePath, stats.mtimeMs);
        return 'create';
      } else if (stats.mtimeMs !== cachedMtime) {
        // Modified file
        this.fileCache.set(relativePath, stats.mtimeMs);
        return 'modify';
      }

      return null;
    } catch (error) {
      // File doesn't exist - must be deleted
      if (this.fileCache.has(relativePath)) {
        this.fileCache.delete(relativePath);
        return 'delete';
      }
      return null;
    }
  }

  /**
   * Check if path should be ignored
   */
  private shouldIgnore(path: string): boolean {
    for (const pattern of this.options.ignore) {
      if (pattern instanceof RegExp) {
        if (pattern.test(path)) {
          return true;
        }
      } else if (typeof pattern === 'string') {
        if (path.includes(pattern)) {
          return true;
        }
      }
    }
    return false;
  }

  /**
   * Stop watching
   */
  async stop(): Promise<void> {
    if (!this.watcher) {
      return;
    }

    logger.info('Stopping file watcher');

    // Clear all debounce timers
    for (const timer of this.debounceTimers.values()) {
      clearTimeout(timer);
    }
    this.debounceTimers.clear();

    // Close watcher
    this.watcher.close();
    this.watcher = null;
    this.fileCache.clear();

    this.emit('stopped');
    logger.info('File watcher stopped');
  }

  /**
   * Check if watcher is active
   */
  isWatching(): boolean {
    return this.watcher !== null;
  }

  /**
   * Get watched path
   */
  getWatchedPath(): string {
    return this.watchedPath;
  }

  /**
   * Get cache statistics
   */
  getCacheStats(): {
    fileCount: number;
    pendingEvents: number;
  } {
    return {
      fileCount: this.fileCache.size,
      pendingEvents: this.debounceTimers.size,
    };
  }

  /**
   * Add ignore pattern
   */
  addIgnorePattern(pattern: string | RegExp): void {
    this.options.ignore.push(pattern);
  }

  /**
   * Remove ignore pattern
   */
  removeIgnorePattern(pattern: string | RegExp): void {
    const index = this.options.ignore.indexOf(pattern);
    if (index !== -1) {
      this.options.ignore.splice(index, 1);
    }
  }
}

/**
 * Create and start file watcher
 */
export async function createFileWatcher(
  watchPath: string,
  options?: FileWatcherOptions
): Promise<FileWatcher> {
  const watcher = new FileWatcher(watchPath, options);
  await watcher.start();
  return watcher;
}
