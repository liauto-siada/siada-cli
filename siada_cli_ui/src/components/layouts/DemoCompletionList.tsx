import React from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { Box, Text } from '@jrichman/ink';
import type { Suggestion } from '../../types/autocomplete.js';
import { colors } from '../../utils/colors.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { slashCommandService } from '../../services/slashCommandService.js';

/** Use the same typography and selection treatment as the demo's other lists. */
export function DemoCompletionList({ suggestions, activeIndex, width }: {
  suggestions: Suggestion[]; activeIndex: number; width: number;
}) {
  useUiLanguage();
  const start = Math.max(0, activeIndex - 4);
  return <Box width={width} paddingX={1} flexDirection="column">
    <Box height={1}><Text bold color={colors.content.secondary}>{t('命令建议', 'Suggestions')}</Text></Box>
    {suggestions.slice(start, start + 5).map((suggestion, offset) => {
      const selected = start + offset === activeIndex;
      const tone = selected ? '#1f2328' : colors.content.secondary;
      const labelWidth = suggestion.description
        ? Math.min(22, Math.max(12, Math.floor(width / 3)), Math.max(0, width - 2))
        : Math.max(0, width - 2);
      return <Box key={`${start + offset}:${suggestion.value}`} height={1}
        backgroundColor={selected ? '#8aa8c8' : undefined}>
        <Box width={2} flexShrink={0}>
          <Text color={tone} bold={selected}>{selected ? '›' : ' '} </Text>
        </Box>
        <Box width={Math.max(0, labelWidth - (suggestion.description ? 3 : 2))} flexShrink={0}>
          <Text color={tone} bold={selected} wrap="truncate-middle">{suggestion.label}</Text>
        </Box>
        {suggestion.description && <Box marginLeft={1} flexShrink={1} overflowX="hidden">
          <Text color={tone} wrap="truncate-end">{suggestion.type === 'command'
            ? slashCommandService.describeCommand(suggestion.label, suggestion.description)
            : suggestion.description || ''}</Text>
        </Box>}
      </Box>;
    })}
    <Text color={colors.content.secondary} wrap="truncate-end">{PANEL_TIPS.demoCompletion}</Text>
  </Box>;
}