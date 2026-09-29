/**
 * Palette guard for the conversation view.
 *
 * Body text (tool values, commands, answers) renders in the terminal's own
 * foreground — the same color as the plain text of a "Run N commands" heading.
 * On top of that the theme sets a hierarchy: `secondary` for reasoning text,
 * hints and diff context, `tertiary` for line numbers and separators, plus the
 * structural tones (frames, command surface, diff bands and signs). Each tier
 * has to stay legible on the user's palette *and* stay visibly distinct from
 * the tier above it, which is what makes the hierarchy readable instead of
 * washed out.
 */

import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Message as ChatMessage } from '../src/types/index.js';

vi.mock('@jrichman/ink', async () => {
  const React = await import('react');
  return {
    Box: ({ children, borderStyle, borderColor }: { children?: React.ReactNode; borderStyle?: string; borderColor?: string }) => (
      <div {...(borderStyle ? { 'data-border-style': borderStyle } : {})} {...(borderColor ? { 'data-border-color': borderColor } : {})}>{children}</div>
    ),
    Text: ({ children, color, bold, backgroundColor, dimColor }: {
      children?: React.ReactNode;
      color?: string;
      bold?: boolean;
      backgroundColor?: string;
      dimColor?: boolean;
    }) => (
      <span
        data-color={color}
        data-bold={bold}
        data-dim={dimColor}
        {...(backgroundColor ? { 'data-background': backgroundColor } : {})}
      >
        {children}
      </span>
    ),
    Static: ({ items, children }: { items: unknown[]; children: (item: unknown, index: number) => React.ReactNode }) => (
      <section>{items.map((item, index) => children(item, index))}</section>
    ),
    useStdout: () => ({ stdout: { rows: 48, columns: 80 } }),
  };
});

import { Message } from '../src/components/Chat/Message.js';
import { setActiveTheme, getActiveTheme } from '../src/themes/index.js';
import { colors } from '../src/utils/colors.js';

type Theme = 'dark' | 'light';

/** Backgrounds a dark theme can sit on, and the foreground it then inherits. */
const DARK_BACKGROUNDS = ['#000000', '#1e1e1e', '#002b36', '#282828', '#2e3440', '#1a1b26'];
const LIGHT_BACKGROUNDS = ['#ffffff', '#fafafa', '#fdf6e3', '#eee8d5', '#fbf1c7', '#f4ecd8'];

function channel(value: number): number {
  const c = value / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex: string): number {
  const value = hex.replace('#', '');
  const [r, g, b] = [0, 2, 4].map(offset => parseInt(value.slice(offset, offset + 2), 16));
  return 0.2126 * channel(r!) + 0.7152 * channel(g!) + 0.0722 * channel(b!);
}

function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (high! + 0.05) / (low! + 0.05);
}

function minContrast(foreground: string, backgrounds: string[]): number {
  return Math.min(...backgrounds.map(background => contrast(foreground, background)));
}

const thinkingMessage = (): ChatMessage => ({
  id: 'thinking',
  type: 'agent',
  content: 'THINKING: \nWeigh the two options, then pick the smaller diff.',
  author: 'Siada',
  timestamp: '2026-01-01T00:00:00.000Z',
  metadata: { subtype: 'thinking', streamEnd: true },
});

const readToolMessage = (): ChatMessage => ({
  id: 'read',
  type: 'agent',
  content: 'Read the file `/tmp/project/src/entry.py` from line 46 to line 620.\ncwd: `/tmp/project`',
  author: 'Siada',
  timestamp: '2026-01-01T00:00:00.000Z',
  metadata: { subtype: 'tool_use', streamEnd: true },
});

afterEach(() => setActiveTheme('dark'));

describe('structural colors stay usable under the terminal foreground', () => {
  it.each([
    { theme: 'dark' as Theme, backgrounds: DARK_BACKGROUNDS, inherited: '#ffffff', typicalForeground: '#e6e6e6' },
    { theme: 'light' as Theme, backgrounds: LIGHT_BACKGROUNDS, inherited: '#000000', typicalForeground: '#333333' },
  ])('keeps $theme content tiers legible and ordered', ({ theme, backgrounds, inherited, typicalForeground }) => {
    setActiveTheme(theme);
    const { secondary, tertiary } = colors.content;
    // Both tiers are meant to be read, not squinted at.
    expect(minContrast(secondary, backgrounds)).toBeGreaterThanOrEqual(4.5);
    expect(minContrast(tertiary, backgrounds)).toBeGreaterThanOrEqual(3.5);
    // ...and both have to sit below the body text, or the hierarchy collapses
    // into "everything is the same color" again.
    expect(contrast(secondary, typicalForeground)).toBeGreaterThanOrEqual(1.3);
    expect(contrast(tertiary, typicalForeground)).toBeGreaterThanOrEqual(1.8);
    // The two tiers must be further apart than a rounding error.
    expect(contrast(secondary, tertiary)).toBeGreaterThanOrEqual(1.6);
    // Frames only need to be visible against the terminal background.
    expect(minContrast(colors.content.border, backgrounds)).toBeGreaterThanOrEqual(1.2);
    // The command surface stays a near-background tone, so the foreground the
    // terminal already picked for that background keeps its contrast on top.
    expect(contrast(colors.content.surface, inherited)).toBeGreaterThanOrEqual(7);
  });

  it.each([
    { theme: 'dark' as Theme, foreground: '#ffffff', signs: { added: '#4ade80', removed: '#f87171' } },
    { theme: 'light' as Theme, foreground: '#000000', signs: { added: '#14752f', removed: '#b81f2a' } },
  ])('keeps $theme diff bands readable under the inherited foreground', ({ theme, foreground, signs }) => {
    setActiveTheme(theme);
    const { diff } = colors;
    // Code on a band is uncolored, so every band has to tolerate the polarity
    // of foreground that comes with this theme.
    for (const band of [diff.addedBg, diff.removedBg, diff.addedWordBg, diff.removedWordBg]) {
      expect(contrast(band, foreground)).toBeGreaterThanOrEqual(4.5);
    }
    expect(contrast(signs.added, diff.addedBg)).toBeGreaterThanOrEqual(4.5);
    expect(contrast(signs.removed, diff.removedBg)).toBeGreaterThanOrEqual(4.5);
    // Word-level highlights still have to be told apart from the band itself.
    expect(contrast(diff.addedWordBg, diff.addedBg)).toBeGreaterThanOrEqual(1.2);
    expect(contrast(diff.removedWordBg, diff.removedBg)).toBeGreaterThanOrEqual(1.2);
    expect(diff.addedSign).toBe(signs.added);
    expect(diff.removedSign).toBe(signs.removed);
  });

  it('swaps the structural tones in place so memoized views repaint on /theme', () => {
    setActiveTheme('dark');
    const content = colors.content;
    const diff = colors.diff;
    const darkBorder = content.border;
    setActiveTheme('light');
    expect(colors.content).toBe(content);
    expect(colors.diff).toBe(diff);
    expect(content.border).not.toBe(darkBorder);
    setActiveTheme('dark');
    expect(colors.content.border).toBe(darkBorder);
  });
});

describe('thinking and tool bodies match the terminal foreground', () => {
  it.each(['dark', 'light'] as const)('renders reasoning one tier below the body text (%s)', theme => {
    setActiveTheme(theme);
    const output = renderToStaticMarkup(<Message message={thinkingMessage()} isCollapsed={false} />);

    expect(output).toContain(`data-color="${colors.content.secondary}">Weigh the two options, then pick the smaller diff.</span>`);
    expect(output).toContain(`data-border-color="${colors.content.border}"`);
    // `dimColor` is not a legibility guarantee: palettes are free to ignore it.
    expect(output).not.toContain('data-dim="true"');
  });

  it.each(['dark', 'light'] as const)('keeps tool values on the body text and connectors a tier below (%s)', theme => {
    setActiveTheme(theme);
    const output = renderToStaticMarkup(<Message message={readToolMessage()} isCollapsed={false} />);

    expect(output).toContain('<span>cwd: /tmp/project</span>');
    expect(output).toContain(`data-color="${colors.content.secondary}">└─ </span>`);
    expect(output).not.toContain('data-color="white"');
    // No washed-out grays left over from the previous palettes.
    const stale = ['#c4cbd3', '#39424c', '#9ca3af', '#57606a', '#9aa4b2', '#d0d7de', '#1f2328', '#7d8590'];
    expect(output).not.toMatch(new RegExp(`data-color="(?:${stale.join('|')})"`));
  });

  it('keeps the theme applied while tool bodies are rendered', () => {
    setActiveTheme('light');
    expect(getActiveTheme()).toBe('light');
    renderToStaticMarkup(<Message message={readToolMessage()} isCollapsed={false} />);
    expect(colors.content.surface).toBe('#f0f1f3');
  });
});
