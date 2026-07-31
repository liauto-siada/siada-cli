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
 */

import React, { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { Box, Text, useStdout } from '@jrichman/ink';
import { githubTheme } from './theme.js';
import chalk from 'chalk';
import { useCommandCompletion } from '../../hooks/useCommandCompletion.js';
import { SuggestionsDisplay } from '../AutoComplete/SuggestionsDisplay.js';
import { CompletionMode } from '../../types/autocomplete.js';
import { useAppState, useAppDispatch } from '../../store/context.js';
import { toggleShellMode, setShellMode } from '../../store/reducers.js';
import { ShellModeIndicator } from '../Shell/ShellModeIndicator.js';
import { useShellCommand } from '../../hooks/useShellCommand.js';
import { useShellHistory } from '../../hooks/useShellHistory.js';
import { useEnhancedTextBuffer } from './TextBuffer.js';
import { EditorDialog, useEditorDialog } from '../EditorDialog/index.js';
import { StatusBarDialog, useStatusBarDialog } from '../StatusBarDialog/index.js';
import { resolveEditorCommand } from '../../utils/editor.js';
import { configManager } from '../../utils/config.js';
import { writeFileSync, unlinkSync, mkdtempSync, readFileSync, rmdirSync } from 'fs';
import { join } from 'path';
import { tmpdir, homedir } from 'os';
import { spawnSync, execSync } from 'child_process';
import { logger } from '../../utils/logger.js';
import { Message } from '../../types/index.js';
import { useKeypress, type Key } from '../../hooks/useKeypress.js';
import { cpLen, cpSlice } from './textUtils.js';
import { INFORMATIVE_TIPS } from '../../constants/phrases.js';
import { getImageFromClipboard, getTextFromClipboard, copyTextToClipboard } from '../../utils/clipboard.js';
import { promptQueueStore } from '../../store/promptQueueStore.js';
import { TodoDisplay } from '../Todo/TodoDisplay.js';

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
  onSubmit: (value: string, imagePaths?: string[]) => void;
  onAddMessage?: (message: Message) => void;
  onUpdateMessage?: (id: string, updates: Partial<Message>) => void;
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
  quotaUsage?: string | null;
  todoItems?: import('../../hooks/useAcp/types.js').TodoItem[];
  onTodoSelect?: (content: string) => void;
  cacheStatus?: import('../../hooks/useAcp/types.js').CacheStatusData | null;
  workingDir?: string;
}

export const InputPromptWithWrapUseKPC: React.FC<InputPromptWithWrapUseKPCProps> = React.memo(({
  onSubmit,
  onAddMessage,
  onUpdateMessage,
  placeholder = 'Type your message, /command, or @path/to/file ...',
  disabled = false,
  disabledMessage = 'Waiting for response...',
  focus = true,
  maxLines = 20,
  width,
  cwd = process.cwd(),
  mcpResources = [],
  loading = false,
  onStopExecution,
  onFlushQueueAndRun,
  onCancelPendingQueue,
  tokenUsage,

  model,
  quotaUsage = null,
  todoItems = [],
  onTodoSelect,
  cacheStatus = null,
  workingDir,
}) => {
  const CursorAwareText = Text as React.FC<React.ComponentProps<typeof Text> & {
    terminalCursorFocus?: boolean;
    terminalCursorPosition?: number;
  }>;
  const { stdout } = useStdout();
  const terminalWidth = width ?? stdout?.columns ?? 80;

  const randomTip = useMemo(
    () => INFORMATIVE_TIPS[Math.floor(Math.random() * INFORMATIVE_TIPS.length)],
    [],
  );

  const editorDialog = useEditorDialog();
  const statusBarDialog = useStatusBarDialog();

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

  // 构建可见的状态栏项列表——保持原本白色单色，按逻辑分组用 │ 分割线区分，
  // 组内仍用双空格连接。分组：① model/balance ② 5 项成本 ③ hit_rate/cost_time ④ git/workspace
  //
  // 3 档自适应伸缩：宽度不够时按优先级逐组丢弃（① ④ 优先保留）：
  //   档1（完整）：全部分组
  //   档2：丢弃 ② 5 项成本明细 (in/out/cw/cr/cost)
  //   档3：再丢弃 ③ hit_rate/cost_time
  const STATUS_BAR_COLOR = 'white';
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
    const parts: { key: string; text: string; group: number }[] = [];
    const visibleKeys = statusBarDialog.visibleItems;
    const cs = cacheStatus;
    const tu = tokenUsage;

    const addIfVisible = (key: string, text: string | null, group: number) => {
      if (visibleKeys.includes(key) && text !== null) {
        parts.push({ key, text, group });
      }
    };

    addIfVisible('model', model ? `${model}` : null, 1);
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
  }, [model, quotaUsage, cacheStatus, tokenUsage, gitBranch, workingDir, statusBarDialog.visibleItems, terminalWidth]);

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
  
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [tempInput, setTempInput] = useState('');
  const historyRef = useRef<string[]>([]);
  // Stores original text for large paste placeholders: id → full text
  const pastedTextsRef = useRef<Map<number, string>>(new Map());
  const nextPasteIdRef = useRef(1);
  // Stores temp image file paths for image paste placeholders: id → filePath
  const imagePathsRef = useRef<Map<number, string>>(new Map());
  const nextImageIdRef = useRef(1);
  const [expandedIndex, setExpandedIndex] = useState(-1);

  // Todo panel state
  const [todoFocused, setTodoFocused] = useState(false);
  const [todoActiveIndex, setTodoActiveIndex] = useState(0);

  const appState = useAppState();
  const dispatch = useAppDispatch();
  const shellModeActive = appState.shellModeActive;

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
    enabled: focus && !disabled,
    mcpResources,
  });

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

  const openExternalEditor = useCallback(async () => {
    if (disabled) return;

    const tmpDir = mkdtempSync(join(tmpdir(), 'siada-edit-'));
    const filePath = join(tmpDir, 'buffer.txt');
    const currentText = buffer.text;
    
    try {
      writeFileSync(filePath, currentText, 'utf-8');
      
      const preferredEditor = configManager.getPreferredEditor();
      const { command, args, source } = resolveEditorCommand(preferredEditor);
      
      logger.info('[InputPromptWithWrapUseKPC] Opening external editor', {
        component: 'InputPromptWithWrapUseKPC',
        editor: preferredEditor || 'default',
        command,
        source,
      });
      
      const editorArgs = [...args, filePath];
      const result = spawnSync(command, editorArgs, {
        stdio: 'inherit',
        shell: process.platform === 'win32',
      });
      
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
      
      const newText = readFileSync(filePath, 'utf-8');
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
  }, [buffer, disabled]);

  const handleSubmit = useCallback(async () => {
    const trimmed = buffer.text.trim();
    if (!trimmed || disabled) return;

    if (trimmed === '/editor' || trimmed === '/edit') {
      editorDialog.openDialog();
      return;
    }

    if (trimmed === '/statusbar') {
      statusBarDialog.openDialog();
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
          content: `Failed: ${command}`,
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
    resetShellHistoryIndex,
    editorDialog.openDialog,
    statusBarDialog.openDialog,
    loading,
    onAddMessage,
    onUpdateMessage,
  ]);


  useKeypress((key: Key) => {
    if (editorDialog.isOpen || statusBarDialog.isOpen) return;
    if (disabled || !focus) return;

    // Todo panel keyboard routing
    if (todoItems.length > 0) {
      // Tab with empty input: toggle todo focus
      if (key.name === 'tab' && buffer.text.trim() === '' && !showSuggestions) {
        setTodoFocused(f => !f);
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
    // back into the input box (merged) for editing — mirrors Claude Code's
    // "press up to edit queued messages". Also tell the backend to drop those
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
      const textToCopy = buffer.text;
      if (textToCopy) {
        void copyTextToClipboard(textToCopy);
      }
      return;
    }

    // Word movement: Alt/Option+Left/Right, Ctrl+Left/Right, Meta+B/F (readline)
    if (key.name === 'left'  && (key.alt || key.ctrl)) { buffer.moveCursor('wordLeft');  return; }
    if (key.name === 'right' && (key.alt || key.ctrl)) { buffer.moveCursor('wordRight'); return; }
    if (key.alt && key.name === 'b') { buffer.moveCursor('wordLeft');  return; }
    if (key.alt && key.name === 'f') { buffer.moveCursor('wordRight'); return; }
    if (key.name === 'up'    && !showSuggestions) { buffer.moveCursor('up');    return; }
    if (key.name === 'down'  && !showSuggestions) { buffer.moveCursor('down');  return; }
    if (key.name === 'left')  { buffer.moveCursor('left');  return; }
    if (key.name === 'right') { buffer.moveCursor('right'); return; }
    if (key.name === 'backspace' || key.name === 'delete') {
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

    // Ctrl+V / Cmd+V: explicitly read from OS clipboard (supports image paste)
    if ((key.ctrl || key.cmd) && key.name === 'v') {
      logger.info('[InputPromptWithWrapUseKPC] Ctrl/Cmd+V detected, reading clipboard', {
        ctrl: key.ctrl,
        cmd: key.cmd,
      });
      void (async () => {
        try {
          const image = await getImageFromClipboard();
          logger.info('[InputPromptWithWrapUseKPC] getImageFromClipboard result', {
            hasImage: !!image,
            filePath: image?.filePath,
            mediaType: image?.mediaType,
          });
          if (image) {
            const imageId = nextImageIdRef.current++;
            imagePathsRef.current.set(imageId, image.filePath);
            buffer.insert(formatImageRef(imageId));
            return;
          }
          // No image — fall back to reading text from clipboard
          const text = await getTextFromClipboard();
          logger.info('[InputPromptWithWrapUseKPC] getTextFromClipboard result', { length: text?.length ?? 0 });
          if (text) {
            const numLines = text.split('\n').length;
            if (text.length > PASTE_THRESHOLD || numLines > PASTE_LINE_THRESHOLD) {
              const pasteId = nextPasteIdRef.current++;
              pastedTextsRef.current.set(pasteId, text);
              buffer.insert(formatPasteRef(pasteId, numLines));
            } else {
              buffer.insert(text);
            }
          }
        } catch (err) {
          logger.error('[InputPromptWithWrapUseKPC] clipboard read error', String(err));
        }
      })();
      return;
    }

    // Paste entire bracketed-paste sequence at once; avoids 14000+ re-renders per large paste
    if (key.name === 'paste') {
      const text = key.sequence;

      logger.info('[InputPromptWithWrapUseKPC] paste event', {
        textLength: text.length,
        isEmpty: !text,
        preview: text.slice(0, 60),
      });

      // Empty bracketed paste = clipboard may contain an image (macOS Cmd+V with image)
      if (!text) {
        void (async () => {
          try {
            const image = await getImageFromClipboard();
            logger.info('[InputPromptWithWrapUseKPC] empty-paste getImageFromClipboard result', {
              hasImage: !!image,
              filePath: image?.filePath,
              mediaType: image?.mediaType,
            });
            if (image) {
              const imageId = nextImageIdRef.current++;
              imagePathsRef.current.set(imageId, image.filePath);
              buffer.insert(formatImageRef(imageId));
            }
          } catch (err) {
            logger.error('[InputPromptWithWrapUseKPC] empty-paste getImageFromClipboard error', String(err));
          }
        })();
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
  }, { isActive: focus && !disabled });


  const borderColor = disabled 
    ? githubTheme.border.disabled
    : (focus ? githubTheme.border.focused : githubTheme.border.default);
  
  const promptChar = shellModeActive ? '! ' : '▸ ';

  if (disabled) {
    return (
      <Box flexDirection="column">
        <ShellModeIndicator active={shellModeActive} cwd={cwd} />
        
        <Box
          borderStyle="round"
          borderColor={borderColor}
          paddingX={1}
          width={terminalWidth}
          flexDirection="row"
          alignItems="flex-start"
          minHeight={3}
        >
          <Text color={githubTheme.input.prompt}>{promptChar}</Text>
          <Box flexGrow={1} flexDirection="column">
            <Text color={githubTheme.text.secondary}>{disabledMessage}</Text>
          </Box>
        </Box>
      </Box>
    );
  }

  if (buffer.text.length === 0) {
    return (
      <Box flexDirection="column">
        <ShellModeIndicator active={shellModeActive} cwd={cwd} />
        
        <Box
          borderStyle="round"
          borderColor={borderColor}
          paddingX={1}
          width={terminalWidth}
          flexDirection="row"
          alignItems="flex-start"
          minHeight={3}
        >
          <Text color={githubTheme.input.prompt}>{promptChar}</Text>
          <Box flexGrow={1} flexDirection="column">
            {focus ? (
              <Text>
                {chalk.inverse(' ')}
                <Text color={githubTheme.input.placeholder}>
                  {shellModeActive ? 'Enter shell command...' : placeholder}
                </Text>
              </Text>
            ) : (
              <Text color={githubTheme.input.placeholder}>
                {shellModeActive ? 'Enter shell command...' : placeholder}
              </Text>
            )}
          </Box>
        </Box>

        {/* Status bar — expanded 12-item display, grouped with │ dividers between groups */}
        {!editorDialog.isOpen && !statusBarDialog.isOpen && !showSuggestions && statusBarParts.segments.length > 0 && (
          <Box marginTop={0} paddingLeft={1} paddingRight={1} flexDirection="row" justifyContent="space-between">
            <Text>
              {statusBarParts.segments.map((seg, idx) => (
                <Text key={seg.key} color={STATUS_BAR_COLOR}>
                  {idx > 0 && (seg.group !== statusBarParts.segments[idx - 1].group ? '  │  ' : '  ')}
                  {seg.text}
                </Text>
              ))}
            </Text>
            {statusBarParts.right && (
              <Text color="cyan" dimColor>
                {statusBarParts.right}
              </Text>
            )}
          </Box>
        )}

        {/* Todo display — shown below input when todos exist */}
        {!editorDialog.isOpen && todoItems.length > 0 && (
          <Box marginTop={0}>
            <TodoDisplay
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
      </Box>
    );
  }

  const linesToRender = buffer.visibleVisualLines;
  const scrollVisualRow = buffer.scrollOffset;
  const [cursorVisualRowAbsolute, cursorVisualColAbsolute] = buffer.visualCursor;

  return (
    <Box flexDirection="column">
      {!editorDialog.isOpen && (
        <ShellModeIndicator active={shellModeActive} cwd={cwd} />
      )}

      {!editorDialog.isOpen && (
        <>
          <Box
            borderStyle="round"
            borderColor={borderColor}
            paddingX={1}
            width={terminalWidth}
            flexDirection="row"
            alignItems="flex-start"
            minHeight={3}
          >
            <Text color={githubTheme.input.prompt}>{promptChar}</Text>
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

                if (isOnCursorLine) {
                  const relativeVisualColForHighlight = cursorVisualColAbsolute;
                  const segStart = 0;
                  const segEnd = lineLen;
                  let display = lineText;

                  if (
                    relativeVisualColForHighlight >= segStart &&
                    relativeVisualColForHighlight < segEnd
                  ) {
                    const charToHighlight = cpSlice(
                      display,
                      relativeVisualColForHighlight - segStart,
                      relativeVisualColForHighlight - segStart + 1,
                    );
                    const highlighted = focus
                      ? chalk.inverse(charToHighlight)
                      : charToHighlight;
                    display =
                      cpSlice(display, 0, relativeVisualColForHighlight - segStart) +
                      highlighted +
                      cpSlice(
                        display,
                        relativeVisualColForHighlight - segStart + 1,
                      );
                  }

                  renderedLine.push(
                    <Text key={`token-0`} color={githubTheme.input.text}>
                      {display}
                    </Text>,
                  );

                  const isAtEndOfLine = cursorVisualColAbsolute === lineLen;
                  if (isAtEndOfLine) {
                    renderedLine.push(
                      <Text key={`cursor-end-${cursorVisualColAbsolute}`}>
                        {focus ? chalk.inverse(' ') : ' '}
                      </Text>,
                    );
                  }
                } else {
                  renderedLine.push(
                    <Text key={`token-0`} color={githubTheme.input.text}>
                      {lineText}
                    </Text>,
                  );
                }

                const isAtEndOfLine = cursorVisualColAbsolute === lineLen;
                const imePosition =
                  isOnCursorLine && isAtEndOfLine
                    ? cursorVisualColAbsolute + 1
                    : cursorVisualColAbsolute;

                return (
                  <Box key={`line-${visualIdxInRenderedSet}`} height={1}>
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
      {!editorDialog.isOpen && !statusBarDialog.isOpen && !showSuggestions && statusBarParts.segments.length > 0 && (
        <Box marginTop={0} paddingLeft={1} paddingRight={1} flexDirection="row" justifyContent="space-between">
          <Text>
            {statusBarParts.segments.map((seg, idx) => (
              <Text key={seg.key} color={STATUS_BAR_COLOR}>
                {idx > 0 && (seg.group !== statusBarParts.segments[idx - 1].group ? '  │  ' : '  ')}
                {seg.text}
              </Text>
            ))}
          </Text>
          {statusBarParts.right && (
            <Text color="cyan" dimColor>
              {statusBarParts.right}
            </Text>
          )}
        </Box>
      )}

      {/* Todo display */}
      {!editorDialog.isOpen && todoItems.length > 0 && (
        <Box marginTop={0}>
          <TodoDisplay
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

      {/* Autocomplete suggestions */}
      {!editorDialog.isOpen && showSuggestions && (
        <Box marginTop={0}>
          <SuggestionsDisplay
            suggestions={suggestions}
            activeIndex={activeIndex}
            isLoading={isCompletionLoading}
            maxHeight={8}
            width={terminalWidth}
            scrollOffset={visibleStartIndex}
            expandedIndex={expandedIndex}
            dualColumnLayout={completionMode === CompletionMode.SLASH || completionMode === CompletionMode.PROMPT}
          />
        </Box>
      )}

      {/* Editor Dialog */}
      {editorDialog.isOpen && (
        <Box marginTop={1}>
          <EditorDialog
            currentEditor={editorDialog.currentEditor}
            onSelect={editorDialog.handleSelect}
            onCancel={editorDialog.closeDialog}
          />
        </Box>
      )}

      {/* StatusBar Dialog */}
      {statusBarDialog.isOpen && (
        <Box marginTop={1}>
          <StatusBarDialog
            visibleItems={statusBarDialog.visibleItems}
            onToggle={statusBarDialog.handleToggle}
            onClose={statusBarDialog.closeDialog}
          />
        </Box>
      )}

    </Box>
  );
});
