/**
 * Rendering limits to prevent Terminal crashes
 * These limits help avoid memory corruption in CoreGraphics text rendering
 * 
 * - Limit by LINES, not just BYTES
 * - Terminal.app crashes from rendering too many lines
 * - Line-based limits are more predictable than byte-based
 */

// Line-based limits
// These are more effective than byte-based limits for preventing crashes
export const MAX_MESSAGE_LINES = 20;       // Single message: max 500 lines
export const MAX_VISIBLE_LINES = 100;       // Single render pass: max 100 lines  
export const MAX_CODE_BLOCK_LINES = 200;    // Code blocks: max 200 lines
export const MAX_RESPONSE_LINES = 1000; // Complete response: max 1000 lines

export const MAX_TEXT_LENGTH = 5000; // of text (safer for Terminal.app)

// Maximum number of lines to render at once (DEPRECATED - use MAX_VISIBLE_LINES)
export const MAX_LINES_TO_RENDER = 1000;

// Maximum length for markdown content
export const MAX_MARKDOWN_LENGTH = 100000; // ~100KB

// Maximum code block size
export const MAX_CODE_BLOCK_LENGTH = 10000;

// Debounce delay for rapid updates (milliseconds)
// Increased to reduce render frequency and prevent terminal crashes
export const RENDER_DEBOUNCE_MS = 50; // ~20fps, safer for terminal stability

// Maximum number of message history items to keep in memory
// CRITICAL: Enforced in reducer to prevent unbounded growth and memory leaks
// 🔴 Reduced from 50 to 30 due to Terminal.app Type C crash
export const MAX_MESSAGE_HISTORY = 30; // More aggressive for Terminal.app stability

// Minimum messages to keep (last N conversations)
// When trimming, always keep at least this many recent messages
export const MIN_MESSAGE_HISTORY = 20;

// Maximum undo stack size (already defined in TextBuffer, but kept here for reference)
export const MAX_UNDO_STACK_SIZE = 100;

// Memory monitoring interval (milliseconds)
export const MEMORY_CHECK_INTERVAL = 30000; // Check every 30 seconds

// Memory warning threshold (MB)
export const MEMORY_WARNING_THRESHOLD = 200; // Warn if heap used exceeds 200MB

// Message splitting thresholds (for rendering optimization)
export const MESSAGE_SPLIT_THRESHOLD = 20; // Split message after 2 lines (FOR TESTING)
export const MIN_PENDING_CONTENT_LINES = 10; // Keep at least 1 line in pending state (FOR TESTING)
export const MAX_STATIC_MESSAGE_LINES = 1000; // Maximum lines for a static message
