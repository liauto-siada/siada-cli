import React from 'react';
import { Text } from '@jrichman/ink';
import { colors } from '../../utils/colors.js';

/**
 * The `›` / `⌄` glyph that marks a row as openable.
 *
 * It shares `colors.info` with the `Run` / `Read` tool action words, so the
 * affordance reads as part of the same accent family: colored even at rest to
 * announce the row is clickable, bold once the pointer arrives.
 */
export const DisclosureArrow: React.FC<{
  glyph: string;
  hovered?: boolean;
  /**
   * Overrides the accent for states where it would not read: a disabled
   * control, or a row painted with the focus highlight.
   */
  idleColor?: string;
}> = ({ glyph, hovered = false, idleColor }) => (
  <Text color={idleColor ?? colors.info} bold={hovered || undefined}>{glyph}</Text>
);
