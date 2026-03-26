/**
 * Session Utilities
 * Helper functions for session data processing
 */

import { SessionInfo } from '../types/session.js';

/**
 * Format time ago string
 */
export function formatTimeAgo(isoString: string): string {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSeconds = Math.floor(diffMs / 1000);
    const diffMinutes = Math.floor(diffSeconds / 60);
    const diffHours = Math.floor(diffMinutes / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSeconds < 60) {
      return `${diffSeconds} seconds ago`;
    } else if (diffMinutes < 60) {
      return `${diffMinutes} minute${diffMinutes > 1 ? 's' : ''} ago`;
    } else if (diffHours < 24) {
      return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
    } else if (diffDays < 7) {
      return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`;
    } else {
      return date.toLocaleDateString();
    }
  } catch {
    return isoString;
  }
}

/**
 * Format file size
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes}B`;
  } else if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)}KB`;
  } else {
    return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
  }
}

/**
 * Truncate text with ellipsis
 */
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) {
    return text;
  }
  return text.substring(0, maxLength - 3) + '...';
}

/**
 * Sort sessions by different criteria
 */
export function sortSessions(
  sessions: SessionInfo[],
  sortOrder: 'date' | 'messages' | 'name',
  reverse: boolean = false
): SessionInfo[] {
  const sorted = [...sessions].sort((a, b) => {
    let comparison = 0;
    
    switch (sortOrder) {
      case 'date':
        comparison = new Date(b.lastUpdated).getTime() - new Date(a.lastUpdated).getTime();
        break;
      case 'messages':
        comparison = b.messageCount - a.messageCount;
        break;
      case 'name':
        comparison = a.firstUserMessage.localeCompare(b.firstUserMessage);
        break;
    }
    
    return reverse ? -comparison : comparison;
  });
  
  return sorted;
}

/**
 * Filter sessions by search query
 */
export function filterSessions(
  sessions: SessionInfo[],
  query: string
): SessionInfo[] {
  if (!query.trim()) {
    return sessions;
  }

  const lowerQuery = query.toLowerCase();
  
  return sessions.filter(session => {
    // Search in first user message
    if (session.firstUserMessage.toLowerCase().includes(lowerQuery)) {
      return true;
    }
    
    // Search in session ID
    if (session.sessionId.toLowerCase().includes(lowerQuery)) {
      return true;
    }
    
    return false;
  });
}

/**
 * Clean message text (remove control characters)
 */
export function cleanMessage(text: string): string {
  return text
    .replace(/\n/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/[^\x20-\x7E]/g, '')
    .trim();
}

/**
 * Calculate visible range for pagination
 */
export function calculateVisibleRange(
  totalCount: number,
  activeIndex: number,
  visibleCount: number
): { startIndex: number; endIndex: number; scrollOffset: number } {
  // Keep active item centered if possible
  const halfVisible = Math.floor(visibleCount / 2);
  let startIndex = Math.max(0, activeIndex - halfVisible);
  let endIndex = Math.min(totalCount, startIndex + visibleCount);
  
  // Adjust if we're near the end
  if (endIndex - startIndex < visibleCount) {
    startIndex = Math.max(0, endIndex - visibleCount);
  }
  
  const scrollOffset = startIndex;
  
  return { startIndex, endIndex, scrollOffset };
}
