/**
 * Tool Call Parser
 * Parses tool call content from formatters.py output patterns
 */

/**
 * Tool call patterns matching formatters.py output
 */
const TOOL_PATTERNS = {
  read_file: /^Read the file `([^`]+)`(?:\s+from line (\d+) to line (\d+))?/,
  view_dir: /^View the directory `([^`]+)`/,
  create_file: /^Create the file `([^`]+)`/,
  update_file: /^In the file `([^`]+)`[,`].*(?:replace|insert)/,
  undo_edit: /^Undo the last edit for the file `([^`]+)`/,
  run_command: /^Run the following command:/,
  run_powershell: /^Run the following PowerShell command:/,
  search: /^Search for: (.+?) in (.+?) with file pattern/,
  analyze: /^Analyze definitions in `([^`]+)`/,
  web: /^(?:Crawl the url:|Fetch URL:|Web search:)\s*(.+)/,
  browser: /^> Siada will (.+)/,
  memory_search: /^Searching memory:\s*(.+)/,
  memory_write: /^Save to memory/,
  fact_store: /^Fact memory(?:\s+(.+))?/,
  fact_feedback: /^Fact feedback(?:\s+(.+))?/,
  sub_agent: /^Sub-agent task:\s*(.+)/,

  lark: /^Send Lark/,
  todo_write: /^(?:Clearing todo list|[○◐✓?]\s+.+)/,
} as const;

export type ToolType = keyof typeof TOOL_PATTERNS;

export interface ParsedToolCall {
  type: ToolType;
  summary: string;
  path?: string;
  details?: string;
  lineStart?: number;
  lineEnd?: number;
}

/**
 * Parse tool call content and extract type and summary
 */
export function parseToolCall(content: string): ParsedToolCall | null {
  if (!content) return null;

  const trimmed = content.trim();

  // Try to match each pattern
  for (const [type, pattern] of Object.entries(TOOL_PATTERNS)) {
    const match = trimmed.match(pattern);
    if (match) {
      return createParsedResult(type as ToolType, match, trimmed);
    }
  }

  return null;
}

/**
 * Create parsed result based on tool type
 */
function createParsedResult(
  type: ToolType,
  match: RegExpMatchArray,
  fullContent: string
): ParsedToolCall {
  switch (type) {
    case 'read_file':
      return {
        type,
        summary: 'Read file',
        path: match[1],
        details: match[1],
        lineStart: match[2] ? parseInt(match[2], 10) : undefined,
        lineEnd: match[3] ? parseInt(match[3], 10) : undefined,
      };

    case 'view_dir':
      return {
        type,
        summary: 'View directory',
        path: match[1],
        details: match[1],
      };

    case 'create_file':
      return {
        type,
        summary: 'Create file',
        path: match[1],
        details: match[1],
      };

    case 'update_file':
      return {
        type,
        summary: 'Update file',
        path: match[1],
        details: match[1],
      };

    case 'undo_edit':
      return {
        type,
        summary: 'Undo edit',
        path: match[1],
        details: match[1],
      };

    case 'run_command':
      // Extract command from code block if present
      const cmdMatch = fullContent.match(/```bash\s*\n(.+?)\n```/s);
      const command = cmdMatch ? cmdMatch[1].trim() : '';
      return {
        type,
        summary: 'Run command',
        details: command,
      };

    case 'run_powershell':
      // Extract command from powershell code block if present
      const psMatch = fullContent.match(/```powershell\s*\n(.+?)\n```/s);
      const psCommand = psMatch ? psMatch[1].trim() : '';
      return {
        type,
        summary: 'Run PowerShell command',
        details: psCommand,
      };

    case 'search':
      return {
        type,
        summary: 'Search',
        details: `${match[1]} in ${match[2]}`,
      };

    case 'analyze':
      return {
        type,
        summary: 'Analyze code',
        path: match[1],
        details: match[1],
      };

    case 'web':
      return {
        type,
        summary: 'Web request',
        details: match[1],
      };

    case 'browser':
      return {
        type,
        summary: 'Browser action',
        details: match[1],
      };

    case 'memory_search':
      return {
        type,
        summary: 'Search memory',
        details: match[1],
      };

    case 'memory_write':
      return {
        type,
        summary: 'Save to memory',
        details: fullContent.substring('Save to memory'.length).trim(),
      };

    case 'fact_store':
      return {
        type,
        summary: 'Fact memory',
        details: (match[1] || '').trim(),
      };

    case 'fact_feedback':
      return {
        type,
        summary: 'Fact feedback',
        details: (match[1] || '').trim(),
      };

    case 'sub_agent':

      return {
        type,
        summary: 'Sub-agent task',
        details: match[1],
      };

    case 'lark':
      return {
        type,
        summary: 'Lark notification',
        details: fullContent.substring('Send Lark'.length).trim(),
      };

    case 'todo_write': {
      const progressMatch = fullContent.match(/\[(\d+)\/(\d+) completed\]/);
      const summary = progressMatch
        ? `Todo List (${progressMatch[1]}/${progressMatch[2]} done)`
        : fullContent.startsWith('Clearing') ? 'Clear todo list' : 'Todo List';
      return {
        type,
        summary,
        details: fullContent,
      };
    }

    default:
      return {
        type,
        summary: 'Tool call',
        details: fullContent,
      };
  }
}

/**
 * Group consecutive tool calls by type
 */
export function groupToolCalls(calls: ParsedToolCall[]): Map<ToolType, ParsedToolCall[]> {
  const groups = new Map<ToolType, ParsedToolCall[]>();

  for (const call of calls) {
    const existing = groups.get(call.type) || [];
    existing.push(call);
    groups.set(call.type, existing);
  }

  return groups;
}

/**
 * Format tool call summary for compact display
 */
export function formatCompactSummary(groups: Map<ToolType, ParsedToolCall[]>): string {
  const parts: string[] = [];

  for (const [type, calls] of groups.entries()) {
    const count = calls.length;
    if (count === 0) continue;

    switch (type) {
      case 'read_file':
        parts.push(count === 1 ? 'Read 1 file' : `Read ${count} files`);
        break;
      case 'view_dir':
        parts.push(count === 1 ? 'View 1 dir' : `View ${count} dirs`);
        break;
      case 'create_file':
        parts.push(count === 1 ? 'Create 1 file' : `Create ${count} files`);
        break;
      case 'update_file':
        parts.push(count === 1 ? 'Update 1 file' : `Update ${count} files`);
        break;
      case 'undo_edit':
        parts.push(count === 1 ? 'Undo 1 edit' : `Undo ${count} edits`);
        break;
      case 'run_command':
        parts.push(count === 1 ? 'Run 1 command' : `Run ${count} commands`);
        break;
      case 'run_powershell':
        parts.push(count === 1 ? 'Run 1 PowerShell command' : `Run ${count} PowerShell commands`);
        break;
      case 'search':
        parts.push(count === 1 ? 'Search' : `${count} searches`);
        break;
      case 'analyze':
        parts.push(count === 1 ? 'Analyze code' : `Analyze ${count} files`);
        break;
      case 'web':
        parts.push(count === 1 ? '1 web request' : `${count} web requests`);
        break;
      case 'browser':
        parts.push(count === 1 ? 'Browser action' : `${count} browser actions`);
        break;
      case 'memory_search':
        parts.push(count === 1 ? 'Search memory' : `${count} memory searches`);
        break;
      case 'memory_write':
        parts.push(count === 1 ? 'Save to memory' : `${count} memory saves`);
        break;
      case 'fact_store':
        parts.push(count === 1 ? 'Fact memory' : `${count} fact memory ops`);
        break;
      case 'fact_feedback':
        parts.push(count === 1 ? 'Fact feedback' : `${count} fact feedbacks`);
        break;
      case 'sub_agent':

        parts.push(count === 1 ? '1 sub-agent task' : `${count} sub-agent tasks`);
        break;
      case 'lark':
        parts.push(count === 1 ? '1 Lark notification' : `${count} Lark notifications`);
        break;
      case 'todo_write':
        parts.push('Todo List');
        break;
    }
  }

  return parts.join(', ');
}
