import React, { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Box, Text, getBoundingBox, getVerticalScrollbarBoundingBox, measureElement, ResizeObserver, useApp, useStdout, type DOMElement } from '@jrichman/ink';
import stringWidth from '../../utils/terminalWidth.js';
import { useKeypress, type Key } from '../../hooks/useKeypress.js';
import { isMermaidControlAt } from '../../utils/mermaidControls.js';
import { useMouseTracking } from '../../hooks/useMouseTracking.js';
import type { CtrlCContext } from '../../hooks/useQuitShortcut.js';
import type { Message as ChatMessage } from '../../types/index.js';
import { Message } from './Message.js';
import { CommandView, parseCommandContent } from './CommandView.js';
import { colors } from '../../utils/colors.js';
import { goalResultSummary } from '../../utils/goalDisplay.js';
import { HISTORY_TIPS } from '../../constants/tips.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { SpotlightThinking } from '../common/SpotlightThinking.js';
import { DisclosureArrow } from '../common/DisclosureArrow.js';
import { getActiveTheme, useThemeVersion } from '../../themes/index.js';
import { formatCompactSummary, groupToolCalls, isTodoWriteAllCompleted, parseToolCall, type ParsedToolCall } from '../../utils/toolCallParser.js';
import { getQueryToolArgument, getQueryToolHeading, getSemanticToolCallDisplay } from '../../utils/toolCallDisplay.js';
import { isErrorMessage } from '../../utils/errorMessage.js';
import { isHookMessage } from '../../utils/hookMessage.js';
import { getSimplePatch, parseApplyPatchContent, parseFileEditContent, parseFileEditPresentation } from '../../utils/diff.js';
import { fileChangeSummary } from '../diff/FileChangeSetView.js';
import { Banner, type BannerProps } from '../Banner/Banner.js';
import { ToolAction, ToolHeading } from './ToolHeading.js';
import { ToolPromptView } from './ToolPromptView.js';
import { copySelectionToClipboard } from '../../utils/clipboard.js';
import { splitMarkdownFragments, type MarkdownCodeFence } from '../../utils/markdownUtilities.js';
import {
  ConversationSelectionLayout, ConversationTextSelection, createSelectionFrame, SELECTION_FRAME_MS,
  type SelectionUnit,
  type SelectionSurface,
} from '../../utils/conversationSelection.js';

interface ConversationViewportProps {
  inputTip?: string | null;
  externalHoverTip?: string | null;
  footerOffset?: number;
  keepMouseTracking?: boolean;
  /** Exclusive screen row where a bottom overlay covers the history. */
  mouseScrollBottom?: number;
  activityLabel?: string;
  presentation?: boolean;
  bannerProps?: BannerProps;
  collapsedStateRef?: React.MutableRefObject<ReadonlyMap<string, boolean>>;
  messages: ChatMessage[];
  width: number;
  height: number;
  isCollapsed: boolean;
  active?: boolean;
  /** Allow mouse reading while the composer owns keyboard input. */
  mouseActive?: boolean;
  mouseOverlayRef?: React.RefObject<DOMElement | null>;
  composerActive?: boolean;
  onDirectoryChange?: (open: boolean) => void;
  onCtrlC?: (context?: CtrlCContext) => void;
  interruptNotice?: string | null;
  composerSelection?: React.RefObject<SelectionSurface>;
}

interface ContentBlock {
  id: string;
  message: ChatMessage;
  turn: number;
  continuation: boolean;
  initialCodeFence?: MarkdownCodeFence;
  gapAfter?: number;
  toolTree?: { first: boolean; last: boolean; summary: string; preview: string };
}

function ActivityIndicator({ label, hidden }: { label?: string; hidden: boolean }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  useEffect(() => {
    if (!label) {
      setElapsedSeconds(0);
      return;
    }
    const startedAt = Date.now();
    const tick = () => setElapsedSeconds(Math.floor((Date.now() - startedAt) / 1000));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [Boolean(label)]);

  if (!label || hidden) return null;
  const minutes = Math.floor(elapsedSeconds / 60);
  const seconds = elapsedSeconds % 60;
  const elapsed = minutes ? `${minutes}m ${seconds}s` : `${seconds}s`;
  return <Box flexShrink={0} marginRight={1}>
    <SpotlightThinking text={label} ring />
    {elapsedSeconds > 0 && <Text color="gray"> ({elapsed})</Text>}
  </Box>;
}

// Bound prose render work and mounted nodes while keeping fenced code whole.
// Original messages stay in the session store; these are presentation fragments.
const fragmentCache = new WeakMap<ChatMessage, ContentBlock[]>();
const patchFragmentCache = new WeakMap<ChatMessage, ContentBlock[]>();
export function conversationBlocks(messages: ChatMessage[], presentation = false): ContentBlock[] {
  const blocks: ContentBlock[] = [];
  let turn = 0;
  for (const message of messages) {
    if (message.type === 'user') turn++;
    if (isHookMessage(message)) {
      if (message.content?.trim()) blocks.push({
        id: message.id, turn, continuation: false, gapAfter: 1,
        message: message.metadata?.subtype === 'hook' ? message : {
          ...message, metadata: { ...message.metadata, subtype: 'hook' },
        },
      });
      continue;
    }
    if (isErrorMessage(message)) {
      if (message.content?.trim()) blocks.push({
        id: message.id, turn, continuation: false, gapAfter: 1,
        message: message.metadata?.subtype === 'error' ? message : {
          ...message, metadata: { ...message.metadata, subtype: 'error' },
        },
      });
      continue;
    }
    if (presentation && message.metadata?.subtype === 'tool_use') {
      const content = message.content.replace(/^[▶►]\s*TOOL\s*USE\s*/i, '').trim();
      const isTodoSnapshot = content === 'Clearing todo list' || /\[\d+\/\d+ completed\]\s*$/.test(content);
      if (isTodoSnapshot && parseToolCall(content)?.type === 'todo_write' &&
          !isTodoWriteAllCompleted(content)) continue;
    }
    const structured = message.metadata?.subtype === 'goal_result' && message.metadata.goalResult ||
      message.metadata?.subtype === 'shell' && message.metadata.shellExecution;
    if (!message.content?.trim() && !structured) continue;
    if (presentation && message.metadata?.subtype === 'tool_use' &&
        message.content.includes('<!-- siada-apply-patch:start -->')) {
      const patch = parseApplyPatchContent(message.content);
      if (patch && patch.changes.length > 1) {
        let fragments = patchFragmentCache.get(message);
        if (!fragments || fragments[0]?.turn !== turn) {
          const body = message.content.split('<!-- siada-apply-patch:start -->')[1]
            .split('<!-- siada-apply-patch:end -->')[0].trim();
          const sections = body.split(/(?=^### )/m).filter(section => section.trim());
          fragments = sections.map((section, index) => {
            const id = `${message.id}:file:${index}`;
            return { id, turn, continuation: false, gapAfter: 1, message: {
              ...message, id,
              content: `Apply patch: 1 file changed\n<!-- siada-apply-patch:start -->\n${section.trim()}\n<!-- siada-apply-patch:end -->`,
            } };
          });
          patchFragmentCache.set(message, fragments);
        }
        blocks.push(...fragments);
        continue;
      }
    }
    const cached = fragmentCache.get(message);
    if (cached && cached[0]?.turn === turn) {
      blocks.push(...cached);
      continue;
    }
    const first = blocks.length;
    const collapsible = message.metadata?.subtype === 'thinking' || message.metadata?.subtype === 'tool_use';
    if (collapsible || !message.content?.trim()) {
      blocks.push({ id: message.id, message, turn, continuation: false, gapAfter: 1 });
      fragmentCache.set(message, blocks.slice(first));
      continue;
    }
    let offset = 0;
    for (const content of splitMarkdownFragments(message.content)) {
      const end = offset + content.length;
      blocks.push({
        id: `${message.id}:${offset}`,
        message: offset === 0 && end === message.content.length
          ? message : { ...message, content },
        turn, continuation: offset > 0 || Boolean(message.metadata?.nativeHistoryContinuation),
        gapAfter: end < message.content.length ? 0 : 1,
      });
      offset = end;
    }
    fragmentCache.set(message, blocks.slice(first));
  }
  return toolTreeBlocks(blocks, presentation);
}

function parsedTool(message: ChatMessage, presentation = false): ParsedToolCall | null {
  const patch = presentation ? parseApplyPatchContent(message.content) : null;
  if (patch?.changes.length === 1 && patch.changes[0].action === 'update') return {
    type: 'update_file', summary: 'Update file', path: patch.changes[0].path,
  };
  const edit = parseFileEditPresentation(message.content);
  if (edit) return {
    type: edit.action === 'create' ? 'create_file' : edit.action === 'undo' ? 'undo_edit' : 'update_file',
    summary: edit.action === 'create' ? 'Create file' : edit.action === 'undo' ? 'Undo edit' : 'Edit file',
    path: edit.path,
  };
  return parseToolCall(message.content.replace(/^[▶►]\s*TOOL\s*USE\s*/i, '').trim());
}

function fileToolSummary(message: ChatMessage): string | null {
  const patch = parseApplyPatchContent(message.content);
  if (patch) return fileChangeSummary(patch.changes, patch.fileCount);
  const edit = parseFileEditPresentation(message.content);
  if (edit?.status === 'completed' && edit.hunks.length) {
    return fileChangeSummary([{ action: edit.action === 'create' ? 'create' : 'update',
      path: edit.path, hunks: edit.hunks }], 1);
  }
  if (message.metadata?.streamEnd !== true) return null;
  const legacyEdit = parseFileEditContent(message.content);
  if (legacyEdit?.isComplete) {
    return fileChangeSummary([{ action: 'update', path: legacyEdit.filePath,
      hunks: getSimplePatch(legacyEdit.filePath, legacyEdit.oldString, legacyEdit.newString) }], 1);
  }
  return null;
}

function toolTreeBlocks(blocks: ContentBlock[], presentation = false): ContentBlock[] {
  const result = [...blocks];
  for (let start = 0; start < blocks.length;) {
    if (blocks[start].message.metadata?.subtype !== 'tool_use') { start++; continue; }
    if (isTodoWriteAllCompleted(blocks[start].message.content) &&
        parsedTool(blocks[start].message)?.type === 'todo_write') { start++; continue; }
    let end = start + 1;
    while (end < blocks.length && blocks[end].message.metadata?.subtype === 'tool_use' &&
      !(isTodoWriteAllCompleted(blocks[end].message.content) &&
        parsedTool(blocks[end].message)?.type === 'todo_write')) end++;
    if (end - start > 1) {
      const tools = blocks.slice(start, end).map(block => parsedTool(block.message, presentation));
      const summary = formatCompactSummary(groupToolCalls(tools.filter((tool): tool is ParsedToolCall => tool !== null))) ||
        `${end - start} tool calls`;
      for (let index = start; index < end; index++) {
        const tool = tools[index - start];
        const semantic = tool ? getSemanticToolCallDisplay(tool) : null;
        const filename = tool?.path?.split(/[\\/]/).at(-1);
        const range = tool?.type === 'read_file' && tool.lineStart !== undefined && tool.lineEnd !== undefined
          ? `:${tool.lineStart}-${tool.lineEnd}` : '';
        const command = tool?.type === 'run_command' || tool?.type === 'run_powershell'
          ? parseCommandContent(blocks[index].message.content.replace(/^[▶►]\s*TOOL\s*USE\s*/i, '').trim()).body : undefined;
        const preview = (presentation ? fileToolSummary(blocks[index].message) : null) ||
          semantic?.compactPreview || (tool ? getQueryToolArgument(tool, blocks[index].message.content) : null) ||
          (filename ? `${filename}${range}` : command || tool?.details) ||
          tool?.summary || blocks[index].message.content.split('\n')[0];
        result[index] = { ...blocks[index], gapAfter: index === end - 1 ? 1 : 0, toolTree: {
          first: index === start, last: index === end - 1, summary, preview: preview.replace(/\s+/g, ' '),
        } };
      }
    }
    start = end;
  }
  return result;
}

function thinkingText(content: string): string {
  return content.replace(/^[\s▶►]*\*{0,2}THINKING\*{0,2}:?\s*/i, '').trim();
}

function hoverColor(soft = false): string {
  return getActiveTheme() === 'dark' ? soft ? '#d0d7df' : colors.white : soft ? '#39424e' : colors.gray[900];
}

const commandSegmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
function clipCommandLabel(label: string, maxWidth: number): string {
  if (stringWidth(label) <= maxWidth) return label;
  let clipped = '';
  for (const { segment } of commandSegmenter.segment(label.replaceAll('\t', '    '))) {
    if (stringWidth(clipped) + stringWidth(segment) >= maxWidth) break;
    clipped += segment;
  }
  return `${clipped}…`;
}

export function estimateBlockRows(block: ContentBlock, width: number, collapsed: boolean): number {
  const treeHeader = block.toolTree?.first ? 1 : 0;
  const gap = block.gapAfter ?? 1;
  const subtype = block.message.metadata?.subtype;
  if (subtype === 'error' || subtype === 'hook') {
    return 1 + gap + block.message.content.split('\n').reduce(
      (rows, line) => rows + Math.max(1, Math.ceil(stringWidth(line) / Math.max(1, width - 2))), 0,
    );
  }
  if (subtype === 'tool_use') {
    if (collapsed) return 1 + treeHeader + gap;
    const edit = parseFileEditPresentation(block.message.content);
    if (edit?.hunks.length) return treeHeader + gap + 2 + edit.hunks.reduce(
      (rows, hunk) => rows + hunk.lines.reduce(
        (count, line) => count + Math.max(1, Math.ceil(stringWidth(line) / Math.max(1, width - 10))), 0,
      ), 0,
    );
    return treeHeader + gap + 1 + block.message.content.split('\n').reduce(
      (rows, line) => rows + Math.max(1, Math.ceil(stringWidth(line) / Math.max(1, width - 4))), 0,
    );
  }
  if (subtype === 'thinking') {
    if (collapsed) return 1 + gap;
    return gap + thinkingText(block.message.content).split('\n').reduce(
      (rows, line) => rows + Math.max(1, Math.ceil(stringWidth(line) / Math.max(1, width - 6))), 0,
    );
  }
  return Math.max(1, block.message.content.split('\n').reduce(
    (rows, line) => rows + Math.max(1, Math.ceil(stringWidth(line) / Math.max(8, width - 4))), 0,
  )) + gap;
}

interface MousePoint { x: number; y: number }

function mousePosition(key: Key): MousePoint | null {
  const match = /^\x1b\[<\d+;(\d+);(\d+)M$/.exec(key.sequence);
  return match ? { x: Number(match[1]) - 1, y: Number(match[2]) - 1 } : null;
}

function containsPoint(node: DOMElement | null, point: MousePoint): boolean {
  if (!node) return false;
  const bounds = getBoundingBox(node);
  return point.x >= bounds.x && point.x < bounds.x + bounds.width &&
    point.y >= bounds.y && point.y < bounds.y + bounds.height;
}

export const ConversationBlock = React.memo(function ConversationBlock({
  block, width, collapsed, onMeasure, onHeadingRef, onBlockRef, hovered, presentation,
}: {
  block: ContentBlock; width: number; collapsed: boolean;
  onMeasure: (id: string, height: number) => void;
  onHeadingRef: (id: string, node: DOMElement | null) => void;
  onBlockRef: (id: string, node: DOMElement | null) => void;
  hovered: boolean;
  presentation?: boolean;
}) {
  useUiLanguage();
  const ref = useRef<DOMElement>(null);
  const blockRef = useCallback((node: DOMElement | null) => {
    ref.current = node;
    onBlockRef(block.id, node);
  }, [block.id, onBlockRef]);
  const summaryRef = useCallback((node: DOMElement | null) => onHeadingRef(block.id, node), [block.id, onHeadingRef]);
  const subtype = block.message.metadata?.subtype;
  const isThinking = subtype === 'thinking';
  const isGoalResult = presentation && subtype === 'goal_result';
  const goalResult = block.message.metadata?.goalResult;
  const collapsible = isThinking || subtype === 'tool_use' || isGoalResult;
  const gapAfter = block.gapAfter ?? 1;
  useLayoutEffect(() => {
    if (ref.current) onMeasure(block.id, Math.max(1, Math.ceil(measureElement(ref.current).height)) + gapAfter);
  });
  useLayoutEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(entries => {
      onMeasure(block.id, Math.max(1, Math.ceil(entries[0].contentRect.height)) + gapAfter);
    });
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [block.id, gapAfter, onMeasure]);
  const clean = thinkingText(block.message.content);
  const thinkingBackground = getActiveTheme() === 'light' ? '#e9edf2' : '#333333';
  const parsed = !isThinking && collapsible ? parsedTool(block.message, presentation) : null;
  const isCompletedPlan = presentation && parsed?.type === 'todo_write' && isTodoWriteAllCompleted(block.message.content);
  const semantic = parsed ? getSemanticToolCallDisplay(parsed) : null;
  const fileEdit = parsed ? parseFileEditPresentation(block.message.content) : null;
  const longSemanticContent = Boolean(semantic?.fields.length && parsed?.details &&
    (parsed.details.includes('\n') || stringWidth(parsed.details) > Math.min(72, width - 8)));
  const isCommand = parsed?.type === 'run_command' || parsed?.type === 'run_powershell';
  const command = isCommand
    ? parseCommandContent(block.message.content.replace(/^[▶►]\s*TOOL\s*USE\s*/i, '').trim()) : null;
  const commandBody = block.message.content.match(/```[^\r\n]*\r?\n([\s\S]*?)\r?\n```/)?.[1]?.trim() ??
    command?.body.trim();
  const commandPrefix = block.toolTree ? (block.toolTree.last ? '└─ ' : '├─ ') : '● Run ';
  const commandIndent = block.toolTree ? 2 : 0;
  const commandOverflows = Boolean(commandBody) &&
    (commandBody!.includes('\n') || stringWidth(commandBody!) +
      stringWidth(commandPrefix) >
      width - commandIndent - 1);
  const inlineCommand = presentation && isCommand && Boolean(commandBody) &&
    !commandOverflows;
  const needsDisclosure = !presentation || isThinking || isGoalResult || isCompletedPlan ||
    parsed?.type === 'update_file' || parsed?.type === 'apply_patch' ||
    Boolean(fileEdit) || parsed?.type === 'create_file' || longSemanticContent ||
    parsed?.type === 'search' && Boolean(parsed.cwd) ||
    isCommand && commandOverflows;
  // A single-line notice has no tool details beyond its heading.
  const singleLineNotice = presentation && subtype === 'tool_use' && !parsed &&
    !block.message.content.trim().includes('\n');
  const directlyShown = presentation && subtype === 'tool_use' &&
    (!needsDisclosure || parsed?.type === 'search') && !singleLineNotice;
  const directSearch = parsed?.type === 'search' && Boolean(parsed.path) && (!collapsed || directlyShown);
  const directRead = directlyShown && parsed?.type === 'read_file';
  const directFile = directlyShown && Boolean(parsed?.path) &&
    ['read_file', 'analyze', 'view_dir', 'create_file', 'undo_edit'].includes(parsed!.type);
  const queryAction = parsed ? getQueryToolHeading(parsed, block.message.content) : null;
  const queryHeading = !collapsed || directlyShown ? queryAction : null;
  const queryPreview = parsed && queryAction
    ? parsed.type === 'search'
      ? `Search "${(parsed.query || '').replaceAll('"', '\\"')}" in ${parsed.path}`
      : [queryAction, getQueryToolArgument(parsed, block.message.content)].filter(Boolean).join(' ')
    : null;
  const readRange = directRead && parsed.lineStart !== undefined
    ? ` · Lines ${parsed.lineStart}${parsed.lineEnd !== undefined ? `–${parsed.lineEnd}` : ''}` : '';
  const firstThought = clean.split('\n')[0];
  const firstThoughtSummary = firstThought.trimEnd().replace(/\s*(?:\.{3}|…)$/u, '…');
  const semanticHeading = semantic && !fileEdit && (!collapsed || directlyShown) && semantic.fields.length
    ? semantic.heading : null;
  const thoughtPreview = clipCommandLabel(
    `${firstThoughtSummary}${clean.length > firstThought.length && !firstThoughtSummary.endsWith('…') ? '…' : ''}`,
    Math.max(1, Math.min(60, width - 5)),
  );
  const planCounts = block.message.content.match(/\[(\d+)\/(\d+) completed\]/);
  const headline = isCompletedPlan ? `Plan completed (${planCounts?.[1]}/${planCounts?.[2]})` : isGoalResult
    ? goalResult ? goalResultSummary(goalResult, Math.max(1, width - 4)) : 'Goal verification'
    : isThinking
    ? thoughtPreview
    : (presentation ? fileToolSummary(block.message) : null) ||
      (command ? command.body.split('\n').find(line => line.trim())?.trim() || clean.split('\n')[0]
      : semanticHeading || semantic?.compactSummary ||
        queryPreview || [parsed?.summary, parsed?.path].filter(Boolean).join(' ') || clean.split('\n')[0]);
  const commandLabel = `${commandPrefix}${block.toolTree?.preview || headline}`;
  const commandWidth = width - commandIndent - 1;
  const disclosureLabel = needsDisclosure ? ` ${collapsed ? '›' : '⌄'}` : '';
  const disclosureGlyph = collapsed ? '›' : '⌄';
  const toolLabel = (queryHeading || semanticHeading || block.toolTree?.preview || headline).replace(/\s*(?:\.{3}|…)$/u, '…');
  const visibleToolLabel = clipCommandLabel(toolLabel, Math.max(1,
    width - (block.toolTree ? 6 : 3) - stringWidth(disclosureLabel) - stringWidth(readRange)));
  const commandText = clipCommandLabel(commandLabel, commandWidth - stringWidth(disclosureLabel));
  // Expanded commands show their first line once: the heading row replaces the
  // preview and the body continues from the second line, like thinking blocks.
  const expandedCommand = !collapsed && isCommand && Boolean(commandBody);
  const commandFirstLine = commandBody?.split('\n')[0] ?? '';
  const commandRemaining = commandBody?.includes('\n')
    ? commandBody!.slice(commandBody!.indexOf('\n') + 1) : '';
  const completionAction = isCompletedPlan ? 'Plan completed'
    : isGoalResult && goalResult?.achieved ? 'Goal Achieved' : null;
  return (
    <Box ref={blockRef} flexDirection="column" flexShrink={0} marginBottom={gapAfter}>
      {isThinking && !collapsed ? <Box flexDirection="column">
        {/* The opening line replaces its preview and remains the disclosure target. */}
        <Box ref={summaryRef}>
          <Box userSelect="none" width={2} flexShrink={0}>
            <Text color={colors.content.secondary}>{presentation ? '● ' : <><DisclosureArrow glyph="›" hovered={hovered} />{' '}</>}</Text>
          </Box>
          <Box width={Math.max(2, width - 6)} backgroundColor={thinkingBackground}>
            <Text backgroundColor={thinkingBackground}
              color={hovered ? hoverColor(presentation) : colors.content.secondary} bold={hovered}>
              {firstThought}
            </Text>
          </Box>
          <Box userSelect="none" flexShrink={0}>
            <Text color={colors.content.secondary}>{' '}<DisclosureArrow glyph="⌄" hovered={hovered} /></Text>
          </Box>
        </Box>
        {clean.includes('\n') && <Box paddingLeft={2}>
          <Box width={Math.max(2, width - 6)} backgroundColor={thinkingBackground}>
            <Text backgroundColor={thinkingBackground} color={colors.content.secondary}>
              {clean.slice(firstThought.length + 1)}
            </Text>
          </Box>
        </Box>}
      </Box> : directSearch ? <Box flexDirection="column">
        {block.toolTree?.first && <ToolHeading parts={block.toolTree.summary.split(', ')} wrap="truncate-end" />}
        <Box paddingLeft={block.toolTree ? 2 : 0}>
          <ToolPromptView tool={parsed!} content={block.message.content}
            width={width - (block.toolTree ? 2 : 0)} searchPresentation={{
              prefix: block.toolTree ? block.toolTree.last ? '└─ ' : '├─ ' : '● ',
              headingRef: needsDisclosure ? summaryRef : undefined,
              backgroundColor: hovered && needsDisclosure ? colors.content.surface : undefined,
              disclosure: needsDisclosure ? ` ${collapsed ? '›' : '⌄'}` : '',
              disclosureHovered: hovered && needsDisclosure,
              showCwd: !collapsed,
              secondary: Boolean(block.toolTree),
            }} />
        </Box>
      </Box> : inlineCommand ? <Box flexDirection="column">
        {block.toolTree?.first && <ToolHeading parts={block.toolTree.summary.split(', ')} wrap="truncate-end" />}
        <Box width={width} paddingLeft={block.toolTree ? 2 : 0} paddingRight={1} height={1} overflowX="hidden">
          <Box flexShrink={1} overflowX="hidden">
            <Text color={colors.content.secondary} wrap="truncate-end">
              {block.toolTree ? <>{commandPrefix}{commandBody}</> : <>
                <Text color={colors.info}>●</Text>{' '}
                <ToolAction label={`Run ${commandBody}`} />
              </>}
            </Text>
          </Box>
        </Box>
      </Box> : collapsible ? <>
        {block.toolTree?.first && <Box height={1} flexShrink={0} overflowX="hidden">
          <ToolHeading parts={block.toolTree.summary.split(', ')} wrap="truncate-end" />
        </Box>}
        {expandedCommand ? <>
          {/* The command's first line replaces its preview and remains the disclosure target. */}
          <Box ref={summaryRef} paddingLeft={block.toolTree ? 2 : 0}>
            <Box userSelect="none" flexShrink={0}>
              {block.toolTree
                ? <Text color={colors.content.secondary}>{block.toolTree.last ? '└─ ' : '├─ '}</Text>
                : <Text color={colors.info}>● </Text>}
            </Box>
            <Box width={Math.max(2, width - (block.toolTree ? 8 : 5))}>
              <Text wrap="wrap">
                {block.toolTree
                  ? <Text color={hovered ? hoverColor(presentation) : colors.content.secondary}>{commandFirstLine}</Text>
                  : <ToolAction label={`Run ${commandFirstLine}`} />}
              </Text>
            </Box>
            <Box userSelect="none" flexShrink={0}>
              <Text color={colors.content.secondary}>{' '}<DisclosureArrow glyph="⌄" hovered={hovered} /></Text>
            </Box>
          </Box>
          {commandRemaining && <Box paddingLeft={block.toolTree ? 2 : 0}>
            <CommandView content={commandRemaining} indentation={block.toolTree ? 3 : 2}
              width={Math.max(2, width - (block.toolTree ? 7 : 6))} />
          </Box>}
        </> : <>
        <Box height={1} overflowX="hidden" paddingLeft={block.toolTree ? 2 : 0} paddingRight={1}>
          {/* Hit testing and hover paint share the clipped label's actual cell bounds. */}
          <Box ref={needsDisclosure ? summaryRef : undefined} flexGrow={0} flexShrink={1}
            backgroundColor={hovered && needsDisclosure ? colors.content.surface : undefined}>
            {presentation && isCommand ? (
              <Text color={hovered ? hoverColor(presentation) : colors.content.secondary}
                bold={hovered} wrap="truncate-end">
                {!block.toolTree && commandText.startsWith('● ') ? <>
                  <Text color={colors.info}>●</Text>{' '}
                  <ToolAction label={commandText.slice(2)} />
                </> : commandText}
                {needsDisclosure && <>{' '}<DisclosureArrow glyph={disclosureGlyph} hovered={hovered} /></>}
              </Text>
            ) : <Text color={directRead && !block.toolTree ? undefined : hovered && needsDisclosure ? hoverColor(presentation) : colors.content.secondary}
              bold={hovered && needsDisclosure} underline={hovered && needsDisclosure && !presentation} wrap="truncate-end">
              {completionAction ? <Text color={colors.info}>
                {isCompletedPlan ? '● ' : '✓ '}
              </Text> : directRead && !block.toolTree ? <Text color={colors.info}>● </Text> :
                isGoalResult ? goalResult?.achieved ? '✓ ' : '! ' :
                block.toolTree ? (block.toolTree.last ? '└─ ' : '├─ ') : isThinking && !presentation
                  ? <><DisclosureArrow glyph="›" hovered={hovered && needsDisclosure} />{' '}</> : '● '}
              {completionAction ? <>
                <Text color={colors.info} bold>{completionAction}</Text>
                <Text>{headline.slice(completionAction.length)}</Text>
              </> : directRead && !block.toolTree ? <ToolAction label={`${parsed?.summary || 'Read file'} ${parsed?.path}`.trim()} />
                : directFile && !block.toolTree ? `${parsed?.summary || ''} ${parsed?.path}`.trim()
                : visibleToolLabel}
              <Text color={colors.content.secondary}>{readRange}</Text>
              {needsDisclosure && <>{' '}<DisclosureArrow glyph={disclosureGlyph} hovered={hovered && needsDisclosure} /></>}
            </Text>}
          </Box>
        </Box>
        {(!collapsed || directlyShown) && !directFile && <Box paddingLeft={block.toolTree ? 5 : 2} flexDirection="column">
          <Message message={block.message} isCollapsed={false} disableTruncation
            terminalWidth={width - (block.toolTree ? 7 : 4)} showToolHeading={false} compactSpacing presentation={presentation} />
        </Box>}
        </>}
      </> : <Message message={block.message} disableTruncation isNewGroup={!block.continuation}
        initialCodeFence={block.initialCodeFence}
        terminalWidth={width - 1} compactSpacing presentation={presentation} />}
    </Box>
  );
});

/**
 * A bounded Ink viewport. Off-screen content is represented by two spacers;
 * stable message IDs keep visible history memoized while the active tail grows.
 */
export const ConversationViewport: React.FC<ConversationViewportProps> = ({
  messages, width, height, isCollapsed, active = true, onDirectoryChange, bannerProps, onCtrlC, interruptNotice, inputTip,
  composerSelection, composerActive = active, presentation = false, activityLabel, keepMouseTracking = false,
  footerOffset = 0, externalHoverTip, mouseActive = active, mouseOverlayRef, mouseScrollBottom,
  collapsedStateRef,
}) => {
  const themeVersion = useThemeVersion();
  const uiLanguage = useUiLanguage();
  const { stdout } = useStdout();
  const { selection } = useApp();
  const layout = useMemo(() => new ConversationSelectionLayout(), []);
  const textSelection = useRef<ConversationTextSelection | null>(null);
  const composerSelectionId = '__composer__';
  const selectionOwner = useRef<'history' | 'composer' | null>(null);
  const blockRefs = useRef(new Map<string, DOMElement>());
  const onBlockRef = useCallback((id: string, node: DOMElement | null) => {
    if (node) blockRefs.current.set(id, node);
    else blockRefs.current.delete(id);
  }, []);
  const [selectionSnapshot, setSelectionSnapshot] = useState<ChatMessage[] | null>(null);
  const displayedMessages = selectionSnapshot ?? messages;
  const drag = useRef<{
    point: MousePoint; pointer: MousePoint | null; target: string | null;
    moved: boolean; movedVertically: boolean; resumeFollowing: boolean; unit: SelectionUnit;
  } | null>(null);
  const updateSelectionRef = useRef<(point: MousePoint) => void>(() => {});
  const selectionFrame = useMemo(() => createSelectionFrame(point => updateSelectionRef.current(point)), []);
  const edgeTimer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const stopEdgeScroll = () => { if (edgeTimer.current) clearInterval(edgeTimer.current); edgeTimer.current = undefined; };
  const clearSelection = () => {
    selectionFrame.cancel(); stopEdgeScroll();
    drag.current = null; textSelection.current = null;
    selectionOwner.current = null;
    copyGeneration.current++; clipboardAbort.current?.abort();
    selection?.setRange(undefined); setSelectionSnapshot(null);
  };
  const [copyNotice, setCopyNotice] = useState<string | null>(null);
  const copyGeneration = useRef(0);
  const clipboardAbort = useRef<AbortController | null>(null);
  const lastClick = useRef<{ point: MousePoint; time: number; count: number } | null>(null);
  const copiedText = useRef<string | null>(null);
  const copiedResult = useRef<'pending' | 'native' | 'osc52' | 'failed' | null>(null);
  const clearAfterCopy = useRef(false);
  const copySelection = (clearAfter = false) => {
    const text = textSelection.current?.text() ?? '';
    if (!text.trim()) return;
    clearAfterCopy.current ||= clearAfter;
    if (copiedText.current === text && copiedResult.current !== 'failed' &&
      !(clearAfter && copiedResult.current === 'osc52')) {
      if (clearAfter && copiedResult.current === 'native') clearSelection();
      return;
    }
    clearAfterCopy.current = clearAfter;
    copiedText.current = text;
    copiedResult.current = 'pending';
    clipboardAbort.current?.abort();
    const abort = new AbortController();
    clipboardAbort.current = abort;
    const generation = ++copyGeneration.current;
    void copySelectionToClipboard(text, stdout, abort.signal).then(result => {
      if (copyGeneration.current === generation && !abort.signal.aborted) {
        copiedResult.current = result;
        const count = [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(text)].length;
        setCopyNotice(result === 'native' ? HISTORY_TIPS.copied(count) :
          result === 'osc52' ? HISTORY_TIPS.oscCopied(count) : HISTORY_TIPS.copyFailed);
        if (result === 'native' && clearAfterCopy.current) clearSelection();
      }
    });
  };
  useEffect(() => () => {
    selectionFrame.cancel(); stopEdgeScroll();
    copyGeneration.current++; clipboardAbort.current?.abort(); selection?.setRange(undefined);
  }, [selection, selectionFrame]);
  useEffect(() => {
    if (!copyNotice) return;
    const timer = setTimeout(() => setCopyNotice(null), 2000);
    return () => clearTimeout(timer);
  }, [copyNotice]);
  const blocks = useMemo(() => conversationBlocks(displayedMessages, presentation), [displayedMessages, presentation]);
  const rootRef = useRef<DOMElement>(null);
  const scrollbarDrag = useRef<{ offset: number } | null>(null);
  const pinRef = useRef<DOMElement>(null);
  const footerRef = useRef<DOMElement>(null);
  const headingRefs = useRef(new Map<string, DOMElement>());
  const pointer = useRef<MousePoint | null>(null);
  const hoveredRef = useRef<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const updateHover = useCallback((target: string | null) => {
    if (hoveredRef.current === target) return;
    hoveredRef.current = target;
    setHovered(target);
  }, []);
  const onHeadingRef = useCallback((id: string, node: DOMElement | null) => {
    if (node) headingRefs.current.set(id, node);
    else headingRefs.current.delete(id);
  }, []);
  const [bannerRef, bannerHeight] = useMeasuredHeight();
  const [scrollPosition, setScrollPosition] = useState({ top: 0 });
  const scrollTop = scrollPosition.top;
  // Following mode can change while the numeric offset stays the same.
  const setScrollTop = useCallback((top: number) => setScrollPosition({ top }), []);
  const anchor = useRef<{ id: string; offset: number } | null>(null);
  const following = useRef(!bannerProps || messages.length === 0);
  const [expanded, setExpanded] = useState<Map<string, boolean>>(new Map());
  if (collapsedStateRef) collapsedStateRef.current = expanded;
  // Replace the cache before measuring a new layout, never after child layout effects.
  const measured = useMemo(() => new Map<string, number>(), [width, themeVersion, isCollapsed, uiLanguage]);
  const [revision, setRevision] = useState(0);
  const [directory, setDirectory] = useState(false);
  let latestUser: ChatMessage | undefined;
  for (let index = displayedMessages.length - 1; index >= 0; index--) {
    if (displayedMessages[index].type === 'user' && displayedMessages[index].metadata?.sendFailed !== true &&
      displayedMessages[index].metadata?.sendPending !== true) { latestUser = displayedMessages[index]; break; }
  }
  const users = useMemo(() => displayedMessages.filter(message => message.type === 'user'), [displayedMessages]);
  const [selectedTurn, setSelectedTurn] = useState(0);
  const [unread, setUnread] = useState(false);
  const previousTail = useRef<ChatMessage | undefined>(undefined);
  useEffect(() => { onDirectoryChange?.(directory); }, [directory, onDirectoryChange]);
  const defaultCollapsed = isCollapsed;
  const collapsed = useCallback((id: string) => expanded.get(id) ?? defaultCollapsed, [expanded, defaultCollapsed]);
  const viewportRows = Math.max(1, height - 1);
  const onMeasure = useCallback((id: string, rows: number) => {
    if (measured.get(id) === rows) return;
    measured.set(id, rows);
    if (measured.size > 256) measured.delete(measured.keys().next().value!);
    setRevision(value => value + 1);
  }, [measured]);
  useEffect(() => { setExpanded(new Map()); }, [isCollapsed]);
  const pinIdentity = useRef(latestUser?.id);
  useEffect(() => {
    if (pinIdentity.current === latestUser?.id) return;
    pinIdentity.current = latestUser?.id;
    following.current = true;
    anchor.current = null; setUnread(false); setScrollTop(0);
  }, [latestUser?.id]);
  useEffect(() => {
    const tail = messages[messages.length - 1];
    if (tail !== previousTail.current && previousTail.current && !following.current) setUnread(true);
    previousTail.current = tail;
  }, [messages]);
  useMouseTracking(active || mouseActive || composerActive || keepMouseTracking);
  const offsets = useMemo(() => {
    const result = [bannerProps ? bannerHeight : 0];
    for (const block of blocks) {
      result.push(result[result.length - 1] +
        (measured.get(block.id) ?? estimateBlockRows(block, width, collapsed(block.id))));
    }
    return result;
  }, [blocks, width, collapsed, measured, revision, bannerProps, bannerHeight]);
  const total = offsets[offsets.length - 1];
  const maximum = Math.max(0, total - viewportRows);
  const anchorIndex = anchor.current ? blocks.findIndex(block => block.id === anchor.current?.id) : -1;
  const position = following.current ? maximum : Math.min(maximum, Math.max(0,
    anchorIndex >= 0 ? offsets[anchorIndex] + anchor.current!.offset : scrollTop));
  const committedPosition = useRef(position);
  committedPosition.current = position;
  let stickyUser: ChatMessage | undefined;
  for (let index = 0; index < blocks.length && offsets[index] < position; index++) {
    const message = blocks[index].message;
    if (message.type === 'user' && !message.metadata?.sendFailed && !message.metadata?.sendPending) stickyUser = message;
  }
  if (presentation && !active && !stickyUser) {
    for (let index = messages.length - 1; index >= 0; index--) {
      const message = messages[index];
      if (message.type === 'user' && !message.metadata?.sendFailed && !message.metadata?.sendPending) {
        stickyUser = message;
        break;
      }
    }
  }
  let start = 0;
  while (start < blocks.length && offsets[start + 1] < position - viewportRows) start++;
  let end = start;
  while (end < blocks.length && offsets[end] < position + viewportRows * 2 &&
    end - start < Math.max(60, viewportRows * 3)) end++;
  const toggle = useCallback((id: string) => {
    const index = blocks.findIndex(block => block.id === id);
    const block = blocks[index];
    if (block && collapsed(id) && following.current &&
      total + estimateBlockRows(block, width, false) - (offsets[index + 1] - offsets[index]) > viewportRows) {
      // Keep the heading in view when expansion grows the history beyond its viewport.
      const first = blocks.findIndex((_, index) => offsets[index + 1] > position);
      anchor.current = first >= 0 ? { id: blocks[first].id, offset: position - offsets[first] } : null;
      following.current = false;
      setScrollTop(position);
    }
    measured.delete(id);
    setExpanded(current => {
      const next = new Map(current);
      next.set(id, !(current.get(id) ?? defaultCollapsed));
      if (next.size > 256) next.delete(next.keys().next().value!);
      return next;
    });
  }, [blocks, collapsed, defaultCollapsed, measured, offsets, position, total, viewportRows, width]);
  const scroll = (delta: number) => {
    const next = Math.max(0, Math.min(maximum, committedPosition.current + delta));
    if (next === committedPosition.current) return false;
    committedPosition.current = next;
    const index = blocks.findIndex((_, index) => offsets[index + 1] > next);
    anchor.current = index >= 0 ? { id: blocks[index].id, offset: next - offsets[index] } : null;
    following.current = next >= maximum && !textSelection.current;
    if (following.current) setUnread(false);
    setScrollTop(next);
    return true;
  };
  const dragScrollbar = (point: MousePoint) => {
    const current = scrollbarDrag.current;
    const track = rootRef.current && getVerticalScrollbarBoundingBox(rootRef.current);
    if (!current || !track) { scrollbarDrag.current = null; return; }
    // Use Ink's half-cell thumb geometry, preserving the grabbed point.
    const travel = track.height - (track.thumb.endHalf - track.thumb.startHalf) / 2;
    if (travel <= 0) return;
    const fraction = point.y <= track.y ? 0 : point.y >= track.y + track.height - 1 ? 1 :
      Math.max(0, Math.min(1, (point.y + 0.5 - track.y - current.offset) / travel));
    scroll(Math.round(fraction * maximum) - committedPosition.current);
  };
  useLayoutEffect(() => {
    scrollbarDrag.current = null;
  }, [width, height, mouseActive, directory]);
  const bottom = () => {
    clearSelection(); following.current = true; anchor.current = null; setUnread(false); setScrollTop(maximum);
  };
  const jump = (turn: number) => {
    clearSelection();
    const target = Math.max(0, Math.min(users.length - 1, turn));
    setSelectedTurn(target);
    const index = blocks.findIndex(block => block.message.id === users[target]?.id);
    following.current = false;
    if (index >= 0) {
      anchor.current = { id: blocks[index].id, offset: 0 };
      setScrollTop(offsets[index]);
    }
  };
  const historyTurn = blocks.find((_, index) => offsets[index + 1] > position)?.turn ?? users.length;
  const directoryStart = Math.max(0, selectedTurn - Math.floor(viewportRows / 2));
  const mouseTarget = (point: MousePoint): string | null => {
    if (containsPoint(mouseOverlayRef?.current ?? null, point)) return null;
    // The sticky prompt occludes headings at the top of the history.
    if (!directory && stickyUser && containsPoint(pinRef.current, point)) return 'pin';
    if (!directory && !following.current && (!presentation || !copyNotice && !interruptNotice) &&
      containsPoint(footerRef.current, point)) return 'bottom';
    if (!containsPoint(rootRef.current, point)) return null;
    if (directory && rootRef.current) {
      const box = getBoundingBox(rootRef.current);
      const index = Math.floor(point.y - box.y) - 1 + directoryStart;
      return point.y >= box.y + 1 && point.y < box.y + viewportRows && users[index] ? `turn:${index}` : null;
    }
    for (const [id, node] of headingRefs.current) {
      if (containsPoint(node, point)) return `block:${id}`;
    }
    return null;
  };
  const clipRef = useRef({ x: 0, y: 0, width, height: viewportRows });
  const refreshSelectionLayout = (owner = selectionOwner.current) => {
    if (!rootRef.current || directory) return;
    if (owner === 'composer') {
      const surface = composerSelection?.current;
      if (!surface?.root) return;
      const bounds = getBoundingBox(surface.root);
      const clip = { ...bounds, width: Math.min(bounds.width, width - 1),
        height: Math.max(0, Math.min(bounds.height, (stdout?.rows || bounds.y + bounds.height) - 1 - bounds.y)) };
      clipRef.current = clip;
      const nodes = new Map([[composerSelectionId, surface.root]]);
      const sources = surface.source ? new Map([[composerSelectionId, surface.source]]) : undefined;
      layout.refresh(nodes, clip, sources);
      textSelection.current?.observe(layout);
      return;
    }
    const bounds = getBoundingBox(rootRef.current);
    const top = stickyUser ? 1 : 0;
    const clip = { ...bounds, y: bounds.y + top, height: Math.max(0, bounds.height - top), width: Math.max(1, bounds.width - 1) };
    clipRef.current = clip;
    layout.refresh(blockRefs.current, clip);
    textSelection.current?.observe(layout);
  };
  const edgeTick = useRef<() => void>(() => {});
  edgeTick.current = () => {
    const current = drag.current;
    if (!current?.pointer || !current.movedVertically || !textSelection.current || !mouseActive || directory ||
      selectionOwner.current === 'composer') {
      stopEdgeScroll(); return;
    }
    const clip = clipRef.current;
    const direction = current.pointer.y <= clip.y ? -1 :
      current.pointer.y >= clip.y + clip.height - 1 ? 1 : 0;
    if (!direction || !scroll(direction)) stopEdgeScroll();
  };
  updateSelectionRef.current = point => {
    const current = drag.current, model = textSelection.current;
    if (!current || !model) return;
    current.moved ||= point.x !== current.point.x || point.y !== current.point.y;
    current.movedVertically ||= point.y !== current.point.y;
    current.pointer = point;
    const end = layout.hit(point);
    if (end && model.extend(end, layout)) model.paint(layout, selection);
    const clip = clipRef.current;
    const edge = selectionOwner.current === 'history' && (point.y <= clip.y || point.y >= clip.y + clip.height - 1);
    if (current.movedVertically && edge && !edgeTimer.current) {
      edgeTimer.current = setInterval(() => edgeTick.current(), SELECTION_FRAME_MS);
    } else if (!edge) stopEdgeScroll();
  };
  useLayoutEffect(() => {
    if (!mouseActive) {
      stopEdgeScroll();
      updateHover(null);
    }
    const ownerActive = selectionOwner.current === 'composer' ? composerActive : mouseActive;
    if (!ownerActive) {
      pointer.current = null;
      if (drag.current || textSelection.current) clearSelection();
      clipboardAbort.current?.abort();
      return;
    }
    refreshSelectionLayout();
    if (drag.current?.pointer && drag.current.moved) updateSelectionRef.current(drag.current.pointer);
    textSelection.current?.paint(layout, selection);
    // Recheck after scrolling, resizing or streaming moves a heading under the pointer.
    if (!drag.current) updateHover(mouseActive && pointer.current ? mouseTarget(pointer.current) : null);
  });
  useLayoutEffect(() => {
    if (!composerSelection) return;
    const update = () => {
      if (selectionOwner.current !== 'composer') return;
      refreshSelectionLayout('composer');
      if (textSelection.current && !textSelection.current.matchesSource(layout)) {
        clearSelection();
        return;
      }
      textSelection.current?.paint(layout, selection);
    };
    composerSelection.current.onUpdate = update;
    return () => {
      if (composerSelection.current.onUpdate === update) composerSelection.current.onUpdate = undefined;
    };
  });
  useKeypress(key => {
    const isWheel = key.name === 'wheelup' || key.name === 'wheeldown';
    if (!isWheel && !active && !mouseActive && !composerActive) return;
    if (key.name === 'escape') scrollbarDrag.current = null;
    if ((key.name === 'selectioncopy' || ((key.ctrl || key.cmd) && key.name === 'c')) &&
      textSelection.current && !textSelection.current.empty) {
      // A right-click copy belongs to a visible selection surface, not an overlay.
      if (key.sequence.startsWith('\x1b[<')) {
        const point = mousePosition(key);
        const root = selectionOwner.current === 'composer'
          ? composerSelection?.current.root : rootRef.current;
        if (!point || containsPoint(mouseOverlayRef?.current ?? null, point) ||
          !containsPoint(root ?? null, point)) return;
      }
      selectionFrame.flush();
      copySelection(true);
      return;
    }
    if ((key.name === 'escape' || key.name === 'selectionclear') && textSelection.current) {
      clearSelection(); return;
    }
    if (key.name === 'mousemove' || key.name === 'mouseclick' || key.name === 'mouserelease') {
      const point = mousePosition(key);
      let releasePoint = key.name === 'mouserelease'
        ? mousePosition({ ...key, sequence: key.sequence.replace(/m$/, 'M') }) : point;
      if (!releasePoint) return;
      // Capture before text selection and overlays so release always ends the gesture.
      if (scrollbarDrag.current && key.name !== 'mouseclick') {
        if (key.name === 'mouserelease' || /\x1b\[<35;/.test(key.sequence)) {
          if (key.name === 'mouserelease') dragScrollbar(releasePoint);
          scrollbarDrag.current = null;
        } else dragScrollbar(releasePoint);
        return;
      }
      if (key.name === 'mouseclick') {
        scrollbarDrag.current = null;
        const track = mouseActive && !directory && maximum > 0 && rootRef.current &&
          getVerticalScrollbarBoundingBox(rootRef.current);
        if (track && !containsPoint(mouseOverlayRef?.current ?? null, releasePoint) &&
          releasePoint.x === track.x && releasePoint.y >= track.y && releasePoint.y < track.y + track.height) {
          const onThumb = releasePoint.y >= track.thumb.y && releasePoint.y < track.thumb.y + track.thumb.height;
          const travel = track.height - (track.thumb.endHalf - track.thumb.startHalf) / 2;
          const offset = onThumb ? releasePoint.y + 0.5 - track.y - committedPosition.current / maximum * travel :
            (track.thumb.endHalf - track.thumb.startHalf) / 4;
          clearSelection(); lastClick.current = null; pointer.current = null; updateHover(null);
          scrollbarDrag.current = { offset };
          if (!onThumb) dragScrollbar(releasePoint);
          return;
        }
      }
      if (isMermaidControlAt(stdout, releasePoint)) {
        pointer.current = null;
        updateHover(null);
        if (key.name === 'mouseclick') clearSelection();
        return;
      }
      if (containsPoint(mouseOverlayRef?.current ?? null, releasePoint)) {
        pointer.current = null;
        updateHover(null);
        if (key.name === 'mouseclick') { clearSelection(); return; }
        if (!drag.current) return;
        selectionFrame.flush(); stopEdgeScroll();
        if (key.name === 'mousemove') return;
        // Finish captured gestures at the last visible point, without selecting behind the overlay.
        releasePoint = drag.current.pointer ?? drag.current.point;
      }
      const navigationTarget = mouseActive ? mouseTarget(releasePoint) : null;
      const inComposer = navigationTarget !== 'bottom' && composerActive && !directory &&
        containsPoint(composerSelection?.current.root ?? null, releasePoint);
      if (!mouseActive && !inComposer &&
        !(drag.current && selectionOwner.current === 'composer' && key.name !== 'mouseclick')) {
        if (key.name === 'mouseclick' && textSelection.current) clearSelection();
        return;
      }
      pointer.current = releasePoint;
      if (key.name === 'mousemove') {
        if (drag.current && textSelection.current) selectionFrame.queue(releasePoint);
        else updateHover(mouseActive ? mouseTarget(releasePoint) : null);
        return;
      }
      const target = inComposer || !mouseActive ? null : navigationTarget;
      if (key.name === 'mouseclick') {
        selectionFrame.cancel(); stopEdgeScroll();
        const owner = inComposer ? 'composer' : 'history';
        const extendingOwner = !selectionOwner.current || selectionOwner.current === owner;
        refreshSelectionLayout(owner);
        const point = !directory && target !== 'pin' && target !== 'bottom' &&
          (inComposer || mouseActive && containsPoint(rootRef.current, releasePoint))
          ? layout.hit(releasePoint, true, !inComposer) : undefined;
        const textHit = point ? layout.hit(releasePoint, false) : undefined;
        const extending = key.shift && extendingOwner && textSelection.current && point;
        if (!extending) {
          textSelection.current = null;
          selectionOwner.current = null;
          selection?.setRange(undefined);
        }
        copyGeneration.current++;
        clipboardAbort.current?.abort();
        copiedText.current = null;
        copiedResult.current = null; clearAfterCopy.current = false;
        setCopyNotice(null);
        const now = Date.now();
        const previous = lastClick.current;
        const count = textHit && !target && !key.shift && previous && now - previous.time < 400 &&
          previous.point.x === releasePoint.x && previous.point.y === releasePoint.y
          ? previous.count % 3 + 1 : 1;
        lastClick.current = { point: releasePoint, time: now, count };
        const resumeFollowing = following.current;
        const unit = count === 3 ? 'line' : count === 2 ? 'word' : 'character';
        if (point) {
          selectionOwner.current = owner;
          textSelection.current ??= new ConversationTextSelection(
            inComposer ? [composerSelectionId] : blocks.map(block => block.id), point, unit, layout,
            new Set(blocks.filter(block => block.continuation).map(block => block.id)),
            new Set(blocks.filter(block => block.toolTree && !block.toolTree.first).map(block => block.id)),
          );
          if (!inComposer) {
            const first = blocks.findIndex((_, index) => offsets[index + 1] > position);
            anchor.current = first >= 0 ? { id: blocks[first].id, offset: position - offsets[first] } : null;
            following.current = false;
            setScrollTop(position);
          }
          // Message updates replace records; retaining handles also preserves memoized content.
          setSelectionSnapshot(inComposer ? null : displayedMessages.slice());
        } else {
          setSelectionSnapshot(null);
          updateHover(target);
        }
        drag.current = {
          point: releasePoint, pointer: releasePoint, target, moved: count > 1 || Boolean(extending),
          movedVertically: false, resumeFollowing, unit,
        };
        if (extending) textSelection.current?.extend(point!, layout);
        textSelection.current?.paint(layout, selection);
        return;
      }
      const current = drag.current;
      if (!current) return;
      if (releasePoint.x !== current.point.x || releasePoint.y !== current.point.y) current.moved = true;
      if (current.moved && current.pointer && textSelection.current) selectionFrame.queue(releasePoint);
      selectionFrame.flush(); stopEdgeScroll();
      drag.current = null;
      if (textSelection.current && !textSelection.current.empty) {
        copySelection();
        return;
      }
      if (!current.moved && current.resumeFollowing && selectionOwner.current !== 'composer') {
        following.current = true; anchor.current = null;
      }
      clearSelection();
      updateHover(target);
      if (current.moved) return;
      if (!target || target !== current.target || lastClick.current?.count !== 1) return;
      if (target === 'pin') jump(users.findIndex(user => user.id === stickyUser?.id));
      else if (target === 'bottom') bottom();
      else if (target.startsWith('turn:')) { jump(Number(target.slice(5))); setDirectory(false); }
      else if (target.startsWith('block:')) toggle(target.slice(6));
      return;
    }
    if (textSelection.current && (key.insertable || selectionOwner.current === 'composer' &&
      ['left', 'right', 'up', 'down', 'return', 'backspace', 'delete'].includes(key.name))) clearSelection();
    const wheel = key.name === 'wheelup' || key.name === 'wheeldown';
    const keyboardScroll = key.ctrl && !key.alt && !key.shift && !key.cmd &&
      (key.name === 'up' || key.name === 'down');
    if (wheel) {
      const point = mousePosition(key);
      // Panels own keyboard focus; the wheel belongs to the visible region.
      if (!mouseActive && !keepMouseTracking || !point && !active) return;
      if (point && (!containsPoint(rootRef.current, point) ||
        containsPoint(mouseOverlayRef?.current ?? null, point) ||
        mouseScrollBottom !== undefined && point.y >= mouseScrollBottom)) return;
    } else if (!active) return;
    if (keyboardScroll || ['wheelup', 'wheeldown', 'pageup', 'pagedown', 'home', 'end'].includes(key.name)) {
      scrollbarDrag.current = null;
    }
    if ((keyboardScroll || ['wheelup', 'wheeldown', 'pageup', 'pagedown'].includes(key.name)) && drag.current) {
      selectionFrame.flush(); stopEdgeScroll();
      drag.current.pointer = null; drag.current.moved = true; drag.current.resumeFollowing = false;
    }
    if (key.name === 'wheelup' || keyboardScroll && key.name === 'up') scroll(-3);
    else if (key.name === 'wheeldown' || keyboardScroll && key.name === 'down') scroll(3);
    else if (key.name === 'pageup') scroll(-viewportRows);
    else if (key.name === 'pagedown') scroll(viewportRows);
    else if (key.ctrl && key.name === 'end') bottom();
    else if (key.ctrl && key.name === 'home') {
      clearSelection();
      following.current = false; anchor.current = null; setScrollTop(0);
    }
    else if (key.alt && key.name === 'up') jump((directory ? selectedTurn : historyTurn - 1) - 1);
    else if (key.alt && key.name === 'down') jump((directory ? selectedTurn : historyTurn - 1) + 1);
    else if (key.ctrl && key.name === 'g') { clearSelection(); setDirectory(value => !value); setSelectedTurn(users.length - 1); }
    else if (directory && (key.name === 'escape' || (onCtrlC && key.ctrl && key.name === 'c'))) {
      setDirectory(false);
      if (key.ctrl && key.name === 'c') onCtrlC?.('modal');
    }
    else if (directory && key.name === 'up') setSelectedTurn(value => Math.max(0, value - 1));
    else if (directory && key.name === 'down') setSelectedTurn(value => Math.min(users.length - 1, value + 1));
    else if (directory && key.name === 'return') { jump(selectedTurn); setDirectory(false); }
    else if (presentation && key.name === 'escape' && !directory && !following.current) bottom();
  }, { isActive: active || mouseActive || composerActive || keepMouseTracking });
  const pinLines = useMemo(() => {
    const lines: string[] = [];
    // Wrap only the pinned prompt, using terminal display cells for CJK.
    for (const paragraph of (stickyUser?.content || '').split('\n')) {
      let line = '', cells = 0;
      for (const character of paragraph) {
        const size = stringWidth(character);
        if (cells + size > Math.max(4, width - 4)) { lines.push(line); line = ''; cells = 0; }
        line += character; cells += size;
      }
      lines.push(line);
    }
    return lines;
  }, [stickyUser, width]);
  const hoveredBlock = hovered?.startsWith('block:') ? blocks.find(block => block.id === hovered.slice(6)) : undefined;
  const hoverHint = externalHoverTip || (hovered === 'pin' ? HISTORY_TIPS.pin :
    hovered === 'bottom' ? presentation ? null : HISTORY_TIPS.bottom :
    hovered?.startsWith('turn:') ? HISTORY_TIPS.turn(Number(hovered.slice(5)) + 1) :
    hoveredBlock ? HISTORY_TIPS.block(!collapsed(hoveredBlock.id),
      hoveredBlock.message.metadata?.subtype === 'thinking') : null);
  const showBottomButton = presentation && !directory && !following.current &&
    !copyNotice && !interruptNotice && !textSelection.current;
  const bottomLabel = HISTORY_TIPS.bottomButton(width < 100, unread);
  const tipWidth = showBottomButton ? Math.max(1, Math.floor((width - stringWidth(bottomLabel)) / 2) - 1) : undefined;
  const footerTip = interruptNotice || copyNotice || hoverHint || inputTip ||
    (presentation || following.current ? '' : HISTORY_TIPS.jump(unread));
  const visibleTip = tipWidth && stringWidth(footerTip) > tipWidth
    ? footerTip.replace(/^Click to ([a-z])/, (_match, initial: string) => initial.toUpperCase())
    : footerTip;
  return <Box flexDirection="column" height={height} width={width} flexShrink={0}>
    <Box height={viewportRows} flexDirection="column" flexShrink={0}>
    {directory ? <Box ref={rootRef} height={viewportRows} flexDirection="column" overflowY="hidden" paddingX={1}>
      <Text color={colors.content.secondary}>{HISTORY_TIPS.directory}</Text>
      {users.slice(directoryStart, directoryStart + viewportRows - 1).map((user, index) =>
        <Box key={user.id} height={1} flexShrink={0}
          backgroundColor={hovered === `turn:${directoryStart + index}` ? colors.content.surface : undefined}>
          <Text color={directoryStart + index === selectedTurn || hovered === `turn:${directoryStart + index}` ? hoverColor(presentation) : colors.content.secondary}
            bold={directoryStart + index === selectedTurn || hovered === `turn:${directoryStart + index}`}
            underline={!presentation && hovered === `turn:${directoryStart + index}`} wrap="truncate-end">
            {directoryStart + index === selectedTurn ? '› ' : '  '}{directoryStart + index + 1}. {user.content.replace(/\s+/g, ' ')}
          </Text>
        </Box>)}
    </Box> : <Box ref={rootRef} height={viewportRows} flexShrink={0} overflowY="scroll" overflowX="hidden"
      scrollTop={position} scrollbarStyle="thin" scrollbarThumbColor={colors.gray[500]} flexDirection="column">
      {bannerProps && start === 0 ? <Box ref={bannerRef} flexShrink={0} flexDirection="column">
        <Banner {...bannerProps} interactive={active && !directory} />
      </Box> : null}
      <Box height={Math.max(0, offsets[start] - (bannerProps && start === 0 ? bannerHeight : 0))} flexShrink={0} />
      {blocks.slice(start, end).map(block => <ConversationBlock key={block.id} block={block} width={width}
        presentation={presentation}
        collapsed={collapsed(block.id)} onMeasure={onMeasure} onHeadingRef={onHeadingRef} onBlockRef={onBlockRef}
        hovered={hovered === `block:${block.id}`} />)}
      <Box height={Math.max(0, total - offsets[end])} flexShrink={0} />
    </Box>}
    {stickyUser && !directory && <Box ref={pinRef} position="absolute" width={width}
      height={1} flexShrink={0} overflowY="hidden" flexDirection="column">
      {pinLines.slice(0, 1).map((line, index) =>
        <Text key={index} backgroundColor={colors.content.surface} wrap="truncate-end">
          <Text color={hovered === 'pin' ? hoverColor(presentation) : undefined}
            bold={hovered === 'pin'} underline={!presentation && hovered === 'pin' && index === 0}>
            {index === 0 ? '› ' : '  '}{line}
          </Text>{' '.repeat(Math.max(0, width - 2 - stringWidth(line)))}
        </Text>)}
    </Box>}
    </Box>
    <Box ref={presentation ? undefined : footerRef} height={1} width={width} opaque
      position={footerOffset ? 'absolute' : 'relative'} marginTop={footerOffset ? height - 1 + footerOffset : 0}
      paddingLeft={presentation ? 0 : 1} paddingRight={1} flexShrink={0}
      justifyContent={presentation ? 'space-between' : undefined}
      backgroundColor={!presentation && hovered === 'bottom' ? colors.content.surface : undefined}>
      <ActivityIndicator label={activityLabel} hidden={Boolean(interruptNotice || copyNotice || inputTip)} />
      <Box flexGrow={presentation ? 1 : 0} flexShrink={1}
        justifyContent={presentation ? 'flex-end' : undefined} overflowX="hidden">
      <Box maxWidth={tipWidth} flexShrink={1} overflowX="hidden">
      <Text color={hoverHint ? hoverColor(presentation) : colors.content.secondary}
        bold={Boolean(hoverHint)} underline={!presentation && hovered === 'bottom'} wrap="truncate-end">
        {visibleTip}
      </Text>
      </Box>
      </Box>
      {showBottomButton && <Box position="absolute" width={width} height={1} justifyContent="center">
          <Box ref={footerRef} backgroundColor={hovered === 'bottom' ? colors.content.surface : undefined}>
            <Text color={hovered === 'bottom' ? hoverColor(true) : colors.content.secondary} bold={hovered === 'bottom'}>
              {bottomLabel}
            </Text>
          </Box>
        </Box>}
    </Box>
  </Box>;
};

/** Observe actual layout rather than guessing the height of completion/panel UI. */
export function useMeasuredHeight(initialHeight = 4): [React.RefObject<DOMElement | null>, number] {
  const ref = useRef<DOMElement>(null);
  const [height, setHeight] = useState(initialHeight);
  useLayoutEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(entries => {
      const next = Math.ceil(entries[0].contentRect.height);
      setHeight(previous => previous === next ? previous : next);
    });
    observer.observe(ref.current);
    setHeight(Math.ceil(measureElement(ref.current).height));
    return () => observer.disconnect();
  });
  return [ref, height];
}