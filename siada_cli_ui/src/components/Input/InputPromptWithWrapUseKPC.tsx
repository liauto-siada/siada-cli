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
 *   Ctrl+W         Delete word left
 *   Ctrl+K / U     Kill to line end / start
 *   Ctrl+X         Open buffer in external editor
 *   Alt+Left/Right Word-left / word-right
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
import { resolveEditorCommand } from '../../utils/editor.js';
import { configManager } from '../../utils/config.js';
import { writeFileSync, unlinkSync, mkdtempSync, readFileSync, rmdirSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { spawnSync } from 'child_process';
import { logger } from '../../utils/logger.js';
import { Message } from '../../types/index.js';
import { useKeypress, type Key } from '../../hooks/useKeypress.js';
import { cpLen, cpSlice } from './textUtils.js';
import { INFORMATIVE_TIPS } from '../../constants/phrases.js';

export interface InputPromptWithWrapUseKPCProps {
  onSubmit: (value: string) => void;
  onAddMessage?: (message: Message) => void;
  onUpdateMessage?: (id: string, updates: Partial<Message>) => void;
  placeholder?: string;
  disabled?: boolean;
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
  tokenUsage?: { // Token usage information
    contextSize: number;
    contextMax: number;
    message: string;
  };
}

export const InputPromptWithWrapUseKPC: React.FC<InputPromptWithWrapUseKPCProps> = React.memo(({
  onSubmit,
  onAddMessage,
  onUpdateMessage,
  placeholder = 'Type your message, /command, or @path/to/file ...',
  disabled = false,
  focus = true,
  maxLines = 20,
  width,
  cwd = process.cwd(),
  mcpResources = [],
  loading = false,
  onStopExecution,
  tokenUsage,
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
  const [expandedIndex, setExpandedIndex] = useState(-1);
  const [submitBlocked, setSubmitBlocked] = useState(false);

  const appState = useAppState();
  const dispatch = useAppDispatch();
  const shellModeActive = appState.shellModeActive;

  const editorDialog = useEditorDialog();
  
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

    if (loading) {
      setSubmitBlocked(true);
      setTimeout(() => setSubmitBlocked(false), 2000);
      return;
    }

    if (trimmed === '/editor' || trimmed === '/edit') {
      editorDialog.openDialog();
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
      
      onSubmit(trimmed);
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
    loading,
    onAddMessage,
    onUpdateMessage,
  ]);


  useKeypress((key: Key) => {
    if (editorDialog.isOpen) return;
    if (disabled || !focus) return;

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
      } else if (loading && onStopExecution) {
        onStopExecution();
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
      if (buffer.lines.length < maxLines) {
        buffer.insert('\n');
      }
      return;
    }

    if ((key.name === 'return' || key.name === 'enter') && !key.shift) {
      handleSubmit();
      return;
    }

    // Note: Must be checked AFTER Enter handling to avoid conflicts
    if (key.ctrl && key.name === 'j') {
      if (buffer.lines.length < maxLines) {
        buffer.insert('\n');
      }
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

    if (key.ctrl && key.name === 'w') { buffer.deleteWordLeft(); return; }
    if (key.ctrl && key.name === 'k') { buffer.killLineRight(); return; }
    if (key.ctrl && key.name === 'u') { buffer.killLineLeft(); return; }
    if (key.ctrl && key.name === 'a') { buffer.moveCursor('home'); return; }
    if (key.ctrl && key.name === 'e') { buffer.moveCursor('end'); return; }
    if (key.ctrl && key.name === 'x') { openExternalEditor(); return; }
    if (key.ctrl && key.name === 'd') { buffer.clear(); return; }

    if (key.name === 'left' && key.alt)  { buffer.moveCursor('wordLeft');  return; }
    if (key.name === 'right' && key.alt) { buffer.moveCursor('wordRight'); return; }
    if (key.name === 'up'    && !showSuggestions) { buffer.moveCursor('up');    return; }
    if (key.name === 'down'  && !showSuggestions) { buffer.moveCursor('down');  return; }
    if (key.name === 'left')  { buffer.moveCursor('left');  return; }
    if (key.name === 'right') { buffer.moveCursor('right'); return; }
    if (key.name === 'backspace' || key.name === 'delete') { buffer.backspace(); return; }
    if (key.name === 'pageup')   { buffer.scroll(-5); return; }
    if (key.name === 'pagedown') { buffer.scroll(5);  return; }

    // Paste entire bracketed-paste sequence at once; avoids 14000+ re-renders per large paste
    if (key.name === 'paste' && key.sequence) {
      logger.info('[InputPromptWithWrapUseKPC] Paste event received', {
        component: 'InputPromptWithWrapUseKPC',
        pasteLength: key.sequence.length,
      });
      buffer.insert(key.sequence);
      return;
    }

    if (key.insertable && key.sequence && !key.ctrl && !key.alt) {
      buffer.insert(key.sequence);
    }
  }, { isActive: focus && !disabled });


  const borderColor = submitBlocked 
    ? 'red' 
    : disabled 
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
            <Text color={githubTheme.text.secondary}>Waiting for response...</Text>
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

        {/* Token usage information */}
        {!editorDialog.isOpen && !showSuggestions && (
          <Box marginTop={0} paddingLeft={1} paddingRight={1} flexDirection="row" justifyContent="space-between">
            <Text color="gray" dimColor>
              {randomTip}
            </Text>
            {tokenUsage && (
              <Text color="cyan" dimColor>
                {tokenUsage.message}
              </Text>
            )}
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

      {/* Warning message when submit is blocked */}
      {submitBlocked && (
        <Box marginTop={0} paddingLeft={1}>
          <Text color="red">
            ⚠ Agent is still responding. Press Ctrl+C to stop, then submit your message.
          </Text>
        </Box>
      )}
      </>
      )
      }

      {/* Token usage information */}
      {!editorDialog.isOpen && !showSuggestions && (
        <Box marginTop={0} paddingLeft={1} paddingRight={1} flexDirection="row" justifyContent="space-between">
          <Text color="gray" dimColor>
            {randomTip}
          </Text>
          {tokenUsage && (
            <Text color="cyan" dimColor>
              {tokenUsage.message}
            </Text>
          )}
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

    </Box>
  );
});
