import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { StructuredPatchHunk } from 'diff';

vi.mock('@jrichman/ink', async () => {
  const React = await import('react');
  return {
    Box: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    Text: ({ children, color, backgroundColor, bold }: {
      children?: React.ReactNode;
      color?: string;
      backgroundColor?: string;
      bold?: boolean;
    }) => <span data-color={color} data-background={backgroundColor} data-bold={bold}>{children}</span>,
  };
});

import { DiffView } from '../src/components/diff/DiffView.js';

function renderLines(lines: string[], width = 60): string {
  const hunk: StructuredPatchHunk = {
    oldStart: 1,
    oldLines: lines.filter(line => !line.startsWith('+')).length,
    newStart: 1,
    newLines: lines.filter(line => !line.startsWith('-')).length,
    lines,
  };
  return renderToStaticMarkup(<DiffView filePath="src/example.ts" hunks={[hunk]} width={width} showFrame={false} />);
}

function expectBrightSigns(output: string): void {
  expect(output).toContain('<span data-color="#f87171" data-background="#4a1a1a" data-bold="true">-</span>');
  expect(output).toContain('<span data-color="#4ade80" data-background="#1a4a1a" data-bold="true">+</span>');
  // Only the signs get brighter foreground colors, not the gutter or code.
  expect(output.match(/data-color="#(?:f87171|4ade80)"/g)).toHaveLength(2);
}

describe('diff +/- emphasis', () => {
  it('highlights signs in regular and wrapped rows without highlighting continuation gutters', () => {
    const output = renderLines([
      '-an entirely different removed line that needs wrapping',
      '+brand new added content that also needs wrapping',
      ' unchanged context',
    ], 25);

    expectBrightSigns(output);
    expect(output).toContain('unchanged context');
  });

  it('highlights signs in word-diff rows while retaining their word background colors', () => {
    const output = renderLines([
      '-const label = "old name";',
      '+const label = "new name";',
    ]);

    expectBrightSigns(output);
    expect(output).toContain('data-background="#6b2626"');
    expect(output).toContain('data-background="#1f5f27"');
  });
});
