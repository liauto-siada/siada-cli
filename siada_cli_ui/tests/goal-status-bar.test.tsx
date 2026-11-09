import React from 'react';
import chalk from 'chalk';
import { PassThrough } from 'node:stream';
import { render } from '@jrichman/ink';
import { afterEach, describe, expect, it, vi } from 'vitest';
import stringWidth from 'string-width';
import { GoalStatusBar } from '../src/components/Goal/GoalStatusBar.js';
import type { GoalState } from '../src/hooks/useAcp/types.js';
import { setActiveTheme } from '../src/themes/index.js';
import { goalElapsedSeconds } from '../src/utils/goalDisplay.js';

const startedAt = '2026-01-01T00:00:00Z';
const startMs = Date.parse(startedAt);
const wait = () => new Promise(resolve => setTimeout(resolve, 100));
const apps = new Set<ReturnType<typeof render>>();

function mount(state: GoalState, width = 80) {
  let frame = '', raw = '';
  const app = render(<GoalStatusBar compact width={width} goalState={state} />, {
    stdout: Object.assign(new PassThrough(), { rows: 24, columns: width }),
    stdin: new PassThrough(), patchConsole: false, exitOnCtrlC: false, maxFps: 0,
    onRender: ({ output }) => { raw = output; frame = output.replace(/\x1b\[[0-9;]*m/g, ''); },
  });
  apps.add(app);
  return { app, frame: () => frame, raw: () => raw };
}

afterEach(() => {
  for (const app of apps) { app.unmount(); app.cleanup(); }
  apps.clear();
  vi.restoreAllMocks();
  vi.useRealTimers();
  setActiveTheme('dark');
});

describe('live Goal status', () => {
  it('ticks while active, stops when blocked, and resumes from accumulated time', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    let now = startMs;
    vi.spyOn(Date, 'now').mockImplementation(() => now);
    const goal = { objective: 'Check live transitions', status: 'active' as const,
      createdAt: startedAt, turns: 1, elapsedSeconds: 2.5, elapsedUpdatedAt: startedAt };
    const view = mount({ goal, verifying: false });
    await wait();
    expect(view.frame()).toContain('(active · 2s · 1 turn)');
    now += 3_000;
    await vi.advanceTimersByTimeAsync(3_000);
    await wait();
    expect(view.frame()).toContain('(active · 5s · 1 turn)');

    const stopped = { ...goal, status: 'blocked' as const, elapsedSeconds: 5.5 };
    view.app.rerender(<GoalStatusBar compact width={80} goalState={{ goal: stopped, verifying: false }} />);
    await wait();
    now += 60_000;
    await vi.advanceTimersByTimeAsync(60_000);
    await wait();
    expect(view.frame()).toContain('(blocked · 5s · 1 turn)');
    const resumed = { ...goal, elapsedSeconds: 5.5, elapsedUpdatedAt: new Date(now).toISOString() };
    view.app.rerender(<GoalStatusBar compact width={80} goalState={{ goal: resumed, verifying: false }} />);
    await wait();
    now += 2_000;
    await vi.advanceTimersByTimeAsync(2_000);
    await wait();
    expect(view.frame()).toContain('In progress (active · 7s · 1 turn)');
  });

  it.each([48, 80])('keeps elapsed time and turns after status at %i columns', async width => {
    vi.spyOn(Date, 'now').mockReturnValue(startMs + 62_000);
    const view = mount({ goal: { objective: '检查目标状态与计时'.repeat(8),
      status: 'active', createdAt: startedAt, turns: 2 }, verifying: false }, width);
    await wait();
    expect(view.frame()).toMatch(/In progress \(active · 1m 2s · 2 turns\)/);
    expect(view.frame().split('\n')).toHaveLength(1);
    expect(stringWidth(view.frame())).toBeLessThanOrEqual(width);
  });

  it('shows initial zero seconds and zero turns', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(startMs);
    const view = mount({ goal: { objective: 'Check initial progress',
      status: 'active', createdAt: startedAt, turns: 0 }, verifying: false });
    await wait();
    expect(view.frame()).toContain('In progress (active · 0s · 0 turns)');
  });

  it('keeps blocked status, time and turns visible in a narrow terminal', async () => {
    const view = mount({ goal: { objective: '核对显示边界'.repeat(10),
      status: 'blocked', elapsedSeconds: 62, turns: 12 }, verifying: false }, 48);
    await wait();
    expect(view.frame()).toContain('Blocked (blocked · 1m 2s · 12 turns)');
    expect(stringWidth(view.frame())).toBeLessThanOrEqual(48);
  });

  it.each(['blocked', 'paused', 'complete'] as const)('freezes %s time across rerenders and remounts', async status => {
    let now = startMs + 100_000;
    vi.spyOn(Date, 'now').mockImplementation(() => now);
    const state = { goal: { objective: 'Check stopped time', status, createdAt: startedAt,
      turns: 3, elapsedSeconds: 12.5, elapsedUpdatedAt: startedAt }, verifying: false };
    const view = mount(state);
    await wait();
    expect(view.frame()).toContain(`(${status} · 12s · 3 turns)`);
    now += 60_000;
    view.app.rerender(<GoalStatusBar compact width={80} goalState={state} notice="Refresh" />);
    await wait();
    expect(view.frame()).toContain(`(${status} · 12s · 3 turns)`);
    const remounted = mount(state);
    await wait();
    expect(remounted.frame()).toContain(`(${status} · 12s · 3 turns)`);
  });

  it('continues from a backend elapsed snapshot when the goal resumes', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(startMs + 3_000);
    const view = mount({ goal: { objective: 'Resume progress', status: 'active',
      createdAt: '2025-01-01T00:00:00Z', turns: 4,
      elapsedSeconds: 12.5, elapsedUpdatedAt: startedAt }, verifying: false });
    await wait();
    expect(view.frame()).toContain('In progress (active · 15s · 4 turns)');
  });

  it.each(['dark', 'light'] as const)('animates Verifying like Thinking in %s', async theme => {
    setActiveTheme(theme);
    chalk.level = 3;
    let now = startMs;
    vi.spyOn(Date, 'now').mockImplementation(() => now);
    const state: GoalState = { goal: { objective: 'Check the animation',
      status: 'active', createdAt: startedAt, turns: 1 }, verifying: true };
    const view = mount(state, 48);
    await wait();
    expect(view.frame()).toContain('◉ Verifying… (active · 0s · 1 turn)');
    const first = view.raw();
    now += 800;
    await wait();
    expect(view.raw()).not.toBe(first);
    expect(view.frame().split('\n')).toHaveLength(1);
    expect(stringWidth(view.frame())).toBeLessThanOrEqual(48);
    view.app.rerender(<GoalStatusBar compact width={48} goalState={{ ...state, verifying: false }} />);
    await wait();
    expect(view.frame()).toContain('In progress');
    expect(view.frame()).not.toContain('◉');
  });

  it.each(
    [46, 80].flatMap(width => (['active', 'blocked', 'paused', 'complete'] as const)
      .map(status => ({ width, status }))),
  )('shows concrete $status state and metrics in $width columns', async ({ width, status }) => {
    const view = mount({ goal: { objective: '核对具体目标状态'.repeat(8),
      status, elapsedSeconds: 62, turns: 2 }, verifying: false }, width);
    await wait();
    expect(view.frame()).toContain(`(${status} · 1m 2s · 2 turns)`);
    expect(view.frame().split('\n')).toHaveLength(1);
    expect(stringWidth(view.frame())).toBeLessThanOrEqual(width);
  });

  it('retains the active state and elapsed time during verification in a narrow terminal', async () => {
    vi.spyOn(Date, 'now').mockReturnValue(startMs);
    const view = mount({ goal: { objective: '核对长时间目标'.repeat(8),
      status: 'active', elapsedSeconds: 3601, elapsedUpdatedAt: startedAt, turns: 12 },
      verifying: true }, 46);
    await wait();
    expect(view.frame()).toContain('◉ Verifying… (active · 60m 1s · 12t)');
    expect(view.frame().split('\n')).toHaveLength(1);
    expect(stringWidth(view.frame())).toBeLessThanOrEqual(46);
  });

  it.each(['blocked', 'paused', 'complete'] as const)('uses a fixed lifecycle end for legacy %s goals', status => {
    const state: GoalState = { goal: { objective: 'Legacy Goal', status,
      createdAt: startedAt, updatedAt: '2026-01-01T00:00:12Z' }, verifying: false };
    expect(goalElapsedSeconds(state, startMs + 60_000)).toBe(12);
    expect(goalElapsedSeconds(state, startMs + 120_000)).toBe(12);
  });

  it('omits unavailable legacy timing and accepts a saved terminal verdict', () => {
    const state: GoalState = { goal: { objective: 'Legacy Goal',
      status: 'blocked', createdAt: 'invalid' }, verifying: false };
    expect(goalElapsedSeconds(state)).toBeUndefined();
    expect(goalElapsedSeconds({ ...state, result: { achieved: false, objective: 'Legacy Goal',
      elapsedSeconds: 12, turns: 1, tokensUsed: 0, reason: 'Stopped' } })).toBe(12);
  });
});
