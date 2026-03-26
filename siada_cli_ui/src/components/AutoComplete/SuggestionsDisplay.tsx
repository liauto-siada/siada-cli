/**
 * Suggestions Display Component
 * Enhanced autocomplete suggestions display with scrolling, highlighting, and dual-column layout
 */

import React, { useState, useMemo } from 'react';
import { Box, Text } from '@jrichman/ink';
import type { Suggestion } from '../../types/autocomplete.js';
import { getIcons } from '../../constants/icons.js';
import { CommandKind } from '../../types/autocomplete.js';
import { githubTheme } from '../Input/theme.js';

export interface SuggestionsDisplayProps {
  /** List of suggestions to display */
  suggestions: Suggestion[];
  
  /** Currently active suggestion index */
  activeIndex: number;
  
  /** Loading state */
  isLoading: boolean;
  
  /** Maximum height (number of items) */
  maxHeight?: number;
  
  /** Width of the display */
  width?: number;
  
  /** Scroll offset for visible window */
  scrollOffset?: number;
  
  /** Whether to show dual-column layout (for commands) */
  dualColumnLayout?: boolean;
  
  /** Expanded suggestion index (for long suggestions) */
  expandedIndex?: number;
}

const MAX_LABEL_LENGTH = 90;
const MAX_DESCRIPTION_LENGTH = 50;

/**
 * Highlight matched portions of text
 */
const HighlightedText: React.FC<{
  text: string;
  positions?: number[];
  isActive: boolean;
}> = React.memo(({ text, positions, isActive }) => {
  if (!positions || positions.length === 0) {
    return (
      <Text color={isActive ? 'cyan' : 'white'} bold={isActive}>
        {text}
      </Text>
    );
  }

  // Create highlighted segments
  const segments: Array<{ text: string; highlighted: boolean }> = [];
  let lastIndex = 0;

    // Deduplicate and sort positions to avoid duplicate chars
  const uniquePositions = Array.from(new Set(positions))
    .filter(pos => pos >= 0 && pos < text.length)
    .sort((a, b) => a - b);

  uniquePositions.forEach(pos => {
    if (pos > lastIndex) {
      segments.push({ text: text.substring(lastIndex, pos), highlighted: false });
    }
    segments.push({ text: text[pos], highlighted: true });
    lastIndex = pos + 1;
  });

  if (lastIndex < text.length) {
    segments.push({ text: text.substring(lastIndex), highlighted: false });
  }

  return (
    <>
      {segments.map((segment, idx) => (
        <Text
          key={idx}
          color={segment.highlighted ? 'yellow' : (isActive ? 'cyan' : 'white')}
          bold={isActive || segment.highlighted}
          backgroundColor={segment.highlighted ? 'blue' : undefined}
        >
          {segment.text}
        </Text>
      ))}
    </>
  );
});

HighlightedText.displayName = 'HighlightedText';

/**
 * Truncate text by removing the middle, keeping start + end.
 * Returns the truncated string and a function to remap original positions
 * into the new string's positions (positions in the removed middle are dropped).
 */
const truncateMiddle = (
  text: string,
  maxLength: number,
  expanded: boolean
): { text: string; remapPosition: (pos: number) => number | null } => {
  const identity = (pos: number) => pos;

  if (expanded || text.length <= maxLength) {
    return { text, remapPosition: identity };
  }

  const available = maxLength - 3; // 3 chars for '...'
  const startLen = Math.floor(available / 3);
  const endLen = available - startLen;
  const cutStart = startLen;
  const cutEnd = text.length - endLen;

  const truncated = text.substring(0, startLen) + '...' + text.substring(cutEnd);

  const remapPosition = (pos: number): number | null => {
    if (pos < cutStart) return pos;
    if (pos >= cutEnd) return pos - cutEnd + startLen + 3;
    return null; // position is in the removed middle
  };

  return { text: truncated, remapPosition };
};

export const SuggestionsDisplay: React.FC<SuggestionsDisplayProps> = ({
  suggestions,
  activeIndex,
  isLoading,
  maxHeight = 8,
  width,
  scrollOffset = 0,
  dualColumnLayout = false,
  expandedIndex = -1
}) => {
  const icons = getIcons();
  
  // Loading state
  if (isLoading) {
    return (
      <Box 
        paddingX={1} 
        paddingY={0}
        borderStyle="round" 
        borderColor="gray"
        width={width}
      >
        <Text color="gray" >
          {icons.pending} Searching...
        </Text>
      </Box>
    );
  }

  // No suggestions
  if (suggestions.length === 0) {
    return null;
  }

  // Calculate visible range with scrolling window
  const totalSuggestions = suggestions.length;
  const start = Math.max(0, Math.min(scrollOffset, totalSuggestions - maxHeight));
  const end = Math.min(totalSuggestions, start + maxHeight);
  const visibleSuggestions = suggestions.slice(start, end);
  
  const hasMoreAbove = start > 0;
  const hasMoreBelow = end < totalSuggestions;
  
  // Calculate position (1-indexed for display)
  const currentPosition = activeIndex + 1;

  return (
    <Box 
      flexDirection="column" 
      paddingX={1}
      paddingY={0}

      width={width}
    >
      {/* Header with position counter */}
      <Box marginBottom={0} justifyContent='space-between'>
        <Text color="cyan" dimColor={githubTheme.textSettings.useDimColor}>
        Suggestions
        </Text>
        <Text color="cyan" dimColor={githubTheme.textSettings.useDimColor}>
          {hasMoreAbove && ' ▲ '}
          {!hasMoreAbove && '  '}
          ({currentPosition}/{totalSuggestions})
          {hasMoreBelow && ' ▼'}
        </Text>
      </Box>

      {/* Suggestion items */}
      {visibleSuggestions.map((suggestion, visibleIndex) => {
        const globalIndex = start + visibleIndex;
        const isActive = globalIndex === activeIndex;
        const isExpanded = globalIndex === expandedIndex;
        
        const { text: label, remapPosition } = truncateMiddle(suggestion.label, MAX_LABEL_LENGTH, isExpanded);
        const remappedPositions = suggestion.positions
          ?.map(remapPosition)
          .filter((p): p is number => p !== null);
        const description = suggestion.description
          ? truncateMiddle(suggestion.description, MAX_DESCRIPTION_LENGTH, isExpanded).text
          : '';
        
        // Check if this is an MCP resource or command
        const isMcpCommand = suggestion.commandKind === CommandKind.MCP_PROMPT;
        const isMcpResource = suggestion.type === 'resource';
        const showMcpBadge = isMcpCommand || isMcpResource;
        
        return (
          <Box key={globalIndex} flexDirection="row" marginY={0}>
            {/* Selection indicator */}
            <Text color={isActive ? 'cyan' : 'gray'}>
              {isActive ? `${icons.arrowRight} ` : '  '}
            </Text>

            {/* Icon */}
            {suggestion.icon && (
              <Text>{suggestion.icon} </Text>
            )}

            {/* Dual-column layout for commands */}
            {dualColumnLayout ? (
              <>
                {/* Command name column */}
                <Box width={30}>
                  <HighlightedText
                    text={label}
                    positions={remappedPositions}
                    isActive={isActive}
                  />
                  {showMcpBadge && (
                    <Text color="magenta"> [MCP]</Text>
                  )}
                </Box>
                
                {/* Description column */}
                {description && (
                  <Box flexGrow={1} marginLeft={2}>
                    <Text color="gray" wrap="truncate">
                      {description}
                    </Text>
                  </Box>
                )}
              </>
            ) : (
              // Single-column layout for files
              <>
                {/* Label */}
                <Box flexGrow={1}>
                  <HighlightedText
                    text={label}
                    positions={remappedPositions}
                    isActive={isActive}
                  />
                  {showMcpBadge && (
                    <Text color="magenta" > [MCP]</Text>
                  )}
                </Box>

                {/* Description */}
                {description && (
                  <Box marginLeft={2}>
                    <Text color="white"  wrap="truncate">
                      {description}
                    </Text>
                  </Box>
                )}
              </>
            )}
            
            {/* Expand indicator for long text */}
            {(suggestion.label.length > MAX_LABEL_LENGTH || 
              (suggestion.description && suggestion.description.length > MAX_DESCRIPTION_LENGTH)) && (
              <Text color="gray">
                {isExpanded ? ' ←' : ' →'}
              </Text>
            )}
          </Box>
        );
      })}

      {/* Navigation hint */}
      <Box marginTop={0}>
        <Text color="gray">
          ↑↓ navigate • Tab/Enter accept • →← expand • Esc cancel
        </Text>
      </Box>
    </Box>
  );
};

export default SuggestionsDisplay;
