import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Box, Text, getBoundingBox, getText, type DOMElement } from '@jrichman/ink';
import stringWidth from '../../utils/terminalWidth.js';
import stripAnsi from 'strip-ansi';
import { useKeypress } from '../../hooks/useKeypress.js';
import { colors } from '../../utils/colors.js';
import { getActiveTheme, useThemeVersion } from '../../themes/index.js';
import type { GoalState, TodoItem, SubAgentItem } from '../../hooks/useAcp/types.js';
import { SpotlightThinking } from '../common/SpotlightThinking.js';
import { GoalStatusBar } from '../Goal/GoalStatusBar.js';
import { TodoDisplay } from '../Todo/TodoDisplay.js';
import { getTodoFocusIndex, getTodoVisibleRange } from '../../utils/todoDisplay.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { SubAgentDisplay } from '../SubAgent/SubAgentDisplay.js';
import { DisclosureArrow } from '../common/DisclosureArrow.js';

interface Props {
  goalState?: GoalState | null;
  tasks: TodoItem[];
  agents: SubAgentItem[];
  width: number;
  rows: number;
  onTask: (content: string) => void;
  onAgent: (id: string) => void;
  expanded: string | null;
  onExpandedChange: (section: string | null) => void;
  active?: boolean;
  focusedSection?: string | null;
  onFocusChange?: (section: string | null) => void;
  placement?: 'all' | 'above' | 'below';
  goalNotice?: string | null;
  onHoverTipChange?: (tip: string | null) => void;
}

/** Preview progressive disclosure without changing the production presentation. */
export function DemoWorkStatus({ goalState, tasks, agents, width, rows, onTask, onAgent,
  expanded, onExpandedChange, active = true, focusedSection, onFocusChange, placement = 'all', goalNotice,
  onHoverTipChange }: Props) {
  useThemeVersion();
  const uiLanguage = useUiLanguage();
  const [hovered, setHovered] = useState<string | null>(null);
  const [focused, setFocused] = useState(0);
  const [selectedTask, setSelectedTask] = useState<string | null>(null);
  const taskFocused = active && focusedSection === 'tasks';
  const selectedIndex = tasks.findIndex(task => task.content === selectedTask);
  const taskIndex = taskFocused && selectedIndex >= 0 ? selectedIndex : getTodoFocusIndex(tasks);
  useEffect(() => {
    if (!taskFocused) setSelectedTask(null);
  }, [taskFocused]);
  const refs = useRef(new Map<string, DOMElement>());
  const down = useRef<{ id: string | null; x: number; y: number; moved: boolean } | null>(null);
  const goalLabelRef = useCallback((node: DOMElement | null) => {
    if (node) refs.current.set('goal', node);
    else refs.current.delete('goal');
  }, []);
  useEffect(() => {
    if (!active) { setHovered(null); down.current = null; }
  }, [active]);
  useEffect(() => {
    const name = hovered === 'goal' ? 'Goal' : hovered === 'agents' ? t('智能体', 'Agents') : null;
    const englishTip = `Click to ${expanded === hovered ? 'close' : 'view'} ${name}`;
    const scrollTip = hovered === 'todo-up' ? t('向上滚动待办清单', 'Scroll Todo up')
      : hovered === 'todo-down' ? t('向下滚动待办清单', 'Scroll Todo down') : null;
    onHoverTipChange?.(active && scrollTip ? scrollTip : active && name ? hovered === 'goal' ? englishTip
      : t(`点击${expanded === hovered ? '收起' : '查看'}${name}`, englishTip) : null);
    return () => onHoverTipChange?.(null);
  }, [active, hovered, expanded, onHoverTipChange, uiLanguage]);
  const goal = goalState?.goal;
  const sections = [goal ? 'goal' : '', tasks.length ? 'tasks' : '', agents.length ? 'agents' : ''].filter(Boolean);
  const done = tasks.filter(task => task.status === 'completed').length;
  const todoRange = getTodoVisibleRange(tasks, taskFocused ? taskIndex : -1);
  const scrollTodo = (direction: number) => {
    const nextStart = Math.max(0, Math.min(tasks.length - Math.min(3, tasks.length),
      todoRange.start + direction));
    if (nextStart === todoRange.start) return;
    setSelectedTask(tasks[nextStart + 1]?.content ?? tasks[nextStart]?.content ?? null);
    onFocusChange?.('tasks');
  };
  const running = agents.filter(agent => agent.status === 'running').length;
  const failed = agents.filter(agent => agent.status === 'failed').length;
  const completed = agents.filter(agent => agent.status === 'completed').length;
  const currentTask = tasks.find(task => task.status === 'in_progress') ?? tasks.find(task => task.status === 'pending');
  const state = goalState?.verifying ? '验证中' : goal?.status === 'complete' ? '已完成'
    : goal?.status === 'blocked' ? '待处理' : '进行中';
  const tone = goal?.status === 'complete' ? colors.success : goal?.status === 'blocked' ? colors.error : colors.content.secondary;
  const activate = (id: string) => {
    if (id === 'todo-up') { scrollTodo(-1); return; }
    if (id === 'todo-down') { scrollTodo(1); return; }
    if (id === 'tasks' || id.startsWith('task:')) return;
    else if (id.startsWith('agent:')) onAgent(agents[Number(id.slice(6))].id);
    else onExpandedChange(expanded === id ? null : id);
  };
  useKeypress(key => {
    if (placement === 'below' && !['mousemove', 'mouseclick', 'mouserelease'].includes(key.name)) return;
    const match = /^\x1b\[<\d+;(\d+);(\d+)[Mm]$/.exec(key.sequence);
    if (match && ['mousemove', 'mouseclick', 'mouserelease'].includes(key.name)) {
      const x = Number(match[1]) - 1, y = Number(match[2]) - 1;
      const target = [...refs.current].find(([id, node]) => {
        const bounds = getBoundingBox(node);
        const textWidth = id.startsWith('todo-') ? bounds.width : stringWidth(stripAnsi(getText(node)));
        return x >= bounds.x && x < bounds.x + Math.min(bounds.width, textWidth) &&
          y >= bounds.y && y < bounds.y + bounds.height;
      })?.[0] ?? null;
      setHovered(target);
      if (down.current && (down.current.x !== x || down.current.y !== y)) down.current.moved = true;
      if (key.name === 'mouseclick') down.current = { id: target, x, y, moved: false };
      if (key.name === 'mouserelease') {
        if (target && target === down.current?.id && !down.current.moved) activate(target);
        down.current = null;
      }
    }
    if (focusedSection) {
      if (key.name === 'escape' || key.ctrl && key.name === 'c') {
        onFocusChange?.(null);
        return;
      }
      if (key.name === 'return') { activate(focusedSection); return; }
      if (key.name === 'tab') {
        const index = sections.indexOf(focusedSection);
        const next = index + (key.shift ? -1 : 1);
        onFocusChange?.(sections[next] ?? null);
        return;
      }
      if (key.name === 'up' || key.name === 'down') {
        if (focusedSection === 'tasks') {
          const next = Math.max(0, Math.min(tasks.length - 1,
            taskIndex + (key.name === 'up' ? -1 : 1)));
          setSelectedTask(tasks[next]?.content ?? null);
          return;
        }
        const index = sections.indexOf(focusedSection);
        onFocusChange?.(sections[Math.max(0, Math.min(sections.length - 1, index + (key.name === 'up' ? -1 : 1)))]);
        return;
      }
    }
    if (key.alt && key.name === 's') {
      const next = (focused + 1) % Math.max(1, sections.length);
      setFocused(next);
      if (sections[next] === 'tasks') onFocusChange?.('tasks');
      else onExpandedChange(sections[next]);
    }
  }, { isActive: active });
  const hoverTone = getActiveTheme() === 'dark' ? '#d0d7df' : '#39424e';
  const label = (id: string, text: React.ReactNode) => <Box key={id} height={1} flexShrink={0}>
    <Box
    ref={node => { if (node) refs.current.set(id, node); else refs.current.delete(id); }}
    backgroundColor={hovered === id ? colors.content.surface : undefined} flexShrink={1}>
    <Text wrap="truncate-end" bold={hovered === id}
      color={hovered === id ? hoverTone : colors.content.secondary}>{text}</Text>
    </Box>
  </Box>;
  const summaryRow = (id: string, name: string, description: string, status: React.ReactNode) =>
    <Box key={id} height={1} flexShrink={0}
      backgroundColor={focusedSection === id ? '#8aa8c8' : undefined}>
      <Box flexShrink={1} overflowX="hidden"
        ref={node => { if (node) refs.current.set(id, node); else refs.current.delete(id); }}
        backgroundColor={hovered === id && focusedSection !== id ? colors.content.surface : undefined}>
      <Box width={id === 'tasks' ? undefined : 9} flexShrink={0}>
        <Text color={focusedSection === id ? '#1f2328' : hovered === id ? hoverTone : colors.content.secondary}
          bold>
          <DisclosureArrow glyph={expanded === id ? '⌃' : '›'} hovered={hovered === id && focusedSection !== id}
            idleColor={focusedSection === id ? '#1f2328' : undefined} /> {name}
        </Text>
      </Box>
      <Box flexShrink={1} overflowX="hidden">
        <Text wrap="truncate-end" bold={focusedSection === id || hovered === id}
          color={focusedSection === id ? '#1f2328' : hovered === id ? hoverTone : colors.content.secondary}>{description}</Text>
      </Box>
      </Box>
      {id !== 'tasks' && <Box flexGrow={1} />}
      <Box flexShrink={0} marginLeft={1}><Text color={colors.content.secondary}>{status}</Text></Box>
    </Box>;
  const itemRow = (id: string, title: string, status: string, tone: string, last = false) => label(id,
    <><Text color={colors.content.tertiary}>{last ? '└─ ' : '├─ '}</Text>
      <Text color={tone}>{status === '完成' ? '✓' : status === '失败' ? '!' : status === '进行中' ? '◉' : '○'}</Text>
      {' '}<Text>{title}</Text><Text color={tone}> · {status}</Text>{id.startsWith('task:') ? '' :
        <>{' '}<DisclosureArrow glyph="›" hovered={hovered === id} /></>}</>);
  const previewLimit = 3;
  const previewTasks = tasks.map((task, index) => ({ task, index }))
    .slice(0, previewLimit);
  const previewAgents = agents.map((agent, index) => ({ agent, index }))
    .sort((a, b) => Number(b.agent.status === 'failed') - Number(a.agent.status === 'failed') ||
      Number(b.agent.status === 'running') - Number(a.agent.status === 'running')).slice(0, previewLimit);
  const scrollButton = (id: string, symbol: string, enabled: boolean) => <Box marginLeft={1} userSelect="none"
    ref={node => { if (node && enabled) refs.current.set(id, node); else refs.current.delete(id); }}
    backgroundColor={enabled && hovered === id ? colors.content.surface : undefined}>
    <DisclosureArrow glyph={symbol} hovered={enabled && hovered === id}
      idleColor={enabled ? undefined : colors.content.tertiary} />
  </Box>;
  return <Box width={width} paddingRight={1} flexDirection="column">
    {placement !== 'below' && (goal || goalNotice) && <Box height={1} flexShrink={0}
      backgroundColor={focusedSection === 'goal' ? '#8aa8c8' : undefined}>
      <GoalStatusBar goalState={goalState ?? null} width={width - 1} isCollapsed compact notice={goalNotice}
        onLabelRef={goalLabelRef} hoverColor={hovered === 'goal' ? hoverTone : undefined} />
    </Box>}
    {placement !== 'below' && tasks.length > 0 && <Box height={1} flexShrink={0}
      backgroundColor={taskFocused ? '#8aa8c8' : undefined}>
      <Text bold color={taskFocused ? '#1f2328' : colors.content.secondary}>› Todo</Text>
      <Box marginLeft={1}><Text color={colors.content.secondary}>{done}/{tasks.length}</Text></Box>
      {scrollButton('todo-up', '▲', todoRange.start > 0)}
      {scrollButton('todo-down', '▼', todoRange.end < tasks.length)}
    </Box>}
    {placement !== 'below' && tasks.length > 0 && <TodoDisplay items={tasks}
      activeIndex={taskFocused ? taskIndex : -1}
      width={width - 1} compact onSelect={() => {}} onClose={() => {}} />}
    {placement !== 'above' && agents.length > 0 && <Box flexDirection="column">
      {summaryRow('agents', 'Agents', '', `${agents.length}`)}
      <SubAgentDisplay items={agents} activeIndex={-1} width={width - 1} compact />
    </Box>}
  </Box>;
}