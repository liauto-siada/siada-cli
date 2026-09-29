/**
 * Conversation Export
 * Serializes the frontend message list to a plain-text transcript and writes
 * it to a .txt file. Follows the same content rules the chat view uses
 * (extractCleanContent for backend block messages, raw text for user input).
 *
 * Usage: /export [<filename>] — intercepted by the input prompt, never sent
 * to the backend.
 */

import { writeFileSync } from 'fs';
import { isAbsolute, join } from 'path';
import type { Message } from '../types/index.js';
import { extractCleanContent } from './contentCleaner.js';
import { BANNER_LINES } from '../constants/banner.js';

const DIVIDER = '─'.repeat(60);
const MAX_PROMPT_FILENAME_LENGTH = 50;

/** Banner header shown at the top of the export, mirroring the on-screen Banner. */
export interface ExportBannerInfo {
  version?: string;
  workingDir: string;
  agent?: string;
  provider?: string;
  model?: string;
  prePlanMode?: boolean;
  isCollapsed?: boolean;
}

export interface ExportResult {
  success: boolean;
  message: string;
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

/** Local timestamp used in the default filename, e.g. 2026-02-06-150432. */
function formatFileTimestamp(date: Date): string {
  return (
    `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}` +
    `-${pad2(date.getHours())}${pad2(date.getMinutes())}${pad2(date.getSeconds())}`
  );
}

/** Readable local timestamp for the export meta line, e.g. 2026-02-06 15:04:32. */
function formatReadableTimestamp(date: Date): string {
  return (
    `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}` +
    ` ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
  );
}

/** HH:MM:SS for the per-message header line. */
function formatClockTime(timestamp: string): string {
  const d = new Date(timestamp);
  if (Number.isNaN(d.getTime())) return '';
  return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
}

/**
 * First user prompt, first line only, capped — used for the default filename.
 * Mirrors claude-code /export but keeps unicode letters (CJK prompts stay
 * readable instead of being stripped to an empty string).
 */
export function extractFirstPrompt(messages: Message[]): string {
  const firstUserMessage = messages.find(msg => msg.type === 'user');
  if (!firstUserMessage) return '';

  let result = (firstUserMessage.content || '').trim().split('\n')[0] || '';
  if (result.length > MAX_PROMPT_FILENAME_LENGTH) {
    result = result.substring(0, MAX_PROMPT_FILENAME_LENGTH - 1) + '…';
  }
  return result;
}

export function sanitizeFilename(text: string): string {
  return (
    text
      .trim()
      .replace(/[\r\n]+/g, ' ')
      // Path-hostile characters
      .replace(/[\\/:*?"<>|]/g, '')
      // Whitespace runs and separators collapse to a single hyphen
      .replace(/[\s._]+/g, '-')
      // Keep unicode letters/digits and hyphens only
      .replace(/[^\p{L}\p{N}-]/gu, '')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
      .slice(0, MAX_PROMPT_FILENAME_LENGTH)
  );
}

/** Default filename: {timestamp}-{sanitized-first-prompt}.txt */
export function buildDefaultExportFilename(messages: Message[], now: Date = new Date()): string {
  const timestamp = formatFileTimestamp(now);
  const sanitized = sanitizeFilename(extractFirstPrompt(messages));
  return sanitized ? `${timestamp}-${sanitized}.txt` : `conversation-${timestamp}.txt`;
}

function charDisplayWidth(ch: string): number {
  return ch.codePointAt(0)! > 0x2E7F ? 2 : 1;
}

function textDisplayWidth(text: string): number {
  let width = 0;
  for (const ch of text) width += charDisplayWidth(ch);
  return width;
}

/**
 * Reproduces the on-screen Banner (the first thing the user sees above the
 * conversation) as plain text: bordered box, ASCII art, working directory,
 * agent/provider/model line and the cost disclaimer. Layout mirrors
 * components/Banner/Banner.tsx at a standard 80-column terminal.
 */
export function renderBannerBlock(info: ExportBannerInfo, columns = 80): string {
  const contentWidth = Math.max(0, columns - 2);
  const bordered = (content: string, padByDisplayWidth = false) => {
    const used = padByDisplayWidth ? textDisplayWidth(content) : [...content].length;
    return `│${content}${' '.repeat(Math.max(0, contentWidth - used))}│`;
  };
  const blank = () => bordered(' '.repeat(contentWidth));

  const title = info.version ? `Siada CLI v${info.version}` : 'Siada CLI';
  const titleSegment = `─ ${title} `;
  const topMiddle =
    contentWidth > 0
      ? titleSegment.length >= contentWidth
        ? titleSegment.slice(0, contentWidth)
        : titleSegment + '─'.repeat(contentWidth - titleSegment.length)
      : '';
  const lines: string[] = [`╭${topMiddle}╮`, blank()];

  for (const art of BANNER_LINES) {
    const chars = [...art];
    const visible = chars.slice(0, contentWidth).join('');
    lines.push(bordered(visible + ' '.repeat(Math.max(0, contentWidth - chars.length))));
  }
  lines.push(blank());

  // Working Directory (truncated to the box width like the on-screen Banner)
  const wdLabel = 'Working Directory: ';
  const maxPathLen =
    wdLabel.length + info.workingDir.length > contentWidth
      ? Math.max(0, contentWidth - wdLabel.length)
      : info.workingDir.length;
  lines.push(bordered(wdLabel + info.workingDir.slice(0, maxPathLen)));

  // Agent / Provider / Model info, same segment order as Banner.tsx
  const segments = [
    `Agent: ${info.agent ?? 'coder'}`,
    `, Provider: ${info.provider ?? 'default'}`,
    `, Model: ${info.model || 'default'}`,
  ];
  if (info.prePlanMode !== false) segments.push('; pre-plan mode');
  segments.push(`; ${info.isCollapsed ? 'compact mode' : 'expanded mode'} (ctrl+o)`);
  const infoLine = [...segments.join('')].slice(0, contentWidth).join('');
  lines.push(bordered(infoLine));

  lines.push(blank());
  lines.push(`╰${'─'.repeat(contentWidth)}╯`);
  return lines.join('\n');
}

function sectionLabel(message: Message): string {
  // The adapter emits more subtypes than AgentMessageSubtype declares
  // (shell / error_box / goal_result / ...); compare as string like Message.tsx.
  const subtype = message.metadata?.subtype as string | undefined;
  if (message.type === 'user') return 'User';
  if (message.type === 'error' || subtype === 'error_box') return 'Error';
  if (subtype === 'thinking') return 'Thinking';
  if (subtype === 'tool_use') return 'Tool Use';
  if (subtype === 'shell') return 'Shell';
  if (subtype === 'goal_result') return 'Goal';
  if (message.type === 'system') return 'System';
  // answer / slash_command_result / plain agent blocks
  return 'Siada';
}

/** Shell messages carry structured output in metadata.shellExecution. */
function renderShellContent(message: Message): string {
  const exec = message.metadata?.shellExecution as
    | {
        command?: string;
        executing?: boolean;
        stdout?: string;
        stderr?: string;
        exitCode?: number | null;
        duration?: number;
      }
    | undefined;
  if (!exec?.command) return extractCleanContent(message.content || '');

  const parts: string[] = [`$ ${exec.command}`];
  if (!exec.executing) {
    if (exec.exitCode !== undefined && exec.exitCode !== null) {
      parts.push(`exit code: ${exec.exitCode}`);
    }
    for (const [label, output] of [['stdout', exec.stdout], ['stderr', exec.stderr]] as const) {
      const text = (output || '').trim();
      if (text) parts.push(`[${label}]\n${text}`);
    }
  }
  return parts.join('\n');
}

function renderMessageContent(message: Message): string {
  const subtype = message.metadata?.subtype as string | undefined;
  if (subtype === 'shell') {
    return renderShellContent(message);
  }
  if (message.type === 'user') {
    // User input is raw text (possibly markdown); the chat view shows it as-is.
    return (message.content || '').trim();
  }
  return extractCleanContent(message.content || '').trim();
}

/**
 * Serializes the conversation to plain text. When bannerInfo is given the
 * export opens with the same banner the user sees on screen (rendered at the
 * caller's terminal width). Empty stream-end placeholders are skipped with
 * the same rule MessageList uses for rendering.
 */
export interface RenderConversationOptions {
  bannerInfo?: ExportBannerInfo;
  exportedAt?: Date;
  /** Terminal width used to lay out the banner block (default 80). */
  columns?: number;
}

export function renderConversationToText(
  messages: Message[],
  options: RenderConversationOptions = {},
): string {
  const { bannerInfo, exportedAt = new Date(), columns = 80 } = options;
  const parts: string[] = [];
  if (bannerInfo) {
    parts.push(renderBannerBlock(bannerInfo, columns));
  }
  parts.push(
    `Siada CLI Conversation Export\nExported: ${formatReadableTimestamp(exportedAt)} · Messages: ${messages.length}`,
  );

  for (const message of messages) {
    const isStreamEnd = message.metadata?.isStreaming === false && message.metadata?.streamEnd === true;
    const content = renderMessageContent(message);
    if (isStreamEnd && !content) continue;
    if (!content) continue;

    const time = formatClockTime(message.timestamp);
    const header = time ? `${sectionLabel(message)} · ${time}` : sectionLabel(message);
    parts.push(`${DIVIDER}\n${header}\n\n${content}`);
  }

  return parts.join('\n\n') + '\n';
}

/**
 * Writes the conversation to a .txt file.
 * - no filename: default name in workingDir
 * - filename: relative to workingDir (or absolute path); extension forced to .txt
 * - bannerInfo: renders the on-screen banner at the top of the export
 * - columns: terminal width for banner layout (defaults to 80)
 */
export function exportConversation(
  messages: Message[],
  workingDir: string,
  filenameArg: string,
  bannerInfo?: ExportBannerInfo,
  columns?: number,
): ExportResult {
  const trimmed = filenameArg.trim();
  let target: string;
  if (!trimmed) {
    target = join(workingDir, buildDefaultExportFilename(messages));
  } else {
    const withTxtExt = trimmed.replace(/\.[^./\\]+$/, '') + '.txt';
    target = isAbsolute(withTxtExt) ? withTxtExt : join(workingDir, withTxtExt);
  }

  try {
    const text = renderConversationToText(messages, { bannerInfo, columns });
    writeFileSync(target, text, 'utf-8');
    return { success: true, message: `Conversation exported to: ${target}` };
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return { success: false, message: `Failed to export conversation: ${reason}` };
  }
}
