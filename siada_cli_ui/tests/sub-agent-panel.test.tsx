import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@jrichman/ink', async () => {
  const React = await import('react');
  return {
    Box: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
    Text: ({ children, color }: { children?: React.ReactNode; color?: string }) => (
      <span data-color={color}>{children}</span>
    ),
  };
});

import { SubAgentDisplay } from '../src/components/SubAgent/SubAgentDisplay.js';
import type { SubAgentItem } from '../src/hooks/useAcp/types.js';

const item = (status: SubAgentItem['status']): SubAgentItem => ({
  id: `sa_${status}`,
  title: `Task ${status}`,
  status,
});

const visible = (html: string) => html.replace(/<[^>]*>/g, '');

describe('SubAgentDisplay status glyphs', () => {
  it('renders a cancelled sub-agent with the cancelled glyph, not the failure cross', () => {
    const html = renderToStaticMarkup(<SubAgentDisplay items={[item('cancelled')]} activeIndex={-1} />);
    expect(visible(html)).toContain('⊘');
    expect(visible(html)).toContain('Task cancelled');
    expect(visible(html)).not.toContain('✗');
    expect(html).toContain('<span data-color="gray">⊘ </span>');
    expect(html).not.toContain('data-color="red"');
  });

  it('still renders failed sub-agents with the red failure cross', () => {
    const html = renderToStaticMarkup(<SubAgentDisplay items={[item('failed')]} activeIndex={-1} />);
    expect(visible(html)).toContain('✗');
    expect(html).toContain('<span data-color="red">✗ </span>');
    expect(visible(html)).not.toContain('⊘');
  });
});
