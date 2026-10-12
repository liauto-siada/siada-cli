import React from 'react';
import { Text } from '@jrichman/ink';
import { colors } from '../../utils/colors.js';
import { useThemeVersion } from '../../themes/index.js';

/** Render the action in a tool label with the same emphasis in every tool view. */
export const ToolAction: React.FC<{ label: string; failed?: boolean; accent?: string }> = ({ label, failed = false, accent = colors.info }) => {
  const firstSpace = label.indexOf(' ');
  const actionEnd = label === 'Web Search' || label.startsWith('Web Search ')
    ? 'Web Search'.length : firstSpace;
  const action = actionEnd === -1 ? label : label.slice(0, actionEnd);
  const rest = actionEnd === -1 ? '' : label.slice(actionEnd);
  return (
    <>
      <Text color={failed ? colors.error : accent} bold>{action}</Text>
      <Text>{rest}</Text>
    </>
  );
};

/** Shared top-level heading for aggregated commands and file-edit diffs. */
export const ToolHeading: React.FC<{
  parts: string[];
  hint?: string;
  failed?: boolean;
  accent?: string;
  suffix?: React.ReactNode;
}> = ({ parts, hint, failed = false, accent, suffix }) => {
  useThemeVersion();
  const headingAccent = failed ? colors.error : (accent ?? colors.info);
  return (
    <Text>
      <Text color={headingAccent}>●</Text>{' '}
      {parts.map((part, index) => (
        <React.Fragment key={`${index}-${part}`}>
          {index > 0 && ', '}
          <ToolAction label={part} failed={failed} accent={headingAccent} />
        </React.Fragment>
      ))}
      {suffix}
      {hint && <Text color={colors.content.secondary}> ({hint})</Text>}
    </Text>
  );
};
