import React from 'react';
import { Box, Text } from '@jrichman/ink';
import { DiffView } from './DiffView.js';
import { ToolAction, ToolHeading } from '../Chat/ToolHeading.js';
import type { ApplyPatchFileChange } from '../../utils/diff.js';
import { colors } from '../../utils/colors.js';
import { useThemeVersion } from '../../themes/index.js';

export interface FileChangeSetViewProps {
  changes: ApplyPatchFileChange[];
  fileCount: number;
  width?: number;
  showHeading?: boolean;
}

function changeLabel(change: ApplyPatchFileChange): string {
  switch (change.action) {
    case 'create':
      return `Create ${change.path}`;
    case 'update':
      return `Update ${change.path}`;
    case 'delete':
      return `Delete ${change.path}`;
    case 'move':
      return `Move ${change.path} → ${change.moveTo ?? change.path}`;
    case 'failed':
      return `Failed ${change.path}${change.moveTo ? ` → ${change.moveTo}` : ''}`;
    default:
      return change.path;
  }
}

function countLines(change: ApplyPatchFileChange): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  for (const hunk of change.hunks) {
    for (const line of hunk.lines) {
      if (line.startsWith('+')) added++;
      else if (line.startsWith('-')) removed++;
    }
  }
  return { added, removed };
}

export function fileChangeSummary(changes: ApplyPatchFileChange[], fileCount: number): string {
  const total = changes.map(countLines).reduce((counts, lines) => ({
    added: counts.added + lines.added, removed: counts.removed + lines.removed,
  }), { added: 0, removed: 0 });
  const partialDiff = changes.some(change =>
    change.diffOmitted || (change.hunks.length === 0 && !!change.details && !/without text changes\.$/.test(change.details)),
  );
  const totalStats = changes.some(change => change.hunks.length > 0)
    ? ` (+${total.added} -${total.removed}${partialDiff ? ' shown' : ''})`
    : '';
  const groupLabel = changes.some(change => change.action === 'failed') ? 'File operations:' : 'Edited';
  const heading = changes.length > 1
    ? `${groupLabel} ${fileCount} files`
    : changes[0] ? changeLabel(changes[0]) : `Edited ${fileCount} files`;
  return `${heading}${totalStats}`;
}

export const FileChangeSetView: React.FC<FileChangeSetViewProps> = ({
  changes,
  fileCount,
  width,
  showHeading = true,
}) => {
  useThemeVersion();
  const diffWidth = width ?? (process.stdout.columns || 80);
  const multipleFiles = changes.length > 1;
  const fileStats = changes.map(countLines);
  const heading = fileChangeSummary(changes, fileCount);

  return (
    <Box flexDirection="column" width={diffWidth}>
      {showHeading && <ToolHeading parts={[heading]} failed={changes.some(change => change.action === 'failed')} />}
      {changes.map((change, index) => (
        <Box
          key={`${change.action}-${change.path}-${index}`}
          flexDirection="column"
          paddingLeft={multipleFiles ? 2 : 0}
          marginTop={multipleFiles && index > 0 ? 1 : 0}
        >
          {multipleFiles && (
            <Text>
              <Text color={colors.content.secondary}>{index === changes.length - 1 ? '└─ ' : '├─ '}</Text>
              <ToolAction
                label={`${changeLabel(change)}${change.hunks.length > 0 ? ` (+${fileStats[index].added} -${fileStats[index].removed})` : ''}`}
                failed={change.action === 'failed'}
              />
            </Text>
          )}
          {change.hunks.length > 0 ? (
            <Box paddingLeft={2}>
              <DiffView
                filePath={change.moveTo ?? change.path}
                hunks={change.hunks}
                width={Math.max(diffWidth - (multipleFiles ? 4 : 2), 4)}
                showFrame={false}
              />
            </Box>
          ) : (change.error || change.details) ? (
            <Box paddingLeft={2}>
              <Text color={change.action === 'failed' ? colors.error : colors.content.secondary}>
                {change.error || change.details}
              </Text>
            </Box>
          ) : null}
        </Box>
      ))}
    </Box>
  );
};
