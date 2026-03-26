/**
 * Session Loader Service
 * Loads session data from filesystem
 */

import { readFileSync, writeFileSync, readdirSync, existsSync, statSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';
import { createHash } from 'crypto';
import { SessionInfo } from '../types/session.js';
import { logger } from '../utils/logger.js';

interface SessionMetadata {
  created_at: string;
  last_updated: string;
  message_count: number;
  first_user_message: string;
  model_name?: string;
  custom_name?: string;
}

function stripTaskTags(text: string): string {
  return text
    .replace(/^\s*<task>\s*/s, '')
    .replace(/\s*<\/task>[\s\S]*$/s, '')
    .trim();
}

interface ProjectMetadata {
  project_root: string;
  project_name: string;
  created_at?: string;
  last_accessed?: string;
}

/**
 * Calculate project hash (same as Python backend)
 */
function getProjectHash(projectRoot: string): string {
  return createHash('sha256').update(projectRoot).digest('hex');
}

/**
 * Get global temp directory
 */
function getGlobalTempDir(): string {
  return join(homedir(), '.siada-cli', 'data', 'tmp');
}

/**
 * Get sessions directory for a project
 */
function getProjectSessionsDir(projectRoot: string): string {
  const projectHash = getProjectHash(projectRoot);
  return join(getGlobalTempDir(), projectHash, 'sessions');
}

/**
 * Load project metadata
 */
function loadProjectMetadata(projectDir: string): ProjectMetadata {
  const metadataPath = join(projectDir, 'project_metadata.json');
  
  if (existsSync(metadataPath)) {
    try {
      const data = readFileSync(metadataPath, 'utf-8');
      return JSON.parse(data);
    } catch (error) {
      logger.warn('Failed to load project metadata', { projectDir, error });
    }
  }
  
  // Fallback: extract from path
  const parts = projectDir.split('/');
  const projectHash = parts[parts.length - 1];
  return {
    project_root: 'Unknown',
    project_name: projectHash.substring(0, 8),
  };
}

/**
 * Load session metadata
 */
function loadSessionMetadata(sessionDir: string, sessionId: string): SessionMetadata | null {
  const metadataPath = join(sessionDir, 'metadata.json');
  const apiHistoryPath = join(sessionDir, 'api_history.json');
  
  const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB limit
  
  // Try metadata.json first
  if (existsSync(metadataPath)) {
    try {
      // Check file size
      const stats = statSync(metadataPath);
      if (stats.size > MAX_FILE_SIZE) {
        logger.warn('metadata.json too large, skipping', { 
          sessionId, 
          size: stats.size 
        });
        return null;
      }
      
      const data = readFileSync(metadataPath, 'utf-8');
      return JSON.parse(data);
    } catch (error) {
      logger.warn('Failed to load metadata.json', { sessionId, error });
    }
  }
  
  // Fallback: extract from api_history.json
  if (existsSync(apiHistoryPath)) {
    try {
      // Check file size
      const stats = statSync(apiHistoryPath);
      if (stats.size > MAX_FILE_SIZE) {
        logger.warn('api_history.json too large, skipping', { 
          sessionId, 
          size: stats.size 
        });
        // Return basic metadata from file stats
        return {
          created_at: stats.birthtime.toISOString(),
          last_updated: stats.mtime.toISOString(),
          message_count: 0,
          first_user_message: 'Session (file too large)',
        };
      }
      
      const data = readFileSync(apiHistoryPath, 'utf-8');
      const history = JSON.parse(data);
      const items = history.items || [];
      
      // Extract first user message
      let firstUserMessage = 'Untitled Session';
      for (const item of items) {
        if (item.role === 'user') {
          const text = item.text || (typeof item.content === 'string' ? item.content : '');
          if (text) {
            firstUserMessage = stripTaskTags(text).substring(0, 100);
            break;
          }
        }
      }
      
      return {
        created_at: stats.birthtime.toISOString(),
        last_updated: stats.mtime.toISOString(),
        message_count: items.length,
        first_user_message: firstUserMessage || 'Untitled Session',
      };
    } catch (error) {
      logger.warn('Failed to extract metadata from api_history.json', { sessionId, error });
    }
  }
  
  return null;
}

/**
 * Load sessions for current project
 */
export function loadCurrentProjectSessions(
  projectRoot: string,
  currentSessionId?: string
): SessionInfo[] {
  const sessions: SessionInfo[] = [];
  const sessionsDir = getProjectSessionsDir(projectRoot);
  
  if (!existsSync(sessionsDir)) {
    logger.info('Sessions directory does not exist', { sessionsDir });
    return sessions;
  }
  
  const projectName = projectRoot.split('/').pop() || 'Unknown';
  
  try {
    const sessionDirs = readdirSync(sessionsDir);
    
    for (const sessionId of sessionDirs) {
      try {
        const sessionDir = join(sessionsDir, sessionId);
        
        const stat = statSync(sessionDir);
        if (!stat.isDirectory()) {
          continue;
        }
        
        const metadata = loadSessionMetadata(sessionDir, sessionId);
        if (!metadata) {
          continue;
        }

        // Skip empty sessions (no messages and no title)
        if (!metadata.message_count && !metadata.first_user_message) {
          continue;
        }

        sessions.push({
          id: sessionId,
          index: 0, // Will be set after sorting
          sessionId: sessionId,
          firstUserMessage: stripTaskTags(metadata.first_user_message || 'Untitled Session'),
          messageCount: metadata.message_count || 0,
          lastUpdated: metadata.last_updated || new Date().toISOString(),
          startTime: metadata.created_at || new Date().toISOString(),
          isCurrentSession: sessionId === currentSessionId,
          projectRoot: projectRoot || 'Unknown',
          projectName: projectName || 'Unknown',
          displayName: metadata.custom_name || undefined,
        });
      } catch (error) {
        logger.warn('Failed to load session', { sessionId, error });
        continue;
      }
    }
    
    // Sort by creation time (oldest first)
    sessions.sort((a, b) => a.startTime.localeCompare(b.startTime));
    
    // Assign indices (1-based)
    sessions.forEach((session, idx) => {
      session.index = idx + 1;
    });
    
    logger.info('Loaded current project sessions', { 
      projectRoot, 
      count: sessions.length 
    });
    
  } catch (error) {
    logger.error('Failed to load current project sessions', { projectRoot, error });
  }
  
  return sessions;
}

/**
 * Load sessions from all projects
 */
export function loadAllProjectsSessions(currentSessionId?: string): SessionInfo[] {
  const allSessions: SessionInfo[] = [];
  const globalTempDir = getGlobalTempDir();
  
  if (!existsSync(globalTempDir)) {
    logger.info('Global temp directory does not exist', { globalTempDir });
    return allSessions;
  }
  
  try {
    const projectDirs = readdirSync(globalTempDir);
    
    for (const projectHash of projectDirs) {
      const projectDir = join(globalTempDir, projectHash);
      
      if (!statSync(projectDir).isDirectory()) {
        continue;
      }
      
      const sessionsDir = join(projectDir, 'sessions');
      if (!existsSync(sessionsDir)) {
        continue;
      }
      
      // Load project metadata
      const projectMetadata = loadProjectMetadata(projectDir);
      
      // Load all sessions in this project
      const sessionDirs = readdirSync(sessionsDir);
      
      for (const sessionId of sessionDirs) {
        try {
          const sessionDir = join(sessionsDir, sessionId);
          
          const stat = statSync(sessionDir);
          if (!stat.isDirectory()) {
            continue;
          }
          
          const metadata = loadSessionMetadata(sessionDir, sessionId);
          if (!metadata) {
            continue;
          }

          // Skip empty sessions (no messages and no title)
          if (!metadata.message_count && !metadata.first_user_message) {
            continue;
          }

          allSessions.push({
            id: sessionId,
            index: 0, // Will be set after sorting
            sessionId: sessionId,
            firstUserMessage: stripTaskTags(metadata.first_user_message || 'Untitled Session'),
            messageCount: metadata.message_count || 0,
            lastUpdated: metadata.last_updated || new Date().toISOString(),
            startTime: metadata.created_at || new Date().toISOString(),
            isCurrentSession: sessionId === currentSessionId,
            projectRoot: projectMetadata.project_root || 'Unknown',
            projectName: projectMetadata.project_name || 'Unknown',
            displayName: metadata.custom_name || undefined,
          });
        } catch (error) {
          logger.warn('Failed to load session from project', { 
            sessionId, 
            projectHash, 
            error 
          });
          continue;
        }
      }
    }
    
    // Sort by creation time (oldest first)
    allSessions.sort((a, b) => a.startTime.localeCompare(b.startTime));
    
    // Assign indices (1-based)
    allSessions.forEach((session, idx) => {
      session.index = idx + 1;
    });
    
    logger.info('Loaded all projects sessions', { 
      projectCount: projectDirs.length,
      sessionCount: allSessions.length 
    });
    
  } catch (error) {
    logger.error('Failed to load all projects sessions', { error });
  }
  
  return allSessions;
}

/**
 * Load sessions based on scope
 */
export function loadSessions(
  scope: 'current' | 'all',
  projectRoot: string,
  currentSessionId?: string
): SessionInfo[] {
  if (scope === 'all') {
    return loadAllProjectsSessions(currentSessionId);
  } else {
    return loadCurrentProjectSessions(projectRoot, currentSessionId);
  }
}

/**
 * Rename a session by writing custom_name to its metadata.json
 */
export function renameSession(
  sessionId: string,
  projectRoot: string,
  newName: string,
): void {
  const sessionDir = join(getProjectSessionsDir(projectRoot), sessionId);
  const metadataPath = join(sessionDir, 'metadata.json');

  if (!existsSync(metadataPath)) {
    throw new Error(`Session metadata not found: ${metadataPath}`);
  }

  const raw = readFileSync(metadataPath, 'utf-8');
  const metadata = JSON.parse(raw);

  if (newName.trim()) {
    metadata.custom_name = newName.trim();
  } else {
    delete metadata.custom_name;
  }

  writeFileSync(metadataPath, JSON.stringify(metadata, null, 2), 'utf-8');
  logger.info('Session renamed', { sessionId, newName });
}
