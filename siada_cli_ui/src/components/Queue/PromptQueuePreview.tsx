import React from 'react';
import { Box, Text } from '@jrichman/ink';
import type { PromptQueueItem } from '../../types/index.js';

interface PromptQueuePreviewProps {
  queue: PromptQueueItem[];
}

const MAX_PREVIEW_CHARS = 60;

function truncate(text: string): string {
  if (text.length <= MAX_PREVIEW_CHARS) return text;
  return `${text.slice(0, MAX_PREVIEW_CHARS)}…`;
}

export const PromptQueuePreview: React.FC<PromptQueuePreviewProps> = React.memo(({ queue }) => {
  if (queue.length === 0) return null;

  return (
    <Box flexDirection="column" paddingLeft={1} paddingBottom={1}>
      {queue.map((item, i) => (
        <Box key={item.id} flexDirection="row" gap={1}>
          {/* Index stays dim; the prompt text itself is brighter so pending
              items are clearly readable (not the darkest gray). */}
          <Text color="gray" dimColor>
            {`[${i + 1}]`}
          </Text>
          <Text color="white">
            {truncate(item.content)}
          </Text>
          {item.imagePaths && item.imagePaths.length > 0 && (
            <Text color="gray" dimColor>
              {`+${item.imagePaths.length} img`}
            </Text>
          )}
        </Box>
      ))}
      <Box>
        <Text color="gray" dimColor>
          {`${queue.length} queued · ↑ edit · Esc run now`}
        </Text>
      </Box>

    </Box>
  );
});

PromptQueuePreview.displayName = 'PromptQueuePreview';
