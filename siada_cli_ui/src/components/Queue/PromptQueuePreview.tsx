import React from 'react';
import { Box, Text } from '@jrichman/ink';
import type { PromptQueueItem } from '../../types/index.js';
import { colors } from '../../utils/colors.js';
import { useThemeVersion } from '../../themes/index.js';

interface PromptQueuePreviewProps {
  queue: PromptQueueItem[];
}

const MAX_PREVIEW_CHARS = 60;

function truncate(text: string): string {
  if (text.length <= MAX_PREVIEW_CHARS) return text;
  return `${text.slice(0, MAX_PREVIEW_CHARS)}…`;
}

export const PromptQueuePreview: React.FC<PromptQueuePreviewProps> = React.memo(({ queue }) => {
  useThemeVersion(); // repaint on theme change
  if (queue.length === 0) return null;

  return (
    <Box flexDirection="column" paddingLeft={1} paddingBottom={1}>
      {queue.map((item, i) => (
        <Box key={item.id} flexDirection="row" gap={1}>
          {/* Index stays subordinate; the prompt text itself is brighter so pending
              items are clearly readable (not the darkest gray). */}
          <Text color={colors.content.tertiary}>
            {`[${i + 1}]`}
          </Text>
          <Text>
            {truncate(item.content)}
          </Text>
          {item.imagePaths && item.imagePaths.length > 0 && (
            <Text>
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
