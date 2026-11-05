import React, { useInsertionEffect } from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { Box, Text, useStdout } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { useMouseTracking } from '../../hooks/useMouseTracking.js';
import { MessageList } from '../Chat/MessageList.js';
import { Scrollable } from '../common/Scrollable.js';
import type { Message } from '../../types/index.js';
import type { TodoItem, TodoMessageRange } from '../../hooks/useAcp/types.js';
import { recordFlicker } from '../../utils/flickerMonitor.js';
import { decodeHtmlEntities } from '../../utils/htmlEntities.js';
import { useNoAltScreen } from '../../contexts/TerminalModeContext.js';

export interface TodoDetailViewProps {
  todo: TodoItem;
  messages: Message[];
  range: TodoMessageRange | undefined;
  terminalWidth: number;
  onClose: () => void;
  /** The enclosing layout already owns its terminal buffer. */
  embedded?: boolean;
}

const STATUS_ICONS: Record<string, string> = {
  pending:     '○',
  in_progress: '◐',
  completed:   '✓',
};

const STATUS_COLORS: Record<string, string> = {
  pending:     'gray',
  in_progress: 'yellow',
  completed:   'green',
};

export const TodoDetailView: React.FC<TodoDetailViewProps> = ({
  todo,
  messages,
  range,
  terminalWidth,
  onClose,
  embedded = false,
}) => {
  useUiLanguage();
  const { stdout } = useStdout();
  const { rows } = useTerminalSize();
  const noAltScreen = useNoAltScreen();
  useMouseTracking();

  // Mouse reporting is shared with the parent; only standalone views own the buffer.
  useInsertionEffect(() => {
    if (!embedded && !noAltScreen) {
      recordFlicker('manual_clear', 'TodoDetailView: entering alternate screen buffer', { captureStack: false });
      stdout?.write('\x1b[?1049h\x1b[2J\x1b[H');
    }
    return () => {
      if (!embedded && !noAltScreen) {
        recordFlicker('manual_clear', 'TodoDetailView: leaving alternate screen buffer', { captureStack: false });
        stdout?.write('\x1b[?1049l');
      }
    };
  }, [embedded, stdout, noAltScreen]);

  useKeypress((key) => {
    if (key.name === 'escape') onClose();
  }, { isActive: true });

  const slicedMessages: Message[] = range
    ? messages.slice(range.startIdx, range.endIdx ?? messages.length)
    : [];

  const icon = STATUS_ICONS[todo.status] ?? '?';
  const iconColor = STATUS_COLORS[todo.status] ?? 'white';
  const msgCount = slicedMessages.length;

  // Reserve three header rows and one footer row; long records stay in the viewport.
  return (
    <Box flexDirection="column" width={terminalWidth} height={Math.max(1, rows - 1)}>
      {/* Message area */}
      <Scrollable width={terminalWidth} height={Math.max(1, rows - 5)} hasFocus scrollToBottom>
      {slicedMessages.length === 0 ? (
        <Box paddingX={2} paddingY={1}>
          <Text color="gray">{t('此步骤暂无消息记录。', 'No messages recorded for this step.')}</Text>
        </Box>
      ) : (
        <MessageList
          messages={slicedMessages}
          terminalWidth={terminalWidth}
          isCollapsed={false}
          noStatic
        />
      )}
      </Scrollable>

      {/* Task header */}
      <Box
        borderStyle="single"
        borderColor="cyan"
        paddingX={1}
        flexDirection="row"
        justifyContent="space-between"
        flexShrink={0}
      >
        <Box flexGrow={1} flexShrink={1} overflowX="hidden">
          <Text wrap="truncate-end">
            <Text color={iconColor}>{icon} </Text>
            <Text color="cyan" bold>{decodeHtmlEntities(todo.content)}</Text>
            <Text color="gray">  [{todo.status}]</Text>
          </Text>
        </Box>
        <Box flexShrink={0}>
          <Text color="gray" wrap="truncate-end">{msgCount} message{msgCount !== 1 ? 's' : ''}</Text>
        </Box>
      </Box>

      {/* Footer hint */}
      <Box paddingX={1} flexShrink={0}>
        <Text color="gray" wrap="truncate-end">{PANEL_TIPS.todoDetail}</Text>
      </Box>
    </Box>
  );
};

export default TodoDetailView;
