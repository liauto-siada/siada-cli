import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { Box, Text } from '@jrichman/ink';
import Spinner from 'ink-spinner';
import { spawn } from 'node:child_process';
import { useKeypress } from '../../hooks/useKeypress.js';
import { MarkdownText } from '../common/MarkdownText.js';

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
}

const VIEWPORT_LINES = 12;

export const SideQuestionPanel: React.FC<SideQuestionPanelProps> = ({
  items,
  onHide,
  onRemove,
  onClearHistory,
  onFork,
}) => {

  // The newest item (last) is always the focused / highlighted one.
  // Older items are rendered as collapsed history entries (title only).
  const activeIndex = items.length - 1;
  const [scrollOffset, setScrollOffset] = useState(0);
  // Transient flash shown for 3s after the user presses 'c' to copy the
  // answer to the clipboard. While true the footer renders a green
  // "Copied to clipboard" badge instead of the regular shortcut hint.
  const [copiedFlash, setCopiedFlash] = useState(false);

  // Reset scroll when a new item is appended.
  useEffect(() => {
    setScrollOffset(0);
  }, [items.length]);

  // Auto-clear the copied-flash 3 seconds after it was triggered.
  useEffect(() => {
    if (!copiedFlash) return;
    const timer = setTimeout(() => setCopiedFlash(false), 3000);
    return () => clearTimeout(timer);
  }, [copiedFlash]);


  const activeItem = items[activeIndex];
  const isAnswering = activeItem?.answer === null;

  const answerLines = useMemo(() => {
    if (!activeItem?.answer) return [];
    return activeItem.answer.split('\n');
  }, [activeItem?.answer]);

  const maxScroll = Math.max(0, answerLines.length - VIEWPORT_LINES);

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

      // Scroll up one line in the active answer body
      if (key.name === 'up' || (key.ctrl && key.name === 'p')) {
        setScrollOffset(o => Math.max(0, o - 1));
        return;
      }
      // Scroll down one line in the active answer body
      if (key.name === 'down' || (key.ctrl && key.name === 'n')) {
        setScrollOffset(o => Math.min(maxScroll, o + 1));
        return;
      }
    }
  }, [activeItem, isAnswering, maxScroll, onHide, onClearHistory]);

  // The panel only mounts while it is visible (controlled by the parent),
  // so it can unconditionally own keyboard input here. Esc fires onHide
  // which unmounts this component and re-enables the main input box.
  useKeypress(handleKeypress, { isActive: true });


  if (items.length === 0 || !activeItem) return null;

  return (
    // paddingLeft=1 aligns /btw with the ThinkingIndicator spinner
    <Box flexDirection="column" paddingLeft={1} paddingRight={1} marginTop={1}>
      {/* History list — only the newest item is rendered with full body;
          older /btw queries are collapsed to question-title rows. */}
      {items.map((item, index) => {
        const isCurrentActive = index === activeIndex;
        const isAnsweringItem = item.answer === null;

        if (!isCurrentActive) {
          // Collapsed history row — title only, dimmed.
          return (
            <Box key={item.id}>
              <Text color="gray" bold>/btw </Text>
              <Text color="gray">{item.question}</Text>
            </Box>
          );
        }

        // Active (newest) item — full body or answering spinner.
        const itemAnswerLines = item.answer ? item.answer.split('\n') : [];
        const itemVisibleAnswer = itemAnswerLines
          .slice(scrollOffset, scrollOffset + VIEWPORT_LINES)
          .join('\n');

        return (
          <Box key={item.id} flexDirection="column" marginTop={index > 0 ? 1 : 0}>
            {/* Header: /btw question (highlighted) */}
            <Box>
              <Text color="#c5a3ff" bold>/btw </Text>
              <Text color="white">{item.question}</Text>
            </Box>

            {/* Body: answering spinner or markdown answer */}
            <Box marginTop={1} marginLeft={2} flexDirection="column">
              {isAnsweringItem ? (
                <Box>
                  <Text color="#c5a3ff"><Spinner type="dots" /></Text>
                  <Text color="#c5a3ff"> Answering...</Text>
                </Box>
              ) : (
                <MarkdownText content={itemVisibleAnswer} />
              )}
            </Box>
          </Box>
        );
      })}

      {/* Footer hint — panel is always interactive while mounted.
          When the user just pressed 'c' to copy, swap the regular
          shortcut hint for a green "Copied to clipboard" badge for 3s. */}
      <Box marginTop={1}>
        {copiedFlash ? (
          <Text dimColor>
            ↑/↓ to scroll · <Text color="green">Copied to clipboard</Text> · x to clear history · Esc to close
          </Text>
        ) : (
          <Text dimColor>
            {isAnswering
              ? 'x to clear history · Esc to close'
              : '↑/↓ scroll · c copy · x clear history · Esc close'}
          </Text>
        )}
      </Box>


    </Box>
  );
};
