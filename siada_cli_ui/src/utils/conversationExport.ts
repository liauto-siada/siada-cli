/**
 * /export writes the current TUI conversation layout to a plain-text file.
 */
import { writeFile } from 'node:fs/promises';
import { isAbsolute, join } from 'node:path';
import type { Message } from '../types/index.js';
import type { BannerProps } from '../components/Banner/Banner.js';
import {
  renderExportBanner, renderExportConversation, type ConversationRenderOptions,
} from './conversationRender.js';

const MAX_PROMPT_FILENAME_LENGTH = 50;

export type ExportBannerInfo = BannerProps;
export interface ExportResult {
  success: boolean;
  message: string;
}

function pad2(n: number): string {
  return String(n).padStart(2, '0');
}

function formatFileTimestamp(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}` +
    `-${pad2(date.getHours())}${pad2(date.getMinutes())}${pad2(date.getSeconds())}`;
}

export function extractFirstPrompt(messages: Message[]): string {
  const first = messages.find(message => message.type === 'user');
  let result = (first?.content || '').trim().split('\n')[0] || '';
  if (result.length > MAX_PROMPT_FILENAME_LENGTH) {
    result = result.substring(0, MAX_PROMPT_FILENAME_LENGTH - 1) + '…';
  }
  return result;
}

export function sanitizeFilename(text: string): string {
  return text.trim()
    .replace(/[\r\n]+/g, ' ')
    .replace(/[\\/:*?"<>|]/g, '')
    .replace(/[\s._]+/g, '-')
    .replace(/[^\p{L}\p{N}-]/gu, '')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, MAX_PROMPT_FILENAME_LENGTH);
}

export function buildDefaultExportFilename(messages: Message[], now: Date = new Date()): string {
  const timestamp = formatFileTimestamp(now);
  const sanitized = sanitizeFilename(extractFirstPrompt(messages));
  return sanitized ? `${timestamp}-${sanitized}.txt` : `conversation-${timestamp}.txt`;
}

export function renderBannerBlock(info: ExportBannerInfo, columns = 80): Promise<string> {
  return renderExportBanner(info, Math.max(1, Math.floor(columns || 80)));
}

export type RenderConversationOptions = ConversationRenderOptions;
export const renderConversationToText = renderExportConversation;

/** Keep the existing filename rules while sharing the live conversation renderer. */
export async function exportConversation(
  messages: Message[],
  workingDir: string,
  filenameArg: string,
  bannerInfo?: ExportBannerInfo,
  columns?: number,
  viewOptions: Omit<ConversationRenderOptions, 'bannerInfo' | 'columns'> = {},
): Promise<ExportResult> {
  const trimmed = filenameArg.trim();
  const withTxtExt = trimmed.replace(/\.[^./\\]+$/, '') + '.txt';
  const target = !trimmed ? join(workingDir, buildDefaultExportFilename(messages))
    : isAbsolute(withTxtExt) ? withTxtExt : join(workingDir, withTxtExt);
  try {
    const text = await renderConversationToText(messages, { ...viewOptions, bannerInfo, columns });
    await writeFile(target, text, 'utf-8');
    return { success: true, message: `Conversation exported to: ${target}` };
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return { success: false, message: `Failed to export conversation: ${reason}` };
  }
}