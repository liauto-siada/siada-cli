import React, { useEffect } from 'react';
import { Box, Text, useStdout } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { useTerminalSize } from '../../hooks/useTerminalSize.js';
import { MessageList } from '../Chat/MessageList.js';
import { Scrollable } from '../common/Scrollable.js';
import type { Message } from '../../types/index.js';
import type { SubAgentItem, SubAgentMessageEntry } from '../../hooks/useAcp/types.js';

export interface SubAgentDetailViewProps {
  item: SubAgentItem;
  entries: SubAgentMessageEntry[];
  terminalWidth: number;
  onClose: () => void;
}

const STATUS_ICONS: Record<string, string> = {
  running:   '◐',
  completed: '✓',
  failed:    '✗',
};

const STATUS_COLORS: Record<string, string> = {
  running:   'yellow',
  completed: 'green',
  failed:    'red',
};

/**
 * Map sub-agent content entries to chat Messages so MessageList can render them.
 * tool_output entries are intentionally dropped: tool results (e.g. "✓ File
 * content loaded") are noise in the detail view — thinking / tool_call /
 * final message carry the useful information.
 */
export function entriesToMessages(itemId: string, entries: SubAgentMessageEntry[]): Message[] {
  return entries
    .filter(entry => entry.kind !== 'tool_output')
    .map((entry, index) => {
      const base = {
        id: `${itemId}_${index}`,
        timestamp: '1970-01-01T00:00:00.000Z',  // placeholder; detail view doesn't show real times
        author: 'SubAgent',
      };
      switch (entry.kind) {
        case 'thinking':
          return { ...base, type: 'agent' as const, content: entry.text, metadata: { subtype: 'thinking' as const } };
        case 'tool_call':
          return { ...base, type: 'agent' as const, content: entry.text, metadata: { subtype: 'tool_use' as const } };
        case 'message':
        default:
          return { ...base, type: 'agent' as const, content: entry.text, metadata: { subtype: 'answer' as const } };
      }
    });
}

export const SubAgentDetailView: React.FC<SubAgentDetailViewProps> = ({
  item,
  entries,
  terminalWidth,
  onClose,
}) => {
  const { rows } = useTerminalSize();
  const { stdout } = useStdout();

  // Enable SGR mouse reporting (button/wheel events in SGR format) while the
  // detail view is open so the Scrollable viewport responds to the mouse
  // wheel — same mechanism as claude-code's AlternateScreen mouseTracking.
  // Disabled again on unmount. Trade-off: while active, mouse text selection
  // in the terminal is captured by the app (standard for this feature).
  useEffect(() => {
    stdout?.write('\x1b[?1000;1006h');
    return () => {
      stdout?.write('\x1b[?1000;1006l');
    };
  }, [stdout]);

  useKeypress((key) => {
    if (key.name === 'escape') onClose();
  }, { isActive: true });

  const messages: Message[] = entriesToMessages(item.id, entries);
  const icon = STATUS_ICONS[item.status] ?? '?';
  const iconColor = STATUS_COLORS[item.status] ?? 'white';
  const msgCount = messages.length;

  // Inline rendering (NO alternate screen) with a Scrollable viewport: content
  // taller than the terminal is reviewed with ↑↓ / PgUp/PgDn inside the
  // viewport (Ink overflowY="scroll" scrollbar), never pushed into the main
  // scrollback. Header (bordered, 3 rows) + footer (1 row) + slack → viewport
  // gets the rest.
  const viewportHeight = Math.max(5, rows - 6);

  return (
    <Box flexDirection="column" width={terminalWidth}>
      {/* Message area (entries grow in real time while the sub agent runs;
          Scrollable sticks to bottom when already at bottom) */}
      {messages.length === 0 ? (
        <Box paddingX={2} paddingY={1}>
          <Text color="gray">No messages recorded for this sub agent.</Text>
        </Box>
      ) : (
        <Scrollable
          width={terminalWidth}
          height={viewportHeight}
          hasFocus
          scrollToBottom
        >
          <MessageList
            messages={messages}
            terminalWidth={terminalWidth}
            isCollapsed={false}
            noStatic
          />
        </Scrollable>
      )}

      {/* Task header */}
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
          <Text color="cyan" bold>{item.title}</Text>
          <Text color="gray">  [{item.status}]</Text>
        </Box>
        <Text color="gray">{msgCount} message{msgCount !== 1 ? 's' : ''}</Text>
      </Box>

      {/* Footer hint */}
      <Box paddingX={1} flexShrink={0}>
        <Text color="gray">↑↓ / PgUp/PgDn / wheel scroll • Esc close</Text>
      </Box>
    </Box>
  );
};

export default SubAgentDetailView;

