import React from 'react';
import { Box, Text, useStdout, type DOMElement } from '@jrichman/ink';
import stringWidth from '../../utils/terminalWidth.js';
import { useThemeVersion } from '../../themes/index.js';
import { colors } from '../../utils/colors.js';
import { ParsedToolCall } from '../../utils/toolCallParser.js';
import { ToolAction, ToolHeading } from './ToolHeading.js';

const segmenter = new Intl.Segmenter(undefined, { granularity: 'grapheme' });

export function wrapToolFieldText(text: string, width: number): string[] {
  if (text.includes('\n')) {
    return text.split(/\r?\n/).flatMap(line => wrapToolFieldText(line, width));
  }
  const rows: string[] = [];
  let row = '';
  let rowWidth = 0;
  for (const { segment } of segmenter.segment(text.replaceAll('\t', '    '))) {
    const next = stringWidth(segment);
    if (row && rowWidth + next > width) {
      // Ink strips trailing whitespace from rendered lines. At a word
      // boundary, let the newline serve as the separator instead.
      rows.push(row.trimEnd());
      row = '';
      rowWidth = 0;
    }
    row += segment;
    rowWidth += next;
  }
  rows.push(row.trimEnd());
  return rows;
}

export function wrapHeading(text: string, firstWidth: number, continuationWidth: number): string[] {
  const rows: string[] = [];
  let row = '';
  let rowWidth = 0;
  for (const { segment } of segmenter.segment(text.replaceAll('\t', '    '))) {
    if (segment === '\n' || segment === '\r\n') {
      rows.push(row.trimEnd());
      row = '';
      rowWidth = 0;
      continue;
    }
    const width = rows.length === 0 ? firstWidth : continuationWidth;
    const next = stringWidth(segment);
    if (row && rowWidth + next > width) {
      rows.push(row.trimEnd());
      row = '';
      rowWidth = 0;
    }
    row += segment;
    rowWidth += next;
  }
  rows.push(row.trimEnd());
  return rows;
}

type SearchFragment = { text: string; muted: boolean; arrow?: boolean };

function wrapSearchHeading(parts: SearchFragment[], firstWidth: number, continuationWidth: number): SearchFragment[][] {
  const rows: SearchFragment[][] = [[]];
  let width = 0;
  for (const part of parts) {
    for (const { segment } of segmenter.segment(part.text.replaceAll('\t', '    '))) {
      if (segment === '\n' || segment === '\r\n') {
        rows.push([]);
        width = 0;
        continue;
      }
      const nextWidth = stringWidth(segment);
      const limit = rows.length === 1 ? firstWidth : continuationWidth;
      if (width && width + nextWidth > limit) {
        // Terminal rendering strips whitespace at physical line ends. Keep
        // separators on the line where they are visible, never as a new row.
        const last = rows[rows.length - 1];
        if (last[last.length - 1]?.text.endsWith(' ')) {
          last[last.length - 1].text = last[last.length - 1].text.trimEnd();
        }
        rows.push([]);
        width = 0;
      }
      if (!width && segment === ' ') continue;
      const row = rows[rows.length - 1];
      if (row[row.length - 1]?.muted === part.muted && row[row.length - 1]?.arrow === part.arrow) {
        row[row.length - 1].text += segment;
      } else {
        row.push({ text: segment, muted: part.muted, arrow: part.arrow });
      }
      width += nextWidth;
    }
  }
  return rows;
}

function searchFragments(row: SearchFragment[], arrowHovered = false): React.ReactNode {
  return row.map((fragment, index) => (
    <Text key={index}
      color={fragment.arrow ? colors.info : fragment.muted ? colors.content.secondary : undefined}
      bold={fragment.arrow && arrowHovered ? true : undefined}>{fragment.text}</Text>
  ));
}

/** Parsed, borderless arguments for file/directory reads, search, and fetch. */
export const ToolPromptView: React.FC<{
  tool: ParsedToolCall;
  content: string;
  maxRows?: number;
  width?: number;
  showHeading?: boolean;
  searchPresentation?: {
    prefix: string;
    headingRef?: React.Ref<DOMElement>;
    backgroundColor?: string;
    disclosure: string;
    /** Highlight the disclosure glyph while the pointer is over the heading. */
    disclosureHovered?: boolean;
    showCwd: boolean;
    secondary?: boolean;
  };
}> = ({ tool, content, maxRows, width: availableWidth, showHeading = true, searchPresentation }) => {
  useThemeVersion();
  const { stdout } = useStdout();
  const columns = availableWidth ?? (stdout?.columns || process.stdout.columns || 80);
  const isFetch = tool.type === 'web' && !content.startsWith('Web search:');
  const isWebSearch = tool.type === 'web' && !isFetch;
  // WebSearchFormatter emits "Web search: search: <query>"; older history
  // sometimes has only "Web search: <query>".
  const webQuery = isWebSearch ? (tool.details || '').replace(/^search:\s*/, '') : '';
  const action = tool.type === 'read_file' ? 'Read file'
    : tool.type === 'view_dir' ? 'View directory'
      : isFetch ? 'Fetch' : isWebSearch ? 'Web Search' : 'Search';
  const argument = tool.type === 'read_file' ? tool.path || ''
    : tool.type === 'view_dir' ? tool.path || ''
      : isFetch ? tool.details || '' : isWebSearch ? webQuery : tool.query || '';
  const lineRange = tool.type === 'read_file' && tool.lineStart !== undefined && tool.lineEnd !== undefined
    ? ` · lines ${tool.lineStart}-${tool.lineEnd}` : '';
  const searchIndent = searchPresentation ? stringWidth(searchPresentation.prefix) : 2;
  const continuationIndent = searchPresentation ? searchIndent + stringWidth('Search ') : 2;
  const searchRows = tool.type === 'search' && tool.path ? wrapSearchHeading(
    [
      { text: searchPresentation ? `"${argument.replaceAll('"', '\\"')}"` : argument, muted: Boolean(searchPresentation?.secondary) },
      { text: ' in ', muted: true },
      { text: tool.path, muted: Boolean(searchPresentation?.secondary) },
      { text: searchPresentation?.disclosure || '', muted: true, arrow: true },
    ],
    Math.max(1, columns - (searchPresentation ? searchIndent + stringWidth('Search ') + 1 :
      showHeading ? stringWidth('● Search ') + 1 : 1)),
    Math.max(1, columns - continuationIndent - 1),
  ) : null;
  // The value is shown once, in the heading. Wrap instead of clipping long
  // paths/queries/URLs so there is no need to duplicate them in the tree.
  const headingRows = !searchRows && (argument || lineRange) ? wrapHeading(
    `${argument}${lineRange}`,
    Math.max(1, columns - (showHeading ? stringWidth(`● ${action} `) + 1 : 1)),
    Math.max(1, columns - 3),
  ) : [];
  const headingCount = searchRows?.length ?? headingRows.length;
  const arrowHovered = Boolean(searchPresentation?.disclosureHovered);
  const shownCount = maxRows === undefined ? headingCount : Math.min(headingCount, Math.max(1, maxRows));
  const visibleHeading = headingRows.slice(0, shownCount);
  const visibleSearch = searchRows?.slice(0, shownCount);
  const entries: Array<[string, string]> = tool.type === 'read_file'
    ? tool.cwd ? [['cwd', tool.cwd]] : []
    : tool.type === 'view_dir' || isFetch || isWebSearch
      ? []
      : ([
          ['file pattern', tool.filePattern || ''],
          ['cwd', searchPresentation && !searchPresentation.showCwd ? '' : tool.cwd || ''],
        ] as Array<[string, string]>).filter(([, value]) => value !== '');

  // Partially streamed or older tool payloads may not include every field.
  // Preserve the original prompt only if we could not extract the argument.
  const fields = !argument && !isWebSearch ? [['prompt', content]] : entries;
  // Two-column indentation, three-column tree prefix, and one spare column
  // so Ink and the terminal never compete over a soft-wrapped final cell.
  const width = Math.max(2, columns - searchIndent - 4);
  const rows = fields.flatMap(([name, value], index) => {
    const branch = index === fields.length - 1 ? '└─ ' : '├─ ';
    return wrapToolFieldText(`${name}: ${value}`, width).map((line, lineIndex) => ({
      prefix: lineIndex === 0 ? branch : '   ',
      line,
    }));
  });
  const availableRows = maxRows === undefined ? rows.length : Math.max(0, maxRows - shownCount);
  const visible = rows.slice(0, availableRows);

  return (
    <Box flexDirection="column">
      {searchPresentation && searchRows ? (
        <Box>
          <Box ref={searchPresentation.headingRef} flexShrink={1}
            backgroundColor={searchPresentation.backgroundColor}>
            <Text color={searchPresentation.secondary ? colors.content.secondary : undefined}>
              <Text color={colors.content.secondary}>{searchPresentation.prefix}</Text>
              {searchPresentation.secondary ? 'Search' : <ToolAction label="Search" />} {searchFragments(visibleSearch?.[0] || [], arrowHovered)}
            </Text>
          </Box>
        </Box>
      ) : !showHeading ? (
        <Text>{visibleSearch?.[0] ? searchFragments(visibleSearch[0], arrowHovered) : visibleHeading[0]}</Text>
      ) : searchRows ? (
        <ToolHeading parts={['Search']} suffix={visibleSearch?.[0] && <> {searchFragments(visibleSearch[0], arrowHovered)}</>} />
      ) : (
        <ToolHeading parts={[`${action}${visibleHeading.length ? ` ${visibleHeading[0]}` : ''}`]} />
      )}
      {visibleSearch?.slice(1).map((line, index) => (
        <Box key={`search-${index}`} paddingLeft={continuationIndent}>
          <Text>{searchFragments(line, arrowHovered)}</Text>
        </Box>
      ))}
      {visibleHeading.slice(1).map((line, index) => (
        <Box key={index} paddingLeft={2}>
          <Text>{line}</Text>
        </Box>
      ))}
      {shownCount < headingCount && (
        <Box paddingLeft={2}>
          <Text color={colors.content.secondary}>… {headingCount - shownCount} more lines</Text>
        </Box>
      )}
      {rows.length > 0 && <Box flexDirection="column" paddingLeft={searchIndent}>
        {visible.map(({ prefix, line }, index) => (
          <Box key={index}>
            <Text color={colors.content.secondary}>{prefix}</Text>
            <Text>{line}</Text>
          </Box>
        ))}
        {visible.length < rows.length && <Text color={colors.content.secondary}>   … {rows.length - visible.length} more lines</Text>}
      </Box>}
    </Box>
  );
};
