/**
 * Checkpoint Service
 * Manages checkpoint data for command completion
 */

import fs from 'fs';
import path from 'path';
import os from 'os';

export interface CheckpointInfo {
  file_name: string;
  timestamp: string;
  tool: string;
  modified_files: string;
}

class CheckpointService {
  private checkpoints: CheckpointInfo[] = [];
  private initialized: boolean = false;
  private sessionId: string | null = null;
  private projectHash: string | null = null;

  /**
   * Set current session ID
   */
  setSessionId(sessionId: string): void {
    this.sessionId = sessionId;
  }

  /**
   * Set project hash
   */
  setProjectHash(projectHash: string): void {
    this.projectHash = projectHash;
  }

  /**
   * Get checkpoint directory path for current session
   * Real path: ~/.siada-cli/data/tmp/{project-hash}/checkpoints/{session-id}
   */
  private getCheckpointDir(): string | null {
    if (!this.sessionId) {
      console.warn('[CheckpointService] No session ID set');
      return null;
    }
    
    if (!this.projectHash) {
      console.warn('[CheckpointService] No project hash set');
      return null;
    }
    
    // Checkpoint directory: ~/.siada-cli/data/tmp/{project-hash}/checkpoints/{session-id}
    const homeDir = os.homedir();
    const checkpointDir = path.join(homeDir, '.siada-cli', 'data', 'tmp', this.projectHash, 'checkpoints', this.sessionId);
    
    return checkpointDir;
  }

  /**
   * Read checkpoints from file system
   */
  private readCheckpointsFromFS(): CheckpointInfo[] {
    const checkpointDir = this.getCheckpointDir();
    if (!checkpointDir) {
      return [];
    }

    try {
      // Check if directory exists
      if (!fs.existsSync(checkpointDir)) {
        return [];
      }

      // Read all .json files in the directory
      const files = fs.readdirSync(checkpointDir);
      const checkpointFiles = files.filter(f => f.endsWith('.json'));

      // Parse each checkpoint file
      const checkpoints: CheckpointInfo[] = [];
      for (const file of checkpointFiles) {
        try {
          const filePath = path.join(checkpointDir, file);
          const content = fs.readFileSync(filePath, 'utf-8');
          const data = JSON.parse(content);
          
          // Extract checkpoint info
          checkpoints.push({
            file_name: file,
            timestamp: data.timestamp || new Date(fs.statSync(filePath).mtime).toISOString(),
            tool: data.tool || 'unknown',
            modified_files: data.modified_files ? data.modified_files.join(', ') : ''
          });
        } catch (err) {
          console.error(`[CheckpointService] Error reading checkpoint file ${file}:`, err);
        }
      }

      // Sort by timestamp (newest first)
      checkpoints.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

      return checkpoints;
    } catch (err) {
      console.error('[CheckpointService] Error reading checkpoints from file system:', err);
      return [];
    }
  }

  /**
   * Update checkpoints from backend
   */
  updateCheckpointsFromBackend(checkpoints: CheckpointInfo[]): void {
    this.checkpoints = checkpoints;
    this.initialized = true;
  }

  /**
   * Get all checkpoints (from backend cache or file system)
   */
  getCheckpoints(): CheckpointInfo[] {
    // If we have backend data, use it
    if (this.checkpoints.length > 0) {
      return this.checkpoints;
    }
    
    // Otherwise, read from file system
    return this.readCheckpointsFromFS();
  }

  /**
   * Get checkpoint file names for completion
   */
  getCheckpointFileNames(): string[] {
    return this.getCheckpoints().map(cp => cp.file_name);
  }

  /**
   * Search checkpoints by partial file name
   * Always reads from file system to get latest data
   */
  searchCheckpoints(query: string): CheckpointInfo[] {
    // Always read from file system for latest data
    const checkpoints = this.readCheckpointsFromFS();
    
    if (!query) {
      return checkpoints;
    }
    
    const lowerQuery = query.toLowerCase();
    const filtered = checkpoints.filter(cp => 
      cp.file_name.toLowerCase().includes(lowerQuery)
    );
    
    return filtered;
  }

  /**
   * Check if service is initialized
   */
  isInitialized(): boolean {
    return this.initialized;
  }

  /**
   * Initialize with fallback data (empty list)
   */
  initializeWithFallback(): void {
    if (!this.initialized) {
      this.checkpoints = [];
      this.initialized = true;
    }
  }
}

// Export singleton instance
export const checkpointService = new CheckpointService();
