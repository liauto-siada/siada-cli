/**
 * Text Highlighter Utilities
 * Smart detection and highlighting for file paths, bash commands, and inline code
 */

/**
 * Text segment type for highlighting
 */
export type SegmentType = 
  | 'text'        // Normal text
  | 'path'        // File path
  | 'command'     // Bash command
  | 'inlineCode'  // Inline code
  | 'url';        // URL

export interface TextSegment {
  type: SegmentType;
  content: string;
  start: number;
  end: number;
}

/**
 * File path detection patterns
 */
const PATH_PATTERNS = {
  // Unix absolute path: /path/to/file or /path/to/dir/
  unixAbsolute: /(?:^|\s)(\/(?:[a-zA-Z0-9_\-]+\/)*[a-zA-Z0-9_\-.*]+\/?)/g,
  
  // Windows absolute path: C:\path\to\file
  windowsAbsolute: /(?:^|\s)([A-Z]:\\(?:[a-zA-Z0-9_\-]+\\)*[a-zA-Z0-9_\-.*]+\\?)/g,
  
  // Relative path: ./path or ../path
  relative: /(?:^|\s)(\.\.?\/(?:[a-zA-Z0-9_\-]+\/)*[a-zA-Z0-9_\-.*]*)/g,
  
  // Home directory path: ~/path
  home: /(?:^|\s)(~\/(?:[a-zA-Z0-9_\-]+\/)*[a-zA-Z0-9_\-.*]*)/g,
};

/**
 * Bash command detection patterns
 */
const COMMAND_PATTERNS = {
  // Command with prompt: $ command or # command
  withPrompt: /^([$#]\s+.+)/gm,
  
  // Common shell commands at line start
  commonCommands: /^((?:cd|ls|pwd|mkdir|rm|cp|mv|cat|grep|find|touch|chmod|chown|sudo|npm|yarn|pnpm|git|docker|kubectl|ssh|scp|curl|wget|tar|zip|unzip|ps|kill|top|df|du|which|export|source|echo|printf)\s+.+)/gm,
  
  // Commands with pipes and redirections
  withPipes: /^([a-zA-Z0-9_\-./]+\s+[^|>]*[|>&]+.+)/gm,
};

/**
 * Inline code detection patterns
 */
const CODE_PATTERNS = {
  // Backtick wrapped: `code`
  backtick: /`([^`]+)`/g,
  
  // Function calls: functionName(args)
  functionCall: /\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(/g,
  
  // Camel case: camelCase, PascalCase
  camelCase: /\b([a-z][a-z0-9]*[A-Z][a-zA-Z0-9]*)\b/g,
  
  // Snake case: snake_case_name
  snakeCase: /\b([a-z_][a-z0-9_]*_[a-z0-9_]+)\b/g,
  
  // Kebab case with hyphens: kebab-case-name
  kebabCase: /\b([a-z][a-z0-9]*-[a-z0-9-]+)\b/g,
};

/**
 * URL detection pattern
 */
const URL_PATTERN = /(?:https?|ftp):\/\/[^\s]+/g;

/**
 * Detect if text is a file path
 */
export function isFilePath(text: string): boolean {
  const trimmed = text.trim();
  
  // Check Unix absolute path
  if (/^\/[a-zA-Z0-9_\-/.]+/.test(trimmed)) {
    return true;
  }
  
  // Check Windows absolute path
  if (/^[A-Z]:\\[a-zA-Z0-9_\-\\/]+/.test(trimmed)) {
    return true;
  }
  
  // Check relative path
  if (/^\.\.?\//.test(trimmed)) {
    return true;
  }
  
  // Check home directory path
  if (/^~\//.test(trimmed)) {
    return true;
  }
  
  return false;
}

/**
 * Detect if text is a bash command
 */
export function isBashCommand(text: string): boolean {
  const trimmed = text.trim();
  
  // Check for command prompt
  if (/^[$#]\s+/.test(trimmed)) {
    return true;
  }
  
  // Check for common shell commands
  const commonShellCommands = [
    'cd', 'ls', 'pwd', 'mkdir', 'rm', 'cp', 'mv', 'cat', 'grep', 'find',
    'touch', 'chmod', 'chown', 'sudo', 'npm', 'yarn', 'pnpm', 'git',
    'docker', 'kubectl', 'ssh', 'scp', 'curl', 'wget', 'tar', 'zip',
    'unzip', 'ps', 'kill', 'top', 'df', 'du', 'which', 'export',
    'source', 'echo', 'printf', 'node', 'python', 'pip', 'make',
  ];
  
  const firstWord = trimmed.split(/\s+/)[0];
  if (commonShellCommands.includes(firstWord)) {
    return true;
  }
  
  // Check for pipes or redirections
  if (/[|>&]/.test(trimmed)) {
    return true;
  }
  
  return false;
}

/**
 * Extract file paths from text
 */
export function extractFilePaths(text: string): TextSegment[] {
  const segments: TextSegment[] = [];
  
  // Check all path patterns
  Object.values(PATH_PATTERNS).forEach(pattern => {
    const regex = new RegExp(pattern.source, pattern.flags);
    let match;
    
    while ((match = regex.exec(text)) !== null) {
      const content = match[1];
      const start = match.index + (match[0].length - content.length);
      
      segments.push({
        type: 'path',
        content,
        start,
        end: start + content.length,
      });
    }
  });
  
  return segments;
}

/**
 * Extract bash commands from text
 */
export function extractBashCommands(text: string): TextSegment[] {
  const segments: TextSegment[] = [];
  
  // Check all command patterns
  Object.values(COMMAND_PATTERNS).forEach(pattern => {
    const regex = new RegExp(pattern.source, pattern.flags);
    let match;
    
    while ((match = regex.exec(text)) !== null) {
      const content = match[1];
      const start = match.index;
      
      segments.push({
        type: 'command',
        content,
        start,
        end: start + content.length,
      });
    }
  });
  
  return segments;
}

/**
 * Extract inline code from text
 */
export function extractInlineCode(text: string): TextSegment[] {
  const segments: TextSegment[] = [];
  
  // Only check backtick pattern for inline code
  // Other patterns are too aggressive and may cause false positives
  const regex = new RegExp(CODE_PATTERNS.backtick.source, CODE_PATTERNS.backtick.flags);
  let match;
  
  while ((match = regex.exec(text)) !== null) {
    segments.push({
      type: 'inlineCode',
      content: match[0], // Include backticks
      start: match.index,
      end: match.index + match[0].length,
    });
  }
  
  return segments;
}

/**
 * Extract URLs from text
 */
export function extractURLs(text: string): TextSegment[] {
  const segments: TextSegment[] = [];
  const regex = new RegExp(URL_PATTERN.source, URL_PATTERN.flags);
  let match;
  
  while ((match = regex.exec(text)) !== null) {
    segments.push({
      type: 'url',
      content: match[0],
      start: match.index,
      end: match.index + match[0].length,
    });
  }
  
  return segments;
}

/**
 * Merge overlapping segments, prioritizing certain types
 */
function mergeSegments(segments: TextSegment[]): TextSegment[] {
  if (segments.length === 0) return [];
  
  // Sort by start position
  const sorted = [...segments].sort((a, b) => a.start - b.start);
  
  // Priority order: url > inlineCode > command > path
  const priority: Record<SegmentType, number> = {
    url: 4,
    inlineCode: 3,
    command: 2,
    path: 1,
    text: 0,
  };
  
  const merged: TextSegment[] = [];
  let current = sorted[0];
  
  for (let i = 1; i < sorted.length; i++) {
    const next = sorted[i];
    
    // Check for overlap
    if (next.start < current.end) {
      // Keep the higher priority segment
      if (priority[next.type] > priority[current.type]) {
        current = next;
      }
      // If same priority, keep the longer one
      else if (priority[next.type] === priority[current.type]) {
        if (next.end - next.start > current.end - current.start) {
          current = next;
        }
      }
    } else {
      merged.push(current);
      current = next;
    }
  }
  
  merged.push(current);
  return merged;
}

/**
 * Highlight text segments
 * Returns an array of segments with types for different highlighting
 */
export function highlightSegments(
  text: string,
  options: {
    enablePathHighlight?: boolean;
    enableCommandHighlight?: boolean;
    enableCodeHighlight?: boolean;
    enableURLHighlight?: boolean;
  } = {}
): TextSegment[] {
  const {
    enablePathHighlight = true,
    enableCommandHighlight = true,
    enableCodeHighlight = true,
    enableURLHighlight = true,
  } = options;
  
  const allSegments: TextSegment[] = [];
  
  // Extract all types of segments
  if (enableURLHighlight) {
    allSegments.push(...extractURLs(text));
  }
  
  if (enableCodeHighlight) {
    allSegments.push(...extractInlineCode(text));
  }
  
  if (enableCommandHighlight) {
    allSegments.push(...extractBashCommands(text));
  }
  
  if (enablePathHighlight) {
    allSegments.push(...extractFilePaths(text));
  }
  
  // Merge overlapping segments
  const merged = mergeSegments(allSegments);
  
  // Fill in text segments for non-highlighted parts
  const result: TextSegment[] = [];
  let lastEnd = 0;
  
  for (const segment of merged) {
    // Add text segment before this special segment
    if (segment.start > lastEnd) {
      result.push({
        type: 'text',
        content: text.substring(lastEnd, segment.start),
        start: lastEnd,
        end: segment.start,
      });
    }
    
    result.push(segment);
    lastEnd = segment.end;
  }
  
  // Add remaining text
  if (lastEnd < text.length) {
    result.push({
      type: 'text',
      content: text.substring(lastEnd),
      start: lastEnd,
      end: text.length,
    });
  }
  
  return result;
}

/**
 * Language alias mapping for code blocks
 * Maps common aliases to lowlight-supported language names
 */
export const LANGUAGE_ALIASES: Record<string, string> = {
  // JavaScript variants
  'js': 'javascript',
  'jsx': 'javascript',
  'es6': 'javascript',
  'mjs': 'javascript',
  
  // TypeScript variants
  'ts': 'typescript',
  'tsx': 'typescript',
  
  // Shell variants
  'sh': 'shell',
  'bash': 'bash',
  'zsh': 'shell',
  'fish': 'shell',
  
  // C/C++ variants
  'c++': 'cpp',
  'cc': 'cpp',
  'cxx': 'cpp',
  'h': 'cpp',
  'hpp': 'cpp',
  
  // C# variants
  'cs': 'csharp',
  'c#': 'csharp',
  
  // Python variants
  'py': 'python',
  'python3': 'python',
  'py3': 'python',
  
  // Ruby variants
  'rb': 'ruby',
  
  // Rust variants
  'rs': 'rust',
  
  // Go variants
  'golang': 'go',
  
  // Java variants
  'jsp': 'java',
  
  // PHP variants
  'php3': 'php',
  'php4': 'php',
  'php5': 'php',
  
  // HTML/XML variants
  'html': 'xml',
  'htm': 'xml',
  'xhtml': 'xml',
  'svg': 'xml',
  
  // Config files
  'conf': 'ini',
  'config': 'ini',
  'toml': 'ini',
  
  // Styling
  'sass': 'scss',
  
  // Data formats
  'yml': 'yaml',
  
  // Plain text
  'text': 'plaintext',
  'txt': 'plaintext',
};

/**
 * Normalize language name for code highlighting
 */
export function normalizeLanguage(lang: string | null | undefined): string | null {
  if (!lang) return null;
  
  const normalized = lang.toLowerCase().trim();
  return LANGUAGE_ALIASES[normalized] || normalized;
}

/**
 * Get supported languages list
 */
export const SUPPORTED_LANGUAGES = [
  'arduino', 'bash', 'c', 'cpp', 'csharp', 'css', 'diff', 'go', 'graphql',
  'ini', 'java', 'javascript', 'json', 'kotlin', 'less', 'lua', 'makefile',
  'markdown', 'objectivec', 'perl', 'php', 'php-template', 'plaintext',
  'python', 'python-repl', 'r', 'ruby', 'rust', 'scss', 'shell', 'sql',
  'swift', 'typescript', 'vbnet', 'wasm', 'xml', 'yaml',
] as const;

export type SupportedLanguage = typeof SUPPORTED_LANGUAGES[number];

/**
 * Check if a language is supported
 */
export function isLanguageSupported(lang: string): boolean {
  const normalized = normalizeLanguage(lang);
  if (!normalized) return false;
  
  return SUPPORTED_LANGUAGES.includes(normalized as SupportedLanguage);
}
