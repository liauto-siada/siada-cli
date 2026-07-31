import React, { useInsertionEffect } from 'react';
import { Box, Text, useStdout } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { MessageList } from '../Chat/MessageList.js';
import type { Message } from '../../types/index.js';
import type { TodoItem, TodoMessageRange } from '../../hooks/useAcp/types.js';
import { recordFlicker } from '../../utils/flickerMonitor.js';

export interface TodoDetailViewProps {
  todo: TodoItem;
  messages: Message[];
  range: TodoMessageRange | undefined;
  terminalWidth: number;
  onClose: () => void;
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
}) => {
  const { stdout } = useStdout();

  // Switch to alternate screen buffer on mount so Static history doesn't bleed through.
  // useInsertionEffect (NOT useEffect/useLayoutEffect): reconciler triggers onRender
  // between mutation/layout phases. With useEffect, the FIRST frame is written to the
  // MAIN screen before the alt screen is entered, leaking content. Insertion effects
  // run during the mutation phase, so ENTER_ALT_SCREEN reaches the terminal before
  // the first frame does. (Pattern borrowed from claude-code's AlternateScreen.)
  useInsertionEffect(() => {
    recordFlicker('manual_clear', 'TodoDetailView: entering alternate screen buffer (\\x1b[?1049h\\x1b[2J\\x1b[H)', {
      captureStack: false,
    });
    stdout?.write('\x1b[?1049h\x1b[2J\x1b[H');
    return () => {
      recordFlicker('manual_clear', 'TodoDetailView: leaving alternate screen buffer (\\x1b[?1049l)', {
        captureStack: false,
      });
      stdout?.write('\x1b[?1049l');
    };
  }, [stdout]);

  useKeypress((key) => {
    if (key.name === 'escape') onClose();
  }, { isActive: true });

  const slicedMessages: Message[] = range
    ? messages.slice(range.startIdx, range.endIdx ?? messages.length)
    : [];

  const icon = STATUS_ICONS[todo.status] ?? '?';
  const iconColor = STATUS_COLORS[todo.status] ?? 'white';
  const msgCount = slicedMessages.length;

  // Pattern matches MainLayout's input-box arrangement: MessageList uses Static
  // (writes messages to alt-buffer cursor, naturally scrolling), then header +
  // footer are rendered as the Ink live frame right after — like the input box.
  // No height/flexGrow constraint: Static items don't participate in flex layout,
  // so a parent height={rows} would make Ink paint a full-screen live frame that
  // pushes Static items off-screen, leaving messages invisible.
  return (
    <Box flexDirection="column" width={terminalWidth}>
      {/* Message area */}
      {slicedMessages.length === 0 ? (
        <Box paddingX={2} paddingY={1}>
          <Text color="gray">No messages recorded for this step.</Text>
        </Box>
      ) : (
        <MessageList
          messages={slicedMessages}
          terminalWidth={terminalWidth}
          isCollapsed={false}
          noStatic
        />
      )}

      {/* Task header (input-box position: live frame right after Static messages) */}
      <Box
        borderStyle="single"
        borderColor="cyan"
        paddingX={1}
        flexDirection="row"
        justifyContent="space-between"
        flexShrink={0}
      >
        <Box>
          <Text color={iconColor}>{icon} </Text>
          <Text color="cyan" bold>{todo.content}</Text>
          <Text color="gray">  [{todo.status}]</Text>
        </Box>
        <Text color="gray">{msgCount} message{msgCount !== 1 ? 's' : ''}</Text>
      </Box>

      {/* Footer hint */}
      <Box paddingX={1} flexShrink={0}>
        <Text color="gray">Esc close</Text>
      </Box>
    </Box>
  );
};

export default TodoDetailView;
