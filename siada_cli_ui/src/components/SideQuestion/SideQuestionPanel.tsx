import React, { useState, useEffect, useCallback } from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { Box, Text, useStdout } from '@jrichman/ink';
import Spinner from 'ink-spinner';
import { spawn } from 'node:child_process';
import { useKeypress } from '../../hooks/useKeypress.js';
import { MarkdownText } from '../common/MarkdownText.js';
import { colors } from '../../utils/colors.js';
import { Scrollable } from '../common/Scrollable.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { useMouseTracking } from '../../hooks/useMouseTracking.js';

export interface SideQuestionItem {
  id:       string;
  question: string;
  answer:   string | null;  // null while awaiting backend response
}

export interface SideQuestionPanelProps {
  items:    SideQuestionItem[];
  /**
   * Esc handler — hides the panel without clearing the history.
   * The next /btw will reopen the panel and show all preserved items again.
   */
  onHide:   () => void;
  onRemove: (id: string) => void;
  /** 'x' shortcut — keeps only the currently focused (newest) item. */
  onClearHistory?: () => void;
  onFork?:  (item: SideQuestionItem) => void;
  /** Total rendered rows, including the header and footer. */
  height?: number;
}

export const SideQuestionPanel: React.FC<SideQuestionPanelProps> = ({
  items,
  onHide,
  onRemove,
  onClearHistory,
  onFork,
  height: availableHeight,
}) => {
  const { stdout } = useStdout();
  const { rows } = useTerminalSize();
  const height = Math.max(3, availableHeight ?? Math.min(17, Math.floor(rows / 2)));
  const spacing = height >= 6 ? 1 : 0;
  useMouseTracking(true);
  // The newest item (last) is always the focused / highlighted one.
  // Older items are rendered as collapsed history entries (title only).
  const activeIndex = items.length - 1;
  // Transient flash shown for 3s after the user presses 'c' to copy the
  // answer to the clipboard. While true the footer renders a green
  // "Copied to clipboard" badge instead of the regular shortcut hint.
  const [copiedFlash, setCopiedFlash] = useState(false);

  // Auto-clear the copied-flash 3 seconds after it was triggered.
  useEffect(() => {
    if (!copiedFlash) return;
    const timer = setTimeout(() => setCopiedFlash(false), 3000);
    return () => clearTimeout(timer);
  }, [copiedFlash]);


  const activeItem = items[activeIndex];
  const isAnswering = activeItem?.answer === null;

  const handleKeypress = useCallback((key: any) => {
    // Esc / Ctrl+C / Ctrl+D: hide the panel without clearing history.
    // The next /btw will reopen the panel with all preserved items.
    if (
      key.name === 'escape' ||
      (key.ctrl && (key.name === 'c' || key.name === 'd'))
    ) {
      onHide();
      return;
    }

    // 'x': keep only the focused (newest) item, drop older history.
    // The panel itself stays open.
    if (key.name === 'x' && !key.ctrl && !key.meta) {
      onClearHistory?.();
      return;
    }


    // Operations only allowed once the active answer is complete
    if (!isAnswering && activeItem) {
      // Copy to clipboard (macOS pbcopy; silently no-op on other platforms).
      // We always trigger the green "Copied to clipboard" flash so the user
      // gets visual confirmation, even if pbcopy is unavailable downstream.
      if (key.name === 'c' && !key.ctrl && !key.meta) {
        try {
          const proc = spawn('pbcopy');
          proc.on('error', () => { /* tool unavailable */ });
          proc.stdin.write(activeItem.answer ?? '');
          proc.stdin.end();
        } catch {
          /* ignore */
        }
        setCopiedFlash(true);
        return;
      }

    }
  }, [activeItem, isAnswering, onHide, onClearHistory]);

  // The panel only mounts while it is visible (controlled by the parent),
  // so it can unconditionally own keyboard input here. Esc fires onHide
  // which unmounts this component and re-enables the main input box.
  useKeypress(handleKeypress, { isActive: true });


  if (items.length === 0 || !activeItem) return null;

  return (
    // paddingLeft=1 aligns /btw with the ThinkingIndicator spinner
    <Box flexDirection="column" paddingLeft={1} paddingRight={1} paddingTop={spacing}
      height={height} flexShrink={0} overflowY="hidden">
      <Box height={1} flexShrink={0} overflowX="hidden">
        <Text color={colors.secondary} bold>/btw </Text>
        <Text wrap="truncate-end">{activeItem.question.replace(/\s+/g, ' ')}</Text>
      </Box>
      <Box height={spacing} flexShrink={0} />
      <Scrollable key={activeItem.id} height={height - 2 - 3 * spacing} hasFocus scrollToBottom={false}>
      {/* History list — only the newest item is rendered with full body;
          older /btw queries are collapsed to question-title rows. */}
      {items.map((item, index) => {
        const isCurrentActive = index === activeIndex;
        const isAnsweringItem = item.answer === null;

        if (!isCurrentActive) {
          // Collapsed history row — title only, dimmed.
          return (
            <Box key={item.id} height={1} flexShrink={0} overflowX="hidden">
              <Text color={colors.content.secondary} bold>/btw </Text>
              <Text color={colors.content.secondary} wrap="truncate-end">{item.question.replace(/\s+/g, ' ')}</Text>
            </Box>
          );
        }

        // Active (newest) item — full body or answering spinner.
        return (
          <Box key={item.id} flexDirection="column" flexShrink={0} marginTop={index > 0 ? 1 : 0}>
            {/* Body: answering spinner or markdown answer */}
            <Box marginLeft={2} flexDirection="column" flexShrink={0}>
              {isAnsweringItem ? (
                <Box>
                  <Text color={colors.secondary}><Spinner type="dots" /></Text>
                  <Text color={colors.secondary}> Answering...</Text>
                </Box>
              ) : (
                <MarkdownText content={item.answer ?? ''}
                  availableWidth={Math.max((stdout.columns || 80) - 5, 1)} />
              )}
            </Box>
          </Box>
        );
      })}
      </Scrollable>

      {/* Footer hint — panel is always interactive while mounted.
          When the user just pressed 'c' to copy, swap the regular
          shortcut hint for a green "Copied to clipboard" badge for 3s. */}
      <Box marginTop={spacing} height={1} flexShrink={0} overflowX="hidden">
        {copiedFlash ? (
          <Text color={colors.content.secondary} wrap="truncate-end">
            {PANEL_TIPS.sideQuestionCopiedPrefix}<Text color={colors.success}>{PANEL_TIPS.sideQuestionCopied}</Text>{PANEL_TIPS.sideQuestionCopiedSuffix}
          </Text>
        ) : (
          <Text color={colors.content.secondary} wrap="truncate-end">
            {isAnswering
              ? PANEL_TIPS.sideQuestionBusy
              : PANEL_TIPS.sideQuestion}
          </Text>
        )}
      </Box>


    </Box>
  );
};
