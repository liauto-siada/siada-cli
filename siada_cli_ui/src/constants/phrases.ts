/**
 * Thinking and Loading Phrases
 * Collection of phrases to display during model thinking
 */

import { bilingual } from '../i18n/index.js';

export const THINKING_PHRASES = bilingual([
  '正在思考…',
  '正在分析你的请求…',
  '正在处理信息…',
], ['Thinking...', 'Analyzing your request...', 'Processing information...']);

export const WITTY_PHRASES = bilingual([
  '正在思考…',
], ['Thinking...']);

export { INFORMATIVE_TIPS, SHORTCUT_TIPS, TIP_CHANGE_INTERVAL } from './tips.js';

export const STATUS_PHRASES = bilingual({
  INITIALIZING: '正在初始化智能体…',
  CONNECTING: '正在连接 siada-cli…',
  CONFIRMING: '正在思考…',
  THINKING: '正在思考…',
  PROCESSING: '正在思考…',
}, {
  INITIALIZING: 'Initializing Agent...',
  CONNECTING: 'Connecting to siada-cli...',
  CONFIRMING: 'Thinking...',
  THINKING: 'Thinking...',
  PROCESSING: 'Thinking...',
});

// Phrase rotation interval (milliseconds)
export const PHRASE_CHANGE_INTERVAL = 15000; // 15 seconds

/**
 * Thinking Steps
 * Step descriptions for the phases an agent turn goes through while the
 * "thinking" indicator is visible. Derived from the incoming ACP message
 * stream so the UI can tell the user WHAT the agent is currently doing.
 */
export type ThinkingStep = 'reasoning' | 'tool_execution' | 'system_processing' | 'compaction';

export interface ThinkingStepInfo {
  /** Short label shown next to thinking content summaries */
  label: string;
  /** Live phrase shown in the thinking indicator while the step is active */
  phrase: string;
}

export const THINKING_STEPS: Record<ThinkingStep, ThinkingStepInfo> = bilingual({
  reasoning: { label: '模型推理', phrase: '正在推理…' },
  tool_execution: { label: '执行工具', phrase: '正在执行工具…' },
  system_processing: { label: '系统处理', phrase: '系统正在处理…' },
  compaction: { label: '压缩上下文', phrase: '正在压缩上下文…' },
}, {
  reasoning: { label: 'Model Reasoning', phrase: 'Model reasoning...' },
  tool_execution: { label: 'Tool Execution', phrase: 'Executing tools...' },
  system_processing: { label: 'System Processing', phrase: 'System processing...' },
  compaction: { label: 'Context Compaction', phrase: 'Compacting context...' },
});

/**
 * Match the backend's compaction start notice, rather than arbitrary content
 * that happens to mention compression.
 */
export const COMPACTION_CONTENT_PATTERN = /^Compacting context\.\.\.$/;

/** Terminal compaction notices let the indicator resume before the next token. */
export const COMPACTION_COMPLETE_PATTERN = /^(?:Compacted:\s*\d+\s*→\s*\d+\s+messages\s*\(-?\d+\s+removed\)|Nothing to compact \(conversation too short or already compact\)\.|No conversation history to compact\.|Compaction failed:[\s\S]*|Compaction interrupted\.)$/;
