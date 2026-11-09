/**
 * Multi-line prompt input component backed by a TextBuffer with visual-line layout.
 *
 * Uses a custom useKeypress hook (KeypressContext) instead of Ink's useInput so that
 * stdin is shared — App.tsx can still receive Ctrl+C while this component is focused.
 *
 * Key bindings:
 *   Enter          Submit message
 *   Shift/Alt/Ctrl+Enter  Insert newline
 *   Ctrl+J         Insert newline
 *   Up / Down      Navigate input history (or move cursor in multi-line buffers)
 *   Ctrl+A / E     Move to line start / end
 *   Ctrl+F         Move cursor right one char (readline)
 *   Ctrl+P / N     History prev / next (readline)
 *   Ctrl+W         Delete word left
 *   Alt+D          Delete word right
 *   Ctrl+K / U     Kill to line end / start
 *   Ctrl+L         Move to line end (same as Ctrl+E)
 *   Ctrl+X         Open buffer in external editor
 *   Ctrl+B         Copy all buffer content to OS clipboard
 *   Alt/Ctrl+Left/Right  Word-left / word-right
 *   Meta+B / Meta+F     Word-left / word-right (readline style)
 *   !              Toggle shell mode (when input is empty)
 *   Escape         Exit shell mode, dismiss autocomplete, or stop agent
 *
 * Autocomplete:
 *   @<path>        File / MCP resource completion
 *   /<name>        Command completion
 *   Tab / Enter    Accept suggestion
 *   Up / Down      Navigate suggestions
 *
 * Commands:
 *   /editor, /edit Open editor-selection dialog
 *   /export, /export <filename> Export conversation to a .txt file
 */

import React, { useState, useCallback, useRef, useEffect, useLayoutEffect, useMemo } from 'react';
import { Box, Text, useStdout, type DOMElement } from '@jrichman/ink';
import { githubTheme } from './theme.js';
import { useThemeVersion } from '../../themes/index.js';
import chalk from 'chalk';
import { useCommandCompletion } from '../../hooks/useCommandCompletion.js';
import { SuggestionsDisplay } from '../AutoComplete/SuggestionsDisplay.js';
import { LanguageSelector } from '../LanguageSelector/LanguageSelector.js';
import { useUiLanguage, saveUiLanguage, t, type UiLanguage } from '../../i18n/index.js';
import { CompletionMode } from '../../types/autocomplete.js';
import { useAppState, useAppDispatch } from '../../store/context.js';
import { toggleShellMode, setShellMode } from '../../store/reducers.js';
import { ShellModeIndicator } from '../Shell/ShellModeIndicator.js';
import { useShellCommand } from '../../hooks/useShellCommand.js';
import { useShellHistory } from '../../hooks/useShellHistory.js';
import { useEnhancedTextBuffer } from './TextBuffer.js';
import { EditorDialog, useEditorDialog } from '../EditorDialog/index.js';
import { StatusBarDialog, StatusDialog, useStatusBarDialog, useStatusDialog } from '../StatusBarDialog/index.js';
import { resolveEditorCommand } from '../../utils/editor.js';
import { configManager } from '../../utils/config.js';
import { writeFileSync, unlinkSync, mkdtempSync, readFileSync, rmdirSync } from 'fs';
import { join } from 'path';
import { tmpdir, homedir } from 'os';
import { spawnSync, execSync } from 'child_process';
import { logger } from '../../utils/logger.js';
import { Message } from '../../types/index.js';
import { useKeypress, type Key } from '../../hooks/useKeypress.js';
import type { CtrlCContext } from '../../hooks/useQuitShortcut.js';
import type { SelectionSurface } from '../../utils/conversationSelection.js';
import { DemoCompletionList } from '../layouts/DemoCompletionList.js';
import { cpLen, cpSlice } from './textUtils.js';
import { isClipboardPasteKey, useClipboard } from '../../hooks/useClipboard.js';
import { promptQueueStore } from '../../store/promptQueueStore.js';
import { inputRestoreStore } from '../../store/inputRestoreStore.js';
import { TodoDisplay } from '../Todo/TodoDisplay.js';
import { SubAgentDisplay } from '../SubAgent/SubAgentDisplay.js';
import { slashCommandService } from '../../services/slashCommandService.js';
import { INPUT_TIPS } from '../../constants/tips.js';
import { useEditorTerminal } from '../../hooks/useEditorTerminal.js';

/** Matches a fully-typed slash command name with no argument yet, e.g.
 * "/goal" or "/goal  " — used to decide when to show the dimmed inline
 * argument-format hint (ghost text) right after the command name. */
const COMMAND_ONLY_RE = /^\/([a-zA-Z0-9:_-]+)( *)$/;

/** Matches the leading slash-command token of the input (e.g. "/goal" in
 * "/goal fix the bug") — that token is rendered with a highlight color so the
 * command name visually stands out from the rest of the typed text. */
const SLASH_COMMAND_TOKEN_RE = /^\/[a-zA-Z0-9:_-]+/;

// Threshold: pastes longer than this are collapsed into a placeholder pill
const PASTE_THRESHOLD = 800;
const PASTE_LINE_THRESHOLD = 10;

function formatPasteRef(id: number, numLines: number): string {
  return `[Pasted text #${id} +${numLines} lines]`;
}

/** Match a paste placeholder immediately before the cursor */
const PASTE_REF_SUFFIX_RE = /\[Pasted text #(\d+) \+\d+ lines\]$/;

/** Expand all paste placeholders back to their original text before submission */
function expandPasteRefs(text: string, map: Map<number, string>): string {
  return text.replace(/\[Pasted text #(\d+) \+\d+ lines\]/g, (_, id) => map.get(Number(id)) ?? '');
}

function formatImageRef(id: number): string {
  return `[Image #${id}]`;
}

/** Match an image placeholder immediately before the cursor */
const IMAGE_REF_SUFFIX_RE = /\[Image #(\d+)\]$/;

/** Extract all image IDs referenced in text, return their file paths in insertion order. */
function collectImagePaths(text: string, map: Map<number, string>): string[] {
  const paths: string[] = [];
  const seen = new Set<number>();
  for (const m of text.matchAll(/\[Image #(\d+)\]/g)) {
    const id = Number(m[1]);
    if (!seen.has(id) && map.has(id)) {
      seen.add(id);
      paths.push(map.get(id)!);
    }
  }
  return paths;
}

export interface InputPromptWithWrapUseKPCProps {
  onTipChange?: (tip: string | null) => void;
  interactionActive?: boolean;
  onDemoFocusStatus?: () => void;
  onDemoCompletion?: (content: React.ReactNode | null, dialog?: boolean, dialogHeight?: number) => void;
  selectionRootOverride?: React.RefObject<DOMElement | null>;
  demoPresentation?: boolean;
  fullStatusBar?: boolean;
  onSubmit: (value: string, imagePaths?: string[]) => void;
  onAddMessage?: (message: Message) => void;
  onUpdateMessage?: (id: string, updates: Partial<Message>) => void;
  /** Export the current conversation to a .txt file (/export command). */
  onExport?: (filename: string) => void;
  placeholder?: string;
  disabled?: boolean;
  /**
   * Custom message to render when the input is `disabled`.
   * Defaults to "Waiting for response..." (the main agent is busy).
   * For example, when /btw side panel is owning keystrokes, callers can
   * pass a message that does NOT imply the main agent is processing —
   * /btw is an independent side flow.
   */
  disabledMessage?: string;
  focus?: boolean;
  maxLines?: number;
  /** Reserve history navigation bindings for the surrounding conversation view. */
  conversationNavigation?: boolean;
  selectionSurface?: React.RefObject<SelectionSurface>;
  width?: number; // Terminal width for border
  cwd?: string; // Current working directory for @ completion
  mcpResources?: Array<{ // MCP resources for @ completion
    uri: string;
    name: string;
    description?: string;
    mimeType?: string;
  }>;
  loading?: boolean; // Agent is responding (spinning animation active)
  onStopExecution?: () => void; // Callback to stop current execution
  onCtrlC?: (context?: CtrlCContext) => void;
  // Esc while busy: interrupt the current run but KEEP the queue so the backend
  // flushes and runs the queued prompts one-by-one.
  onFlushQueueAndRun?: () => void;
  // Up (with empty input + non-empty queue): after popping the queue back into
  // the input box, tell the backend to drop those pending injections.
  onCancelPendingQueue?: () => void;
  tokenUsage?: { // Token usage information

    contextSize: number;
    contextMax: number;
    message: string;
  };
  model?: string; // Current model name
  agent?: string; // Current agent name
  sessionId?: string | null; // Current session ID
  reasoningEffort?: string; // Current reasoning effort level, shown next to model
  thinkingEnabled?: boolean | null; // Whether thinking is explicitly OFF via /thinking off
  quotaUsage?: string | null;
  todoItems?: import('../../hooks/useAcp/types.js').TodoItem[];
  onTodoSelect?: (content: string) => void;
  subAgentItems?: import('../../hooks/useAcp/types.js').SubAgentItem[];
  onSubAgentSelect?: (id: string) => void;
  cacheStatus?: import('../../hooks/useAcp/types.js').CacheStatusData | null;
  workingDir?: string;
}

export const InputPromptWithWrapUseKPC: React.FC<InputPromptWithWrapUseKPCProps> = React.memo(({
  onSubmit,
  onAddMessage,
  onUpdateMessage,
  onExport,
  placeholder = t('输入消息、/命令或 @文件路径…', 'Type your message, /command, or @path/to/file ...'),
  disabled = false,
  disabledMessage = t('等待回复…', 'Waiting for response...'),
  focus = true,
  maxLines = 20,
  conversationNavigation = false,
  selectionSurface,
  demoPresentation = false,
  fullStatusBar = false,
  interactionActive = true,
  onDemoFocusStatus,
  onDemoCompletion,
  onTipChange,
  selectionRootOverride,
  width,
  cwd = process.cwd(),
  mcpResources = [],
  loading = false,
  onStopExecution,
  onCtrlC,
  onFlushQueueAndRun,
  onCancelPendingQueue,
  tokenUsage,

  model,
  agent,
  sessionId,
  reasoningEffort,
  thinkingEnabled,
  quotaUsage = null,
  todoItems = [],
  onTodoSelect,
  subAgentItems = [],
  onSubAgentSelect,
  cacheStatus = null,
  workingDir,
}) => {
  useThemeVersion(); // repaint on theme change (memo blocks prop-driven re-renders)
  const uiLanguage = useUiLanguage();
  const [languageDialogOpen, setLanguageDialogOpen] = useState(false);
  const closeLanguageDialog = useCallback(() => setLanguageDialogOpen(false), []);
  const CursorAwareText = Text as React.FC<React.ComponentProps<typeof Text> & {
    terminalCursorFocus?: boolean;
    terminalCursorPosition?: number;
  }>;
  const { stdout } = useStdout();
  const terminalWidth = width ?? stdout?.columns ?? 80;
  const selectionRoot = useRef<DOMElement>(null);
  const selectionLines = useRef(new Map<number, DOMElement>());

  const editorDialog = useEditorDialog();
  const statusBarDialog = useStatusBarDialog();
  const statusDialog = useStatusDialog();

  // ---- 状态栏辅助函数 ----

  // 格式化成本金额
  const formatCost = (cny: number): string => `¥${cny.toFixed(4)}`;

  // 格式化 token 数量（千分位）
  const formatTokenCount = (count: number): string => count.toLocaleString('en-US');

  // 格式化耗时
  const formatDuration = (seconds: number): string => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m${s}s`;
  };

  // 缩写 workspace 路径（用 ~ 替换 home）
  const formatWorkspace = (dir: string): string => {
    const home = homedir();
    return dir.startsWith(home) ? `~${dir.slice(home.length)}` : dir;
  };

  // 获取 git 分支
  const getGitBranch = (dir: string): string | null => {
    try {
      const result = execSync('git branch --show-current', {
        cwd: dir,
        encoding: 'utf-8',
        timeout: 2000,
      }).trim();
      return result || null;
    } catch {
      return null;
    }
  };

  // git branch 用 useMemo 缓存
  const gitBranch = useMemo(() => {
    if (!workingDir) return null;
    return getGitBranch(workingDir);
  }, [workingDir]);

  // 构建可见的状态栏项列表——保持单色，按逻辑分组用 │ 分割线区分，
  // 组内仍用双空格连接。分组：① model/balance ② 5 项成本 ③ hit_rate/cost_time ④ git/workspace
  //
  // 3 档自适应伸缩：宽度不够时按优先级逐组丢弃（① ④ 优先保留）：
  //   档1（完整）：全部分组
  //   档2：丢弃 ② 5 项成本明细 (in/out/cw/cr/cost)
  //   档3：再丢弃 ③ hit_rate/cost_time
  const GROUP_SEPARATOR = '  │  ';
  const ITEM_SEPARATOR = '  ';

  const measureWidth = (segs: { text: string; group: number }[]): number => {
    let width = 0;
    segs.forEach((seg, idx) => {
      if (idx > 0) {
        width += segs[idx - 1].group !== seg.group ? GROUP_SEPARATOR.length : ITEM_SEPARATOR.length;
      }
      width += seg.text.length;
    });
    return width;
  };

  const statusBarParts = useMemo(() => {
    if (demoPresentation && !fullStatusBar) return { segments: [{ key: 'model', text: model || 'offline', group: 1 }], right: null };
    const parts: { key: string; text: string; group: number }[] = [];
    const visibleKeys = statusBarDialog.visibleItems;
    const cs = cacheStatus;
    const tu = tokenUsage;

    const addIfVisible = (key: string, text: string | null, group: number) => {
      if (visibleKeys.includes(key) && text !== null) {
        parts.push({ key, text, group });
      }
    };

    // Status-bar model segment reflects the thinking state:
    //   - thinking explicitly OFF (/thinking off) → "model(thinking off)"
    //   - thinking on → the effort level when the model exposes one, e.g.
    //     "baidu-deepseek-v4-flash-0731(low)"; otherwise just the model name.
    const modelText = model
      ? (thinkingEnabled === false
          ? `${model}(thinking off)`
          : (reasoningEffort ? `${model}(${reasoningEffort})` : model))
      : null;
    addIfVisible('model', modelText, 1);
    addIfVisible('balance', (quotaUsage !== null && quotaUsage !== undefined) ? `Balance: ${quotaUsage}` : null, 1);
    addIfVisible('input_cost', cs ? `in:${formatCost(cs.accumulated_input_cost)}(${formatTokenCount(cs.accumulated_input)})` : null, 2);
    addIfVisible('output_cost', cs ? `out:${formatCost(cs.accumulated_output_cost)}(${formatTokenCount(cs.accumulated_output)})` : null, 2);
    addIfVisible('cache_write_cost', cs ? `cw:${formatCost(cs.accumulated_cache_write_cost)}(${formatTokenCount(cs.accumulated_cache_write)})` : null, 2);
    addIfVisible('cache_read_cost', cs ? `cr:${formatCost(cs.accumulated_cache_read_cost)}(${formatTokenCount(cs.accumulated_cache_read)})` : null, 2);
    addIfVisible('total_cost', cs ? `cost:${formatCost(cs.accumulated_total_cost)}(${formatTokenCount(cs.accumulated_input + cs.accumulated_output + cs.accumulated_cache_read + cs.accumulated_cache_write)})` : null, 2);
    addIfVisible('hit_rate', (cs && cs.accumulated_hit_rate != null) ? `hit:${cs.accumulated_hit_rate.toFixed(2)}%` : null, 3);
    addIfVisible('cost_time', cs ? formatDuration(cs.cost_time_seconds) : null, 3);
    addIfVisible('git_branch', gitBranch ? `⎇ ${gitBranch}` : null, 4);
    addIfVisible('workspace', workingDir ? formatWorkspace(workingDir) : null, 4);

    // token_usage 单独处理（放在右侧）
    const rightText = visibleKeys.includes('token_usage') && tu?.message ? tu.message : null;

    // 可用宽度：终端宽度减去左右 padding(各1) 和右侧文本占位
    const available = Math.max(terminalWidth - 2 - (rightText ? rightText.length + 2 : 0), 0);

    let segments = parts;
    if (measureWidth(segments) > available) {
      // 档2：丢弃 4 项成本明细 (in/out/cw/cr)，保留 cost 汇总
      segments = segments.filter((seg) => seg.group !== 2 || seg.key === 'total_cost');
    }
    if (measureWidth(segments) > available) {
      // 档3：再丢弃 hit_rate/cost_time (group 3)
      segments = segments.filter((seg) => seg.group !== 3);
    }

    return { segments, right: rightText };
  }, [model, reasoningEffort, thinkingEnabled, quotaUsage, cacheStatus, tokenUsage, gitBranch, workingDir, statusBarDialog.visibleItems, terminalWidth, demoPresentation, fullStatusBar]);

  const FRAME_PADDING_AND_BORDER = 4;
  const PROMPT_PREFIX_WIDTH = 2;
  const FRAME_OVERHEAD = FRAME_PADDING_AND_BORDER + PROMPT_PREFIX_WIDTH;
  const CURSOR_EXTRA = 1;
  const SAFETY_MARGIN = 1;

  const viewportWidth = Math.max(
    terminalWidth - FRAME_OVERHEAD - CURSOR_EXTRA - SAFETY_MARGIN,
    40,
  );
  
  const buffer = useEnhancedTextBuffer({
    width: viewportWidth,
    height: maxLines,
  });

  // Restore text handed back by the backend (reason 'restore_input') into the
  // input box — user input interrupted by Ctrl+C before being persisted would
  // otherwise be lost. One-shot: consume() clears the store once applied.
  useEffect(() => {
    const apply = () => {
      const text = inputRestoreStore.consume();
      if (text) {
        buffer.setText(text);
      }
    };
    apply(); // drain anything requested before this component mounted
    return inputRestoreStore.subscribe(apply);
  }, [buffer]);

  const [historyIndex, setHistoryIndex] = useState(-1);
  const [tempInput, setTempInput] = useState('');
  const historyRef = useRef<string[]>([]);
  // Stores original text for large paste placeholders: id → full text
  const pastedTextsRef = useRef<Map<number, string>>(new Map());
  const nextPasteIdRef = useRef(1);
  // Stores temp image file paths for image paste placeholders: id → filePath
  const imagePathsRef = useRef<Map<number, string>>(new Map());
  const nextImageIdRef = useRef(1);
  const clearedDraftTextRef = useRef<string | null>(null);
  const deleteStreak = useRef({ count: 0, lastAt: 0, shownAt: 0 });
  const tipTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tipGeneration = useRef(0);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      tipGeneration.current++;
      if (tipTimer.current) clearTimeout(tipTimer.current);
      onTipChange?.(null);
    };
  }, [onTipChange]);
  const showTip = useCallback((tip: string, duration = 2200) => {
    if (!mounted.current) return;
    if (tipTimer.current) clearTimeout(tipTimer.current);
    onTipChange?.(tip);
    if (duration > 0) {
      tipTimer.current = setTimeout(() => {
        tipTimer.current = null;
        onTipChange?.(null);
      }, duration);
    }
  }, [onTipChange]);
  const interruptedDraftRef = useRef<{
    text: string;
    pastedTexts: Map<number, string>;
    nextPasteId: number;
    imagePaths: Map<number, string>;
    nextImageId: number;
    shellMode: boolean;
  } | null>(null);
  const [expandedIndex, setExpandedIndex] = useState(-1);

  // Todo panel state
  const [todoFocused, setTodoFocused] = useState(false);
  const [todoActiveIndex, setTodoActiveIndex] = useState(0);
  const [subAgentFocused, setSubAgentFocused] = useState(false);
  const [subAgentActiveIndex, setSubAgentActiveIndex] = useState(0);

  const appState = useAppState();
  const dispatch = useAppDispatch();
  const shellModeActive = appState.shellModeActive;
  const clipboard = useClipboard({
    active: focus && !disabled && interactionActive && !editorDialog.isOpen &&
      !statusBarDialog.isOpen && !statusDialog.isOpen && !languageDialogOpen &&
      !todoFocused && !subAgentFocused,
    owner: `${sessionId ?? ''}\0${cwd}\0${buffer.text}\0${buffer.cursorRow}:${buffer.cursorCol}`,
    onPaste: content => {
      if (content.kind === 'image') {
        const imageId = nextImageIdRef.current++;
        imagePathsRef.current.set(imageId, content.image.filePath);
        buffer.insert(formatImageRef(imageId));
        showTip(INPUT_TIPS.imagePasted);
      } else {
        const text = content.text;
        const numLines = text.split('\n').length;
        if (text.length > PASTE_THRESHOLD || numLines > PASTE_LINE_THRESHOLD) {
          const pasteId = nextPasteIdRef.current++;
          pastedTextsRef.current.set(pasteId, text);
          buffer.insert(formatPasteRef(pasteId, numLines));
        } else {
          buffer.insert(text);
        }
        showTip(INPUT_TIPS.textPasted);
      }
    },
  });
  const clipboardStatusMessage = onTipChange ? '' : clipboard.message;
  useEffect(() => {
    if (clipboard.message) showTip(clipboard.message, 5000);
  }, [clipboard.message, showTip]);

  // Use ref to always access latest shellModeActive value
  const shellModeRef = useRef(shellModeActive);
  useEffect(() => {
    shellModeRef.current = shellModeActive;
  }, [shellModeActive]);


  // Calculate cursor offset using code points (proper Unicode handling)
  const cursorOffset = useMemo(() => {
    let offset = 0;
    
    // Clamp row to valid range
    const actualRow = Math.min(buffer.cursorRow, buffer.lines.length - 1);
    
    // Add lengths of all lines before the target row
    for (let i = 0; i < actualRow; i++) {
      offset += cpLen(buffer.lines[i]) + 1; // +1 for newline
    }
    
    // Add column offset within the target row
    if (actualRow >= 0 && actualRow < buffer.lines.length) {
      offset += Math.min(buffer.cursorCol, cpLen(buffer.lines[actualRow]));
    }
    
    return offset;
  }, [buffer.cursorRow, buffer.cursorCol, buffer.lines]);

  // Argument-hint lookup (command name -> concise hint text), loaded once
  // from slashCommandService. Mirrors the same one-shot-on-mount pattern
  // used by useSlashCompletion's own command list load.
  const [commandHints, setCommandHints] = useState<Map<string, string>>(new Map());
  // Known command names — the leading "/xxx" token is only highlighted when it
  // exactly matches one of these, so typos / arbitrary "/foo" text stay plain.
  const [commandNames, setCommandNames] = useState<Set<string>>(new Set());
  useEffect(() => {
    let mounted = true;
    slashCommandService.getCommands().then((cmds) => {
      if (!mounted) return;
      const map = new Map<string, string>();
      const names = new Set<string>();
      cmds.forEach((c) => {
        names.add(c.name);
        if (c.argumentHint) map.set(c.name, c.argumentHint);
      });
      setCommandHints(map);
      setCommandNames(names);
    });
    return () => {
      mounted = false;
    };
  }, []);

  // Unified command completion hook (@ and / support)
  const {
    suggestions,
    activeIndex,
    isLoading: isCompletionLoading,
    showSuggestions,
    visibleStartIndex,
    mode: completionMode,
    navigateUp: completionNavigateUp,
    navigateDown: completionNavigateDown,
    acceptSuggestion,
    reset: resetCompletion,
  } = useCommandCompletion({
    inputText: buffer.text,
    cursorPosition: cursorOffset,
    cwd,
    enabled: focus && !disabled && interactionActive,
    mcpResources,
  });

  // Inline "ghost text" argument hint (e.g. "/goal" -> "[<objective> | clear]")
  // shown right after the cursor once a known command name has been fully
  // typed and no argument has been entered yet. Computed synchronously from
  // buffer.text (not from the debounced completion hook's showSuggestions
  // state) so it appears immediately with no timing dependency.
  const activeCommandHint = useMemo(() => {
    const match = COMMAND_ONLY_RE.exec(buffer.text);
    if (!match) return null;
    return commandHints.get(match[1]) ?? null;
  }, [buffer.text, commandHints]);

  const {
    execute: executeShellCommand,
  } = useShellCommand({
    cwd,
  });

  const {
    addCommand: addToShellHistory,
    navigateUp: shellHistoryUp,
    navigateDown: shellHistoryDown,
    resetIndex: resetShellHistoryIndex,
  } = useShellHistory({
    maxEntries: 100,
    autoSave: true,
  });

  const [visualRow, visualCol] = buffer.visualCursor;

  const runInEditorTerminal = useEditorTerminal();
  const openExternalEditor = useCallback(async () => {
    if (disabled) return;

    const tmpDir = mkdtempSync(join(tmpdir(), 'siada-edit-'));
    const filePath = join(tmpDir, 'buffer.txt');
    const currentText = buffer.text;
    
    try {
      // Give the file its own final newline so Vim's automatic end-of-line
      // does not become an extra blank prompt line on each editing round trip.
      writeFileSync(filePath, `${currentText}\n`, 'utf-8');
      
      const preferredEditor = configManager.getPreferredEditor();
      const { command, args, source } = resolveEditorCommand(preferredEditor);
      
      logger.info('[InputPromptWithWrapUseKPC] Opening external editor', {
        component: 'InputPromptWithWrapUseKPC',
        editor: preferredEditor || 'default',
        command,
        source,
      });
      
      const editorArgs = [...args, filePath];
      const result = runInEditorTerminal(() => spawnSync(command, editorArgs, {
        stdio: 'inherit',
        shell: process.platform === 'win32',
      }));
      
      if (result.error) {
        logger.error('[InputPromptWithWrapUseKPC] Editor launch failed', {
          component: 'InputPromptWithWrapUseKPC',
          error: result.error.message,
        });
        return;
      }
      
      if (result.status !== 0) {
        logger.warn('[InputPromptWithWrapUseKPC] Editor exited with non-zero status', {
          component: 'InputPromptWithWrapUseKPC',
          status: result.status,
        });
      }
      
      const newText = readFileSync(filePath, 'utf-8').replace(/\r?\n$/, '');
      buffer.setText(newText);
      
      logger.info('[InputPromptWithWrapUseKPC] Editor closed, content updated', {
        component: 'InputPromptWithWrapUseKPC',
        originalLength: currentText.length,
        newLength: newText.length,
      });
    } catch (error) {
      logger.error('[InputPromptWithWrapUseKPC] External editor error', {
        component: 'InputPromptWithWrapUseKPC',
        error: error instanceof Error ? error.message : String(error),
      });
    } finally {
      try {
        unlinkSync(filePath);
        rmdirSync(tmpDir);
      } catch (err) {
        // Ignore cleanup errors
      }
    }
  }, [buffer, disabled, runInEditorTerminal]);

  const handleSubmit = useCallback(async () => {
    const trimmed = buffer.text.trim();
    if (!trimmed || disabled) return;

    if (trimmed === '/language' || trimmed.startsWith('/language ')) {
      const value = trimmed.slice('/language'.length).trim().toLowerCase();
      if (!value) {
        buffer.clear();
        resetCompletion();
        setLanguageDialogOpen(true);
      } else if (value === 'en' || value === 'zh-cn') {
        try {
          saveUiLanguage(value === 'en' ? 'en' : 'zh-CN');
          buffer.clear();
          resetCompletion();
        } catch (error) {
          showTip(t('无法保存界面语言，请重试。', 'Could not save interface language. Please retry.'));
        }
      } else {
        showTip(t('用法：/language [en | zh-CN]', 'Usage: /language [en | zh-CN]'));
      }
      return;
    }

    if (trimmed === '/editor' || trimmed === '/edit') {
      resetCompletion();
      editorDialog.openDialog();
      return;
    }

    if (trimmed === '/status') {
      resetCompletion();
      statusDialog.openDialog();
      return;
    }

    if (trimmed === '/statusbar') {
      resetCompletion();
      statusBarDialog.openDialog();
      return;
    }

    if (trimmed === '/export' || trimmed.startsWith('/export ')) {
      const filename = trimmed.slice('/export'.length).trim();
      buffer.clear();
      onExport?.(filename);
      return;
    }

    const currentShellMode = shellModeRef.current;
    const isOneTimeCommand = trimmed.startsWith('!');
    const isShellCommand = currentShellMode || isOneTimeCommand;

    if (isShellCommand) {
      const command = isOneTimeCommand ? trimmed.slice(1).trim() : trimmed;
      
      if (!command) {
        buffer.clear();
        return;
      }

      try {
        const shellMessageId = `shell-${Date.now()}`;
        const executingMessage: Message = {
          id: shellMessageId,
          type: 'tool',
          content: `Executing: ${command}`,
          timestamp: new Date().toISOString(),
          author: 'system',
          metadata: {
            subtype: 'shell',
            shellExecution: {
              command,
              executing: true,
              stdout: '',
              stderr: '',
            },
          },
        };
        
        onAddMessage?.(executingMessage);

        const result = await executeShellCommand(command);
        
        const completedMessage: Partial<Message> = {
          content: `Executed: ${command}`,
          metadata: {
            subtype: 'shell',
            shellExecution: {
              command,
              executing: false,
              stdout: result.stdout,
              stderr: result.stderr,
              exitCode: result.exitCode,
              duration: result.duration,
              isBinary: result.isBinary,
            },
          },
        };
        
        onUpdateMessage?.(shellMessageId, completedMessage);

        addToShellHistory(command, cwd, result.exitCode ?? undefined);
        
        if (isOneTimeCommand) {
          dispatch(setShellMode(false));
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : String(error);
        
        const errorShellMessage: Message = {
          id: `shell-error-${Date.now()}`,
          type: 'tool',
          content: t(`执行失败：${command}`, `Failed: ${command}`),
          timestamp: new Date().toISOString(),
          author: 'system',
          metadata: {
            subtype: 'shell',
            shellExecution: {
              command,
              executing: false,
              stdout: '',
              stderr: '',
              error: errorMessage,
            },
          },
        };
        
        onAddMessage?.(errorShellMessage);
      }
      
      buffer.clear();
      resetShellHistoryIndex();
    } else {
      historyRef.current.unshift(trimmed);
      if (historyRef.current.length > 100) {
        historyRef.current.pop();
      }

      // Expand any large-paste placeholders back to their original text before submitting
      const expandedText = expandPasteRefs(trimmed, pastedTextsRef.current);
      pastedTextsRef.current.clear();
      nextPasteIdRef.current = 1;

      // Collect image file paths referenced in the message
      const imagePaths = collectImagePaths(trimmed, imagePathsRef.current);
      imagePathsRef.current.clear();
      nextImageIdRef.current = 1;

      onSubmit(expandedText, imagePaths.length > 0 ? imagePaths : undefined);
      buffer.clear();
      setHistoryIndex(-1);
    }
  }, [
    buffer,
    disabled,
    cwd,
    executeShellCommand,
    addToShellHistory,
    dispatch,
    onSubmit,
    onExport,
    resetShellHistoryIndex,
    editorDialog.openDialog,
    statusBarDialog.openDialog,
    statusDialog.openDialog,
    resetCompletion,
    showTip,
    loading,
    onAddMessage,
    onUpdateMessage,
  ]);


  useKeypress((key: Key) => {
    // Wheel input belongs to the viewport, not draft/history or clipboard state.
    if (key.name === 'wheelup' || key.name === 'wheeldown') return;
    // Reserve conversation scrolling before completion and history handle arrows.
    if (conversationNavigation && key.ctrl && !key.alt && !key.shift && !key.cmd &&
      (key.name === 'up' || key.name === 'down')) return;
    if (key.name === 'mousemiddle' && !isClipboardPasteKey(key)) return;
    if (key.name === 'mouseright' && (key.ctrl || key.cmd || key.alt || key.shift)) return;
    if (!['mousemove', 'mouserelease', 'selectioncopy', 'selectionclear'].includes(key.name)) clipboard.onKey(key);
    const isCtrlC = key.ctrl && key.name === 'c';
    if (!isCtrlC) clearedDraftTextRef.current = null;
    if (isCtrlC && onCtrlC && (editorDialog.isOpen || statusBarDialog.isOpen || statusDialog.isOpen || languageDialogOpen)) {
      editorDialog.closeDialog();
      statusBarDialog.closeDialog();
      statusDialog.closeDialog();
      closeLanguageDialog();
      onCtrlC('modal');
      return;
    }
    if (editorDialog.isOpen || statusBarDialog.isOpen || statusDialog.isOpen || languageDialogOpen) return;
    if (disabled || !focus || !interactionActive) return;
    if (key.name === 'mouseright') {
      if (!showSuggestions) clipboard.pasteOnRightClick();
      return;
    }
    if (key.name === 'mousemiddle') {
      clipboard.paste();
      return;
    }
    if (['mousemove', 'mouserelease', 'selectioncopy', 'selectionclear'].includes(key.name)) return;
    if (key.name !== 'backspace' && key.name !== 'delete') deleteStreak.current.count = 0;
    if (demoPresentation && onDemoFocusStatus && key.name === 'tab' &&
      buffer.text.trim() === '' && !showSuggestions) {
      onDemoFocusStatus();
      return;
    }
    if (isCtrlC && onCtrlC) {
      if (showSuggestions) {
        resetCompletion();
        onCtrlC('modal');
        return;
      }
      if (todoFocused || subAgentFocused) {
        setTodoFocused(false);
        setSubAgentFocused(false);
        onCtrlC('modal');
        return;
      }
      setTodoFocused(false);
      setSubAgentFocused(false);
      if (buffer.text.length > 0 && clearedDraftTextRef.current !== buffer.text) {
        interruptedDraftRef.current = {
          text: buffer.text, pastedTexts: new Map(pastedTextsRef.current), nextPasteId: nextPasteIdRef.current,
          imagePaths: new Map(imagePathsRef.current), nextImageId: nextImageIdRef.current, shellMode: shellModeActive,
        };
        clearedDraftTextRef.current = buffer.text;
        buffer.clear();
        setHistoryIndex(-1);
        onCtrlC('draft');
      } else {
        onCtrlC('main');
      }
      return;
    }

    // Todo / SubAgent panel keyboard routing.
    // Tab (empty input, no suggestions) cycles focus: input → todos → subAgents → input.
    if (todoItems.length > 0 || subAgentItems.length > 0) {
      if (key.name === 'tab' && buffer.text.trim() === '' && !showSuggestions) {
        if (todoFocused) {
          setTodoFocused(false);
          if (subAgentItems.length > 0) setSubAgentFocused(true);
        } else if (subAgentFocused) {
          setSubAgentFocused(false);
        } else if (todoItems.length > 0) {
          setTodoFocused(true);
        } else {
          setSubAgentFocused(true);
        }
        return;
      }
      if (todoFocused) {
        if (key.name === 'up') {
          setTodoActiveIndex(i => Math.max(0, i - 1));
          return;
        }
        if (key.name === 'down') {
          setTodoActiveIndex(i => Math.min(todoItems.length - 1, i + 1));
          return;
        }
        if (key.name === 'return' || key.name === 'enter') {
          const item = todoItems[todoActiveIndex];
          if (item) {
            setTodoFocused(false);
            onTodoSelect?.(item.content);
          }
          return;
        }
        if (key.name === 'escape') {
          setTodoFocused(false);
          return;
        }
      }
      if (subAgentFocused) {
        if (key.name === 'up') {
          setSubAgentActiveIndex(i => Math.max(0, i - 1));
          return;
        }
        if (key.name === 'down') {
          setSubAgentActiveIndex(i => Math.min(subAgentItems.length - 1, i + 1));
          return;
        }
        if (key.name === 'return' || key.name === 'enter') {
          const item = subAgentItems[subAgentActiveIndex];
          if (item) {
            setSubAgentFocused(false);
            onSubAgentSelect?.(item.id);
          }
          return;
        }
        if (key.name === 'escape') {
          setSubAgentFocused(false);
          return;
        }
      }
    }

    if (key.sequence === '!' && buffer.text.trim() === '' && !showSuggestions) {
      dispatch(toggleShellMode());
      buffer.clear();
      return;
    }

    if (key.name === 'escape') {
      if (shellModeActive) {
        dispatch(setShellMode(false));
      } else if (showSuggestions) {
        resetCompletion();
      } else if (loading) {
        // Esc while the agent is busy: interrupt the current run and immediately
        // run any queued prompts one-by-one. The backend ends the turn, flushes
        // _pending_injections into fresh turns and consumes them in order. With
        // an empty queue this is just a plain interrupt. (Ctrl+C, handled in
        // App, instead discards the queue.)
        (onFlushQueueAndRun ?? onStopExecution)?.();
      }
      return;
    }


    const trimmedInput = buffer.text.trim();
    const activeSuggestion = showSuggestions ? suggestions[activeIndex]?.value : undefined;
    if ((key.name === 'return' || key.name === 'enter') && !key.shift && !key.alt && !key.ctrl &&
      ['/language', '/status', '/statusbar', '/editor', '/edit', '/effort'].includes(trimmedInput) &&
      (!showSuggestions || !activeSuggestion || `/${activeSuggestion}` === trimmedInput)) {
      handleSubmit();
      return;
    }

    if (showSuggestions) {
      if (key.name === 'up') {
        completionNavigateUp();
        return;
      }
      if (key.name === 'down') {
        completionNavigateDown();
        return;
      }
      if (key.name === 'tab' || (key.name === 'return' && !key.shift)) {
        const completed = acceptSuggestion();
        if (completed) {
          buffer.setText(completed);
        }
        return;
      }
      if (key.name === 'right' && activeIndex >= 0) {
        setExpandedIndex(activeIndex);
        return;
      }
      if (key.name === 'left' && expandedIndex >= 0) {
        setExpandedIndex(-1);
        return;
      }
    }

    // Note: Some terminals send 'return' with shift flag, others send 'enter'
    if ((key.name === 'return' || key.name === 'enter') && (key.shift || key.alt || key.ctrl)) {
      buffer.insert('\n');
      return;
    }

    if ((key.name === 'return' || key.name === 'enter') && !key.shift) {
      handleSubmit();
      return;
    }

    // Note: Must be checked AFTER Enter handling to avoid conflicts
    if (key.ctrl && key.name === 'j') {
      buffer.insert('\n');
      return;
    }

    // ↑ with a non-empty queue and an empty input box: pull all queued prompts
    // back into the input box (merged) for editing. Tell the backend to drop those
    // pending injections so the pulled-back prompts are not also consumed
    // mid-turn / flushed as a new turn.
    if (
      key.name === 'up' &&
      !showSuggestions &&
      buffer.text.trim() === '' &&
      promptQueueStore.getLength() > 0
    ) {
      const drained = promptQueueStore.popAllEditable();
      if (drained.text) {
        buffer.setText(drained.text);
      }
      onCancelPendingQueue?.();
      return;
    }

    if (key.name === 'up' && !showSuggestions && buffer.text.length === 0 && interruptedDraftRef.current) {
      const draft = interruptedDraftRef.current;
      interruptedDraftRef.current = null;
      pastedTextsRef.current = draft.pastedTexts;
      nextPasteIdRef.current = draft.nextPasteId;
      imagePathsRef.current = draft.imagePaths;
      nextImageIdRef.current = draft.nextImageId;
      dispatch(setShellMode(draft.shellMode));
      buffer.setText(draft.text);
      setHistoryIndex(-1);
      return;
    }
    if (key.name === 'up' && !showSuggestions && visualRow === 0) {
      if (shellModeActive) {
        const cmd = shellHistoryUp();

        if (cmd !== null) {
          buffer.setText(cmd);
        }
      } else if (historyRef.current.length > 0) {
        if (historyIndex === -1) {
          setTempInput(buffer.text);
        }
        const newIndex = Math.min(historyIndex + 1, historyRef.current.length - 1);
        if (newIndex >= 0) {
          buffer.setText(historyRef.current[newIndex]);
          setHistoryIndex(newIndex);
        }
      }
      return;
    }

    if (key.name === 'down' && !showSuggestions && visualRow === buffer.visualLines.length - 1) {
      if (shellModeActive) {
        const cmd = shellHistoryDown();
        if (cmd !== null) {
          buffer.setText(cmd);
        } else {
          buffer.clear();
        }
      } else if (historyIndex > 0) {
        const newIndex = historyIndex - 1;
        buffer.setText(historyRef.current[newIndex]);
        setHistoryIndex(newIndex);
      } else if (historyIndex === 0) {
        buffer.setText(tempInput);
        setHistoryIndex(-1);
      }
      return;
    }

    // Ctrl+P / Ctrl+N: readline-style history navigation (no Kitty needed)
    if (key.ctrl && key.name === 'p' && !showSuggestions) {
      if (shellModeActive) {
        const cmd = shellHistoryUp();
        if (cmd !== null) { buffer.setText(cmd); }
      } else if (historyRef.current.length > 0) {
        if (historyIndex === -1) { setTempInput(buffer.text); }
        const newIndex = Math.min(historyIndex + 1, historyRef.current.length - 1);
        if (newIndex >= 0) { buffer.setText(historyRef.current[newIndex]); setHistoryIndex(newIndex); }
      }
      return;
    }
    if (key.ctrl && key.name === 'n' && !showSuggestions) {
      if (shellModeActive) {
        const cmd = shellHistoryDown();
        if (cmd !== null) { buffer.setText(cmd); } else { buffer.clear(); }
      } else if (historyIndex > 0) {
        const newIndex = historyIndex - 1;
        buffer.setText(historyRef.current[newIndex]);
        setHistoryIndex(newIndex);
      } else if (historyIndex === 0) {
        buffer.setText(tempInput);
        setHistoryIndex(-1);
      }
      return;
    }

    if (key.ctrl && key.name === 'w') { buffer.deleteWordLeft(); return; }
    if (key.ctrl && key.name === 'k') { buffer.killLineRight(); return; }
    if (key.ctrl && key.name === 'u') { buffer.killLineLeft(); return; }
    if (key.ctrl && key.name === 'a') { buffer.moveCursor('home'); return; }
    if (key.ctrl && key.name === 'e') { buffer.moveCursor('end'); return; }
    // Ctrl+Shift+A/E: backup bindings (work in Kitty protocol terminals)
    if (key.ctrl && key.shift && key.name === 'a') { buffer.moveCursor('home'); return; }
    if (key.ctrl && key.shift && key.name === 'e') { buffer.moveCursor('end'); return; }
    // Readline extras (no Kitty needed)
    if (key.ctrl && key.name === 'f') { buffer.moveCursor('right'); return; }
    if (key.ctrl && key.name === 'l') { buffer.moveCursor('end'); return; }
    if (key.alt && key.name === 'd') { buffer.deleteWordRight(); return; }
    if (key.ctrl && key.name === 'x') { openExternalEditor(); return; }
    if (key.ctrl && key.name === 'd') { buffer.clear(); return; }
    if (key.ctrl && key.name === 'b') {
      // Copy expanded text rather than internal paste/image placeholder tokens.
      let textToCopy = buffer.text;
      textToCopy = expandPasteRefs(textToCopy, pastedTextsRef.current);
      textToCopy = textToCopy.replace(/\[Image #(\d+)\]/g, (match, id) => imagePathsRef.current.get(Number(id)) ?? match);
      clipboard.copy(textToCopy);
      return;
    }

    // Word movement: Alt/Option+Left/Right, Ctrl+Left/Right, Meta+B/F (readline)
    if (key.name === 'left'  && (key.alt || key.ctrl)) { buffer.moveCursor('wordLeft');  return; }
    if (key.name === 'right' && (key.alt || key.ctrl)) { buffer.moveCursor('wordRight'); return; }
    if (key.alt && key.name === 'b') { buffer.moveCursor('wordLeft');  return; }
    if (key.alt && key.name === 'f') { buffer.moveCursor('wordRight'); return; }
    if (conversationNavigation && (
      ['pageup', 'pagedown', 'mouseclick', 'wheelup', 'wheeldown'].includes(key.name) ||
      (key.alt && ['up', 'down'].includes(key.name)) ||
      (key.ctrl && ['g', 'end'].includes(key.name))
    )) return;
    if (key.name === 'up'    && !showSuggestions) { buffer.moveCursor('up');    return; }
    if (key.name === 'down'  && !showSuggestions) { buffer.moveCursor('down');  return; }
    if (key.name === 'left')  { buffer.moveCursor('left');  return; }
    if (key.name === 'right') { buffer.moveCursor('right'); return; }
    if (key.name === 'backspace' || key.name === 'delete') {
      const now = Date.now();
      const streak = deleteStreak.current;
      streak.count = buffer.text && now - streak.lastAt < 900 ? streak.count + 1 : 1;
      streak.lastAt = now;
      if (streak.count === 5 && buffer.text.length >= 12 && now - streak.shownAt > 12000) {
        streak.shownAt = now;
        showTip(INPUT_TIPS.repeatedDelete, 3500);
      }
      // If cursor is immediately after a paste or image placeholder, delete the whole token
      const beforeCursor = buffer.text.slice(0, cursorOffset);
      const pasteMatch = PASTE_REF_SUFFIX_RE.exec(beforeCursor);
      if (pasteMatch) {
        buffer.backspace(pasteMatch[0].length);
        pastedTextsRef.current.delete(Number(pasteMatch[1]));
        return;
      }
      const imageMatch = IMAGE_REF_SUFFIX_RE.exec(beforeCursor);
      if (imageMatch) {
        buffer.backspace(imageMatch[0].length);
        imagePathsRef.current.delete(Number(imageMatch[1]));
        return;
      }
      buffer.backspace();
      return;
    }
    if (key.name === 'pageup')   { buffer.scroll(-5); return; }
    if (key.name === 'pagedown') { buffer.scroll(5);  return; }

    // Ctrl+V / Cmd+V: read the host clipboard with visible failure feedback.
    if (isClipboardPasteKey(key)) {
      logger.info('[InputPromptWithWrapUseKPC] Ctrl/Cmd+V detected, reading clipboard', {
        ctrl: key.ctrl,
        cmd: key.cmd,
      });
      clipboard.paste();
      return;
    }

    // Paste entire bracketed-paste sequence at once; avoids 14000+ re-renders per large paste
    if (key.name === 'paste') {
      const text = key.sequence;

      logger.info('[InputPromptWithWrapUseKPC] paste event', {
        textLength: text.length,
        isEmpty: !text,
      });

      // Empty bracketed paste = clipboard may contain an image (macOS Cmd+V with image)
      if (!text) {
        clipboard.paste();
        return;
      }

      const numLines = text.split('\n').length;
      logger.info('[InputPromptWithWrapUseKPC] Paste event received', {
        component: 'InputPromptWithWrapUseKPC',
        pasteLength: text.length,
        numLines,
      });
      if (text.length > PASTE_THRESHOLD || numLines > PASTE_LINE_THRESHOLD) {
        const pasteId = nextPasteIdRef.current++;
        pastedTextsRef.current.set(pasteId, text);
        buffer.insert(formatPasteRef(pasteId, numLines));
      } else {
        buffer.insert(text);
      }
      return;
    }

    if (key.insertable && key.sequence && !key.ctrl && !key.alt) {
      buffer.insert(key.sequence);
    }
  }, { isActive: focus && !disabled && interactionActive });


  const selectLanguage = useCallback((language: UiLanguage) => {
    try {
      saveUiLanguage(language);
      closeLanguageDialog();
    } catch (error) {
      showTip(t('无法保存界面语言，请重试。', 'Could not save interface language. Please retry.'));
    }
  }, [closeLanguageDialog, showTip]);
  const languagePanel = useMemo(() => languageDialogOpen
    ? <LanguageSelector onSelect={selectLanguage} onClose={closeLanguageDialog} />
    : null, [languageDialogOpen, selectLanguage, closeLanguageDialog, uiLanguage]);
  const demoCompletion = useMemo(() => !demoPresentation ? null : languageDialogOpen
    ? languagePanel
    : editorDialog.isOpen
    ? <EditorDialog currentEditor={editorDialog.currentEditor} onSelect={editorDialog.handleSelect}
        onCancel={editorDialog.closeDialog} />
    : statusBarDialog.isOpen
      ? <StatusBarDialog visibleItems={statusBarDialog.visibleItems} onToggle={statusBarDialog.handleToggle}
          onClose={statusBarDialog.closeDialog} />
    : statusDialog.isOpen
      ? <StatusDialog model={model} agent={agent} sessionId={sessionId} workingDir={workingDir || cwd}
          onClose={statusDialog.closeDialog} />
    : showSuggestions ? <DemoCompletionList suggestions={suggestions} activeIndex={activeIndex} width={terminalWidth} />
    : null, [demoPresentation, languageDialogOpen, languagePanel,
      uiLanguage, editorDialog.isOpen, editorDialog.currentEditor, editorDialog.handleSelect,
      editorDialog.closeDialog, statusBarDialog.isOpen, statusBarDialog.visibleItems, statusBarDialog.handleToggle,
      statusBarDialog.closeDialog, statusDialog.isOpen, statusDialog.closeDialog, model, agent, sessionId, workingDir, cwd,
      showSuggestions, suggestions, activeIndex,
      isCompletionLoading, terminalWidth, visibleStartIndex, expandedIndex]);
  useLayoutEffect(() => {
    onDemoCompletion?.(demoCompletion, editorDialog.isOpen || statusBarDialog.isOpen || statusDialog.isOpen || languageDialogOpen,
      statusDialog.isOpen ? 9 : undefined);
  }, [demoCompletion, onDemoCompletion]);
  useEffect(() => () => onDemoCompletion?.(null), [onDemoCompletion]);

  const borderColor = disabled 
    ? githubTheme.border.disabled
    : (focus ? demoPresentation && !interactionActive ? '#8aa8c8'
      : githubTheme.border.focused : githubTheme.border.default);
  
  const promptChar = shellModeActive ? '! ' : '▸ ';

  useLayoutEffect(() => {
    if (!selectionSurface) return;
    const fragments = new Map<DOMElement, { start: number; end: number }>();
    for (const [visualIndex, container] of selectionLines.current) {
      const node = container.childNodes.find(child => child.nodeName === 'ink-text') as DOMElement | undefined;
      if (!node) continue;
      const mapping = buffer.visualToLogicalMap[visualIndex];
      if (!mapping) continue;
      const [row, column] = mapping;
      const start = buffer.lines.slice(0, row).reduce((count, line) => count + line.length + 1, 0) +
        cpSlice(buffer.lines[row] ?? '', 0, column).length;
      fragments.set(node, { start, end: start + (buffer.visualLines[visualIndex]?.length ?? 0) });
    }
    selectionSurface.current.root = selectionRootOverride?.current ?? selectionRoot.current;
    selectionSurface.current.source = { text: buffer.text, fragments };
    selectionSurface.current.onUpdate?.();
  });
  useEffect(() => () => {
    if (!selectionSurface) return;
    selectionSurface.current.root = null;
    selectionSurface.current.source = undefined;
    selectionSurface.current.onUpdate?.();
  }, [selectionSurface]);

  if (disabled) {
    return (
      <Box ref={selectionRoot} flexDirection="column" flexShrink={0} opaque>
        <Box userSelect="none"><ShellModeIndicator active={shellModeActive} cwd={cwd} /></Box>
        
        <Box
          borderStyle={conversationNavigation ? 'single' : 'round'}
          borderLeft={!conversationNavigation}
          borderRight={!conversationNavigation}
          borderColor={borderColor}
          paddingX={1}
          width={terminalWidth}
          flexDirection="row"
          alignItems="flex-start"
          minHeight={3}
          flexShrink={0}
        >
          <Box userSelect="none"><Text color={githubTheme.input.prompt}>{promptChar}</Text></Box>
          <Box flexGrow={1} flexDirection="column">
            <Text color={githubTheme.text.secondary}>{disabledMessage}</Text>
          </Box>
        </Box>
      </Box>
    );
  }

  if (buffer.text.length === 0) {
    return (
      <Box ref={selectionRoot} flexDirection="column" flexShrink={0} opaque>
        <Box userSelect="none"><ShellModeIndicator active={shellModeActive} cwd={cwd} /></Box>
        
        <Box
          borderStyle={conversationNavigation ? 'single' : 'round'}
          borderLeft={!conversationNavigation}
          borderRight={!conversationNavigation}
          borderColor={borderColor}
          paddingX={1}
          width={terminalWidth}
          flexDirection="row"
          alignItems="flex-start"
          minHeight={3}
          flexShrink={0}
        >
          <Box userSelect="none"><Text color={githubTheme.input.prompt}>{promptChar}</Text></Box>
          <Box userSelect="none" flexGrow={1} flexDirection="column">
            {focus ? (
              <Text>
                {chalk.inverse(' ')}
                <Text color={githubTheme.input.placeholder} wrap={conversationNavigation ? 'truncate-end' : 'wrap'}>
                  {shellModeActive ? t('输入终端命令…', 'Enter shell command...') : placeholder}
                </Text>
              </Text>
            ) : (
              <Text color={githubTheme.input.placeholder}>
                {shellModeActive ? t('输入终端命令…', 'Enter shell command...') : placeholder}
              </Text>
            )}
          </Box>
        </Box>

        {/* Status bar — expanded 12-item display, grouped with │ dividers between groups */}
        {!editorDialog.isOpen && !statusBarDialog.isOpen && !statusDialog.isOpen && (clipboardStatusMessage || ((!showSuggestions || demoPresentation) && statusBarParts.segments.length > 0)) && (
          <Box marginTop={0} paddingLeft={1} paddingRight={1} height={1} flexShrink={0}
            overflow="hidden" flexDirection="row" justifyContent="space-between">
            <Text color={clipboardStatusMessage ? 'yellow' : undefined} wrap="truncate-end">
              {clipboardStatusMessage || statusBarParts.segments.map((seg, idx) => (
                <Text key={seg.key}>
                  {idx > 0 && (seg.group !== statusBarParts.segments[idx - 1].group ? '  │  ' : '  ')}
                  {seg.text}
                </Text>
              ))}
            </Text>
            {!clipboardStatusMessage && statusBarParts.right && (
              <Text color="cyan" dimColor>
                {statusBarParts.right}
              </Text>
            )}
          </Box>
        )}

        {/* Todo display — shown below input when todos exist */}
        {!demoPresentation && !editorDialog.isOpen && todoItems.length > 0 && (
          <Box marginTop={0}>
            <TodoDisplay
              compact={conversationNavigation}
              items={todoItems}
              activeIndex={todoFocused ? todoActiveIndex : -1}
              width={terminalWidth}
              onSelect={(idx) => {
                const item = todoItems[idx];
                if (item) { setTodoFocused(false); onTodoSelect?.(item.content); }
              }}
              onClose={() => setTodoFocused(false)}
            />
          </Box>
        )}

        {/* Sub agent display — shown below todo display when sub agents exist */}
        {!demoPresentation && !editorDialog.isOpen && subAgentItems.length > 0 && (
          <Box marginTop={0}>
            <SubAgentDisplay
              compact={conversationNavigation}
              items={subAgentItems}
              activeIndex={subAgentFocused ? subAgentActiveIndex : -1}
              width={terminalWidth}
            />
          </Box>
        )}
      </Box>
    );
  }

  const linesToRender = buffer.visibleVisualLines;
  const scrollVisualRow = buffer.scrollOffset;
  const [cursorVisualRowAbsolute, cursorVisualColAbsolute] = buffer.visualCursor;

  return (
    <Box ref={selectionRoot} flexDirection="column" flexShrink={0} opaque>
      {!editorDialog.isOpen && (
        <Box userSelect="none"><ShellModeIndicator active={shellModeActive} cwd={cwd} /></Box>
      )}

      {!editorDialog.isOpen && (
        <>
          <Box
            borderStyle={conversationNavigation ? 'single' : 'round'}
            borderLeft={!conversationNavigation}
            borderRight={!conversationNavigation}
            borderColor={borderColor}
            paddingX={1}
            width={terminalWidth}
            flexDirection="row"
            alignItems="flex-start"
            minHeight={3}
            flexShrink={0}
          >
            <Box userSelect="none"><Text color={githubTheme.input.prompt}>{promptChar}</Text></Box>
            <Box flexGrow={1} flexDirection="column">
              {linesToRender.map((lineText, visualIdxInRenderedSet) => {
                const absoluteVisualIdx = scrollVisualRow + visualIdxInRenderedSet;
                const mapEntry = buffer.visualToLogicalMap[absoluteVisualIdx];

                if (!mapEntry) {
                  return (
                    <Box key={`line-${visualIdxInRenderedSet}`} height={1}>
                      <Text color={githubTheme.input.text}>{lineText}</Text>
                    </Box>
                  );
                }

                const cursorVisualRow = cursorVisualRowAbsolute - scrollVisualRow;
                const isOnCursorLine = focus && visualIdxInRenderedSet === cursorVisualRow;

                const renderedLine: React.ReactNode[] = [];

                const lineLen = cpLen(lineText);

                // Length of the leading "/command" token — only meaningful on
                // the very first visual line, and only when the typed name is
                // an exact match of a known command (so "/goa", "/nope" etc.
                // stay plain). That token is rendered with a highlight color.
                const cmdTokenLen = (() => {
                  if (absoluteVisualIdx !== 0) return 0;
                  const token = SLASH_COMMAND_TOKEN_RE.exec(lineText)?.[0];
                  if (!token) return 0;
                  return commandNames.has(token.slice(1)) ? cpLen(token) : 0;
                })();

                // Embed the inverse block cursor into a segment when the cursor
                // falls inside it. `offset` is the segment's start column.
                const withCursor = (segment: string, offset: number): string => {
                  if (!isOnCursorLine || !focus) return segment;
                  const idx = cursorVisualColAbsolute - offset;
                  if (idx < 0 || idx >= cpLen(segment)) return segment;
                  return (
                    cpSlice(segment, 0, idx) +
                    chalk.inverse(cpSlice(segment, idx, idx + 1)) +
                    cpSlice(segment, idx + 1)
                  );
                };

                if (cmdTokenLen > 0) {
                  renderedLine.push(
                    <Text key="cmd-token" color={githubTheme.primary} bold>
                      {withCursor(cpSlice(lineText, 0, cmdTokenLen), 0)}
                    </Text>,
                  );
                  renderedLine.push(
                    <Text key={`token-0`} color={githubTheme.input.text}>
                      {withCursor(cpSlice(lineText, cmdTokenLen), cmdTokenLen)}
                    </Text>,
                  );
                } else {
                  renderedLine.push(
                    <Text key={`token-0`} color={githubTheme.input.text}>
                      {withCursor(lineText, 0)}
                    </Text>,
                  );
                }

                if (isOnCursorLine) {
                  const cursorAtEnd = cursorVisualColAbsolute === lineLen;
                  if (cursorAtEnd) {
                    renderedLine.push(
                      <Text key={`cursor-end-${cursorVisualColAbsolute}`}>
                        {focus ? chalk.inverse(' ') : ' '}
                      </Text>,
                    );
                  }

                  // Inline argument-hint "ghost text" — the expected argument
                  // format, shown right after the cursor once a known command
                  // name has been fully typed. Uses text.secondary (#8b949e)
                  // and no Ink `dimColor`: muted (#484f58) plus ANSI dim made
                  // it practically invisible on dark terminals, while
                  // secondary still reads as a hint rather than typed input.
                  if (cursorAtEnd && activeCommandHint) {
                    renderedLine.push(
                      <Text key="cmd-arg-hint" color={githubTheme.text.secondary}>
                        {activeCommandHint}
                      </Text>,
                    );
                  }
                }

                const isAtEndOfLine = cursorVisualColAbsolute === lineLen;
                const imePosition =
                  isOnCursorLine && isAtEndOfLine
                    ? cursorVisualColAbsolute + 1
                    : cursorVisualColAbsolute;

                return (
                  <Box key={`line-${visualIdxInRenderedSet}`} height={1}
                      ref={(node: DOMElement | null) => {
                        if (node) selectionLines.current.set(absoluteVisualIdx, node);
                        else selectionLines.current.delete(absoluteVisualIdx);
                      }}>
                    <CursorAwareText
                      terminalCursorFocus={focus && isOnCursorLine}
                      terminalCursorPosition={imePosition}
                    >
                      {renderedLine}
                    </CursorAwareText>
                  </Box>
                );
              })}
            </Box>
          </Box>


      </>
      )
      }

      {/* Status bar — expanded 12-item display, grouped with │ dividers between groups */}
      {!editorDialog.isOpen && !statusBarDialog.isOpen && !statusDialog.isOpen && (clipboardStatusMessage || ((!showSuggestions || demoPresentation) && statusBarParts.segments.length > 0)) && (
        <Box marginTop={0} paddingLeft={1} paddingRight={1} height={1} flexShrink={0}
          overflow="hidden" flexDirection="row" justifyContent="space-between">
          <Text color={clipboardStatusMessage ? 'yellow' : undefined} wrap="truncate-end">
            {clipboardStatusMessage || statusBarParts.segments.map((seg, idx) => (
              <Text key={seg.key}>
                {idx > 0 && (seg.group !== statusBarParts.segments[idx - 1].group ? '  │  ' : '  ')}
                {seg.text}
              </Text>
            ))}
          </Text>
          {!clipboardStatusMessage && statusBarParts.right && (
            <Text color="cyan" dimColor>
              {statusBarParts.right}
            </Text>
          )}
        </Box>
      )}

      {/* Todo display */}
      {!demoPresentation && !editorDialog.isOpen && todoItems.length > 0 && (
        <Box marginTop={0}>
          <TodoDisplay
            compact={conversationNavigation}
            items={todoItems}
            activeIndex={todoFocused ? todoActiveIndex : -1}
            width={terminalWidth}
            onSelect={(idx) => {
              const item = todoItems[idx];
              if (item) { setTodoFocused(false); onTodoSelect?.(item.content); }
            }}
            onClose={() => setTodoFocused(false)}
          />
        </Box>
      )}

      {/* Sub agent display */}
      {!demoPresentation && !editorDialog.isOpen && subAgentItems.length > 0 && (
        <Box marginTop={0}>
          <SubAgentDisplay
            compact={conversationNavigation}
            items={subAgentItems}
            activeIndex={subAgentFocused ? subAgentActiveIndex : -1}
            width={terminalWidth}
          />
        </Box>
      )}

      {/* Autocomplete suggestions */}
      {!demoPresentation && !editorDialog.isOpen && showSuggestions && (
        <Box marginTop={0}>
          <SuggestionsDisplay
            suggestions={suggestions}
            activeIndex={activeIndex}
            isLoading={isCompletionLoading}
            maxHeight={demoPresentation ? 6 : 8}
            width={demoPresentation ? Math.min(terminalWidth, 58) : terminalWidth}
            scrollOffset={visibleStartIndex}
            expandedIndex={expandedIndex}
            dualColumnLayout={completionMode === CompletionMode.SLASH || completionMode === CompletionMode.PROMPT}
          />
        </Box>
      )}

      {/* Editor Dialog */}
      {!demoPresentation && languageDialogOpen && (
        <LanguageSelector onSelect={selectLanguage} onClose={closeLanguageDialog} />
      )}
      {!demoPresentation && editorDialog.isOpen && (
        <Box marginTop={1}>
          <EditorDialog
            currentEditor={editorDialog.currentEditor}
            onSelect={editorDialog.handleSelect}
            onCancel={editorDialog.closeDialog}
          />
        </Box>
      )}

      {/* StatusBar Dialog */}
      {!demoPresentation && statusBarDialog.isOpen && (
        <Box marginTop={1}>
          <StatusBarDialog
            visibleItems={statusBarDialog.visibleItems}
            onToggle={statusBarDialog.handleToggle}
            onClose={statusBarDialog.closeDialog}
          />
        </Box>
      )}

      {/* Status Dialog */}
      {!demoPresentation && statusDialog.isOpen && (
        <Box marginTop={1}>
          <StatusDialog
            model={model}
            agent={agent}
            sessionId={sessionId}
            workingDir={workingDir || cwd}
            onClose={statusDialog.closeDialog}
          />
        </Box>
      )}

    </Box>
  );
});
