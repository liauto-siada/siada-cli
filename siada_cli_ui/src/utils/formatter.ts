/**
 * Formatting Utilities
 * Provides text formatting, time formatting, and data formatting utilities
 */

/**
 * Format file size in human-readable format
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const k = 1024;
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${units[i]}`;
}

/**
 * Format duration in human-readable format
 */
export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  if (ms < 3600000) return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
  
  const hours = Math.floor(ms / 3600000);
  const minutes = Math.floor((ms % 3600000) / 60000);
  return `${hours}h ${minutes}m`;
}

/**
 * Format a duration given in whole seconds as a single short unit
 * ("2h", "5m", "30s") — used by the collapsible "Goal achieved (2h · 1 turn
 * · 134.1k tokens)" summary line. Unlike formatDuration (which composes
 * hours+minutes, seconds+ms, etc.), this deliberately picks just ONE unit
 * to match that compact style.
 */
export function formatElapsedShort(totalSeconds: number): string {
  const seconds = Math.max(0, Math.round(totalSeconds));
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

/**
 * Format a raw token count as a short human-readable string ("134.1k",
 * "2.3M", "842") — used alongside formatElapsedShort in the same summary line.
 */
export function formatTokensShort(count: number): string {
  const n = Math.max(0, count);
  if (n < 1000) return `${n}`;
  if (n < 1000000) return `${(n / 1000).toFixed(1)}k`;
  return `${(n / 1000000).toFixed(1)}M`;
}

/**
 * Format timestamp in relative time (e.g., "2 minutes ago")
 */
export function formatRelativeTime(timestamp: string | Date): string {

  const date = typeof timestamp === 'string' ? new Date(timestamp) : timestamp;
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  
  if (seconds < 60) return 'just now';
  if (minutes < 60) return `${minutes} minute${minutes > 1 ? 's' : ''} ago`;
  if (hours < 24) return `${hours} hour${hours > 1 ? 's' : ''} ago`;
  if (days < 7) return `${days} day${days > 1 ? 's' : ''} ago`;
  
  return formatDate(date);
}

/**
 * Format date in readable format
 */
export function formatDate(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

/**
 * Format time in readable format
 */
export function formatTime(date: Date | string): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

/**
 * Format datetime in readable format
 */
export function formatDateTime(date: Date | string): string {
  return `${formatDate(date)} ${formatTime(date)}`;
}

/**
 * Format timestamp for logs (ISO format with milliseconds)
 */
export function formatTimestampLog(date: Date = new Date()): string {
  return date.toISOString();
}

/**
 * Truncate text with ellipsis
 */
export function truncate(text: string, maxLength: number, ellipsis: string = '...'): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - ellipsis.length) + ellipsis;
}

/**
 * Truncate text in the middle
 */
export function truncateMiddle(text: string, maxLength: number, separator: string = '...'): string {
  if (text.length <= maxLength) return text;
  
  const charsToShow = maxLength - separator.length;
  const frontChars = Math.ceil(charsToShow / 2);
  const backChars = Math.floor(charsToShow / 2);
  
  return text.slice(0, frontChars) + separator + text.slice(-backChars);
}

/**
 * Wrap text to specified width
 */
export function wrapText(text: string, width: number): string[] {
  const words = text.split(' ');
  const lines: string[] = [];
  let currentLine = '';
  
  for (const word of words) {
    if ((currentLine + word).length <= width) {
      currentLine += (currentLine ? ' ' : '') + word;
    } else {
      if (currentLine) lines.push(currentLine);
      currentLine = word;
    }
  }
  
  if (currentLine) lines.push(currentLine);
  return lines;
}

/**
 * Pad text to specified width
 */
export function padText(text: string, width: number, align: 'left' | 'center' | 'right' = 'left'): string {
  if (text.length >= width) return text;
  
  const padding = width - text.length;
  
  switch (align) {
    case 'right':
      return ' '.repeat(padding) + text;
    case 'center':
      const leftPad = Math.floor(padding / 2);
      const rightPad = padding - leftPad;
      return ' '.repeat(leftPad) + text + ' '.repeat(rightPad);
    default:
      return text + ' '.repeat(padding);
  }
}

/**
 * Format number with commas
 */
export function formatNumber(num: number): string {
  return num.toLocaleString('en-US');
}

/**
 * Format percentage
 */
export function formatPercentage(value: number, total: number, decimals: number = 1): string {
  const percentage = (value / total) * 100;
  return `${percentage.toFixed(decimals)}%`;
}

/**
 * Format JSON with indentation
 */
export function formatJSON(obj: any, indent: number = 2): string {
  return JSON.stringify(obj, null, indent);
}

/**
 * Format key-value pairs as table
 */
export function formatKeyValue(data: Record<string, any>, separator: string = ': '): string {
  const maxKeyLength = Math.max(...Object.keys(data).map(k => k.length));
  
  return Object.entries(data)
    .map(([key, value]) => {
      const paddedKey = key.padEnd(maxKeyLength);
      return `${paddedKey}${separator}${value}`;
    })
    .join('\n');
}

/**
 * Format list with bullets
 */
export function formatList(items: string[], bullet: string = '•'): string {
  return items.map(item => `${bullet} ${item}`).join('\n');
}

/**
 * Format numbered list
 */
export function formatNumberedList(items: string[]): string {
  return items.map((item, i) => `${i + 1}. ${item}`).join('\n');
}

/**
 * Format tree structure
 */
export function formatTree(
  items: Array<{ name: string; level: number; isLast?: boolean }>,
  indent: string = '  '
): string {
  return items.map(({ name, level, isLast }) => {
    const prefix = indent.repeat(level);
    const connector = isLast ? '└─ ' : '├─ ';
    return `${prefix}${level > 0 ? connector : ''}${name}`;
  }).join('\n');
}

/**
 * Format code block with syntax highlighting markers
 */
export function formatCodeBlock(code: string, language?: string): string {
  const header = language ? `\`\`\`${language}\n` : '```\n';
  const footer = '\n```';
  return header + code + footer;
}

/**
 * Format diff output
 */
export function formatDiff(oldText: string, newText: string): string {
  const oldLines = oldText.split('\n');
  const newLines = newText.split('\n');
  const diff: string[] = [];
  
  // Simple line-by-line diff
  const maxLines = Math.max(oldLines.length, newLines.length);
  
  for (let i = 0; i < maxLines; i++) {
    const oldLine = oldLines[i];
    const newLine = newLines[i];
    
    if (oldLine === newLine) {
      diff.push(`  ${oldLine || ''}`);
    } else {
      if (oldLine !== undefined) diff.push(`- ${oldLine}`);
      if (newLine !== undefined) diff.push(`+ ${newLine}`);
    }
  }
  
  return diff.join('\n');
}

/**
 * Format path with highlighting
 */
export function formatPath(path: string, maxLength?: number): string {
  if (maxLength && path.length > maxLength) {
    return truncateMiddle(path, maxLength, '...');
  }
  return path;
}

/**
 * Format command with arguments
 */
export function formatCommand(command: string, args: string[]): string {
  return `${command} ${args.join(' ')}`;
}

/**
 * Format status badge
 */
export function formatStatusBadge(status: string): string {
  const badges: Record<string, string> = {
    success: '[✓]',
    error: '[✗]',
    warning: '[!]',
    info: '[i]',
    pending: '[⋯]',
    running: '[→]',
  };
  return badges[status] || `[${status}]`;
}

/**
 * Format progress bar
 */
export function formatProgressBar(
  current: number,
  total: number,
  width: number = 20,
  fillChar: string = '█',
  emptyChar: string = '░'
): string {
  const percentage = current / total;
  const filled = Math.floor(width * percentage);
  const empty = width - filled;
  
  const bar = fillChar.repeat(filled) + emptyChar.repeat(empty);
  const percent = formatPercentage(current, total, 0);
  
  return `${bar} ${percent}`;
}

/**
 * Format table row
 */
export function formatTableRow(columns: string[], widths: number[]): string {
  return columns.map((col, i) => padText(col, widths[i])).join(' | ');
}

/**
 * Format table
 */
export function formatTable(
  headers: string[],
  rows: string[][],
  padding: number = 1
): string {
  // Calculate column widths
  const widths = headers.map((header, i) => {
    const maxContentWidth = Math.max(
      ...rows.map(row => (row[i] || '').length)
    );
    return Math.max(header.length, maxContentWidth) + padding * 2;
  });
  
  // Format header
  const headerRow = formatTableRow(headers, widths);
  const separator = widths.map(w => '─'.repeat(w)).join('─┼─');
  
  // Format rows
  const formattedRows = rows.map(row => formatTableRow(row, widths));
  
  return [headerRow, separator, ...formattedRows].join('\n');
}

/**
 * Format error message
 */
export function formatError(error: Error | string): string {
  if (typeof error === 'string') return error;
  return `${error.name}: ${error.message}`;
}

/**
 * Format stack trace
 */
export function formatStackTrace(error: Error): string {
  return error.stack || formatError(error);
}

/**
 * Pluralize word
 */
export function pluralize(count: number, singular: string, plural?: string): string {
  if (count === 1) return singular;
  return plural || `${singular}s`;
}

/**
 * Format count with word
 */
export function formatCount(count: number, singular: string, plural?: string): string {
  return `${count} ${pluralize(count, singular, plural)}`;
}

/**
 * Capitalize first letter
 */
export function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Title case
 */
export function titleCase(text: string): string {
  return text.split(' ').map(capitalize).join(' ');
}

/**
 * Camel case to title case
 */
export function camelToTitle(text: string): string {
  return text
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, str => str.toUpperCase())
    .trim();
}

/**
 * Snake case to title case
 */
export function snakeToTitle(text: string): string {
  return titleCase(text.replace(/_/g, ' '));
}
