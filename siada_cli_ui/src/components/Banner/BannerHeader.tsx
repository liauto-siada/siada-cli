import React, { useEffect, useRef, useState } from 'react';
import { Box, Text, getBoundingBox, useStdout, type DOMElement } from '@jrichman/ink';
import stringWidth from '../../utils/terminalWidth.js';
import { useKeypress } from '../../hooks/useKeypress.js';
import { useMouseTracking } from '../../hooks/useMouseTracking.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { getActiveTheme, useThemeVersion } from '../../themes/index.js';
import { openExternalUrl } from '../../utils/openExternalUrl.js';
import { logger } from '../../utils/logger.js';
import { BANNER_TITLE_URL } from '../../constants/banner.js';
import { STAR_HINT_FRAME_MS, STAR_HINT_TOTAL_MS, starHintColor, starHintLight, type StarSpan } from './bannerStarHint.js';

export const BANNER_LINKS = [
  { id: 'star', en: '☆ Star', zh: '☆ Star', url: 'https://github.com/liauto-siada/siada-cli' },
  { id: 'doc', en: 'Doc', zh: '使用手册(Doc)', url: 'https://github.com/liauto-siada/siada-cli/blob/develop/docs/USERMANUAL.md' },
  { id: 'help', en: 'Help', zh: '帮助(Help)', url: 'https://github.com/liauto-siada/siada-cli/issues' },
  { id: 'news', en: 'News', zh: '新闻(News)', url: 'https://github.com/liauto-siada/siada-cli/releases' },
] as const;

type Link = typeof BANNER_LINKS[number] & { label: string };
type Point = { x: number; y: number };
type HeaderProps = { columns: number; version?: string; interactive?: boolean };
const BLUE = '#87D7FF';

/** Ancestors may translate or clip a header while the conversation scrolls. */
function isVisible(node: DOMElement, point: Point, rows: number): boolean {
  if (point.y < 0 || point.y >= rows) return false;
  const contains = (element: DOMElement, axis: 'x' | 'y') => {
    const box = getBoundingBox(element);
    return point[axis] >= box[axis] && point[axis] < box[axis] + box[axis === 'x' ? 'width' : 'height'];
  };
  if (!contains(node, 'x') || !contains(node, 'y')) return false;
  let parent = node.parentNode;
  while (parent) {
    if (parent.nodeName === 'ink-box') {
      const overflow = parent.style.overflow ?? 'visible';
      if ((parent.style.overflowX ?? overflow) !== 'visible' && !contains(parent, 'x')) return false;
      if ((parent.style.overflowY ?? overflow) !== 'visible' && !contains(parent, 'y')) return false;
    }
    parent = parent.parentNode;
  }
  return true;
}

function headerLayout(columns: number, version?: string) {
  const title = version ? `Siada CLI v${version}` : 'Siada CLI';
  let links: Link[] = BANNER_LINKS.map(link => ({ ...link, label: t(link.zh, link.en) }));
  const width = (items: Link[]) => items.reduce((sum, link) => sum + stringWidth(link.label) + 2, 0);
  if (stringWidth(title) + width(links) + 6 > columns) {
    links = links.map(link => ({ ...link, label: link.en }));
  }
  if (stringWidth(title) + width(links) + 6 <= columns) return { title, rows: [links], inline: true };
  const rows: Link[][] = [[]];
  let used = 0;
  for (const link of links) {
    const size = stringWidth(link.label) + 2;
    if (used && used + size > Math.max(1, columns - 2)) { rows.push([]); used = 0; }
    rows[rows.length - 1].push(link);
    used += size;
  }
  return { title, rows, inline: false };
}

type LightMap = ((column: number) => number) | null;

/** Play the hint once per mount; only a completed cycle counts, so an interrupted one restarts. */
function useStarHint(enabled: boolean, span: StarSpan): LightMap {
  const [elapsed, setElapsed] = useState<number | null>(null);
  // Startup can briefly disable the banner; only a completed cycle counts.
  const done = useRef(false);
  useEffect(() => {
    if (!enabled) {
      setElapsed(null);
      return;
    }
    if (done.current) return;
    const started = Date.now();
    const timer = setInterval(() => {
      const next = Date.now() - started;
      if (next >= STAR_HINT_TOTAL_MS) {
        clearInterval(timer);
        done.current = true;
        setElapsed(null);
      } else {
        setElapsed(next);
      }
    }, STAR_HINT_FRAME_MS);
    return () => clearInterval(timer);
  }, [enabled]);
  return elapsed === null ? null : column => starHintLight(column, elapsed, span);
}

/** One text node per distinct lit tone; an unlit row stays a single node. */
function LightText({ text, start, color, bold = false, dark, light }: {
  text: string; start: number; color: string; bold?: boolean; dark: boolean; light: LightMap;
}) {
  if (!light) return <Text color={color} bold={bold}>{text}</Text>;
  const runs: { text: string; color: string; bold: boolean }[] = [];
  let column = start;
  for (const character of text) {
    const lit = light(column);
    const runColor = lit > 0.02 ? starHintColor(color, lit, dark) : color;
    const runBold = bold || lit >= 0.5;
    const last = runs[runs.length - 1];
    if (last && last.color === runColor && last.bold === runBold) last.text += character;
    else runs.push({ text: character, color: runColor, bold: runBold });
    column += stringWidth(character);
  }
  return <>{runs.map((run, index) => <Text key={index} color={run.color} bold={run.bold}>{run.text}</Text>)}</>;
}

function HeaderFrame({ columns, version, interactive = false, hovered, nodes }: HeaderProps & {
  hovered?: string | null; nodes?: React.MutableRefObject<Map<string, DOMElement>>;
}) {
  useUiLanguage();
  useThemeVersion();
  const { stdout } = useStdout();
  const light = getActiveTheme() === 'light';
  const layout = headerLayout(columns, version);
  const title = [...layout.title].slice(0, Math.max(0, columns - 2)).join('');
  const firstRow = layout.rows[0] ?? [];
  const prefix = layout.inline ? stringWidth(title) + 3 : 0;
  const used = firstRow.reduce((sum, link) => sum + stringWidth(link.label) + 2, 0);
  const rule = Math.max(0, columns - prefix - used - 2);
  const span: StarSpan = { start: prefix + rule + 1, width: firstRow[0] ? stringWidth(firstRow[0].label) : 0 };
  const hint = useStarHint(
    interactive && Boolean(stdout.isTTY) && !process.env.NO_COLOR && process.env.TERM !== 'dumb', span);
  const titleNode = <Box flexShrink={0}
    ref={nodes ? node => { if (node) nodes.current.set('title', node); else nodes.current.delete('title'); } : undefined}
    backgroundColor={hovered === 'title' ? (light ? '#E7EAEE' : '#303843') : undefined}>
    <LightText text={title} start={2} color={BLUE} bold dark={!light} light={layout.inline ? hint : null} />
  </Box>;
  return <Box flexDirection="column" width={columns} flexShrink={0}>
    {!layout.inline && <Box height={1}><Text color={BLUE}>─ </Text>{titleNode}</Box>}
    {layout.rows.map((links, row) => {
      const used = links.reduce((sum, link) => sum + stringWidth(link.label) + 2, 0);
      const prefix = layout.inline ? stringWidth(title) + 3 : 0;
      const remaining = Math.max(0, columns - prefix - used);
      const lead = Math.max(0, remaining - 2);
      const tail = Math.min(2, remaining);
      const rowHint = row === 0 ? hint : null;
      let column = prefix + lead;
      return <Box key={row} height={1} flexShrink={0} width={columns}>
        {layout.inline && <>
          <LightText text="─ " start={0} color={BLUE} dark={!light} light={rowHint} />
          {titleNode}
          <Text> </Text>
        </>}
        {lead > 0 && <LightText text={'─'.repeat(lead)} start={prefix} color={BLUE} dark={!light} light={rowHint} />}
        {links.map(link => {
          const start = column;
          column += stringWidth(link.label) + 2;
          return <Box key={link.id} flexShrink={0}
            ref={nodes ? node => { if (node) nodes.current.set(link.id, node); else nodes.current.delete(link.id); } : undefined}
            backgroundColor={hovered === link.id ? (light ? '#E7EAEE' : '#303843') : undefined}>
            <LightText text={` ${link.label} `} start={start}
              color={hovered === link.id ? (light ? '#243B4E' : '#EDF5FA') : (light ? '#467692' : '#9AB7CB')}
              dark={!light} light={rowHint} />
          </Box>;
        })}
        {tail > 0 && <Text color={BLUE}>{'─'.repeat(tail)}</Text>}
      </Box>;
    })}
  </Box>;
}

export type BannerLinkState = {
  hovered: string | null;
  nodes: React.MutableRefObject<Map<string, DOMElement>>;
};

/** Share click, clipping and subprocess ownership across banner link surfaces. */
export function BannerLinkInteraction({ columns, links, children }: {
  columns: number;
  links: readonly { id: string; url: string }[];
  children: (state: BannerLinkState) => React.ReactNode;
}) {
  useUiLanguage();
  const { stdout } = useStdout();
  const nodes = useRef(new Map<string, DOMElement>());
  const [hovered, setHovered] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const pointer = useRef<Point | null>(null);
  const pressed = useRef<{ id: string; point: Point } | null>(null);
  const request = useRef<AbortController | null>(null);
  useMouseTracking();
  const hit = (point: Point) => {
    for (const [id, node] of nodes.current) if (isVisible(node, point, stdout.rows ?? 24)) return id;
    return null;
  };
  useEffect(() => {
    if (pointer.current) setHovered(hit(pointer.current));
  });
  useEffect(() => () => { request.current?.abort(); }, []);
  useKeypress(key => {
    const match = /^\x1b\[<(\d+);(\d+);(\d+)([Mm])$/.exec(key.sequence);
    if (!match || !['mousemove', 'mouseclick', 'mouserelease'].includes(key.name) ||
      key.shift || key.alt || key.ctrl) {
      pressed.current = null; pointer.current = null; setHovered(null); return;
    }
    const point = { x: Number(match[2]) - 1, y: Number(match[3]) - 1 };
    const id = hit(point);
    pointer.current = point;
    if (key.name === 'mousemove') {
      const button = Number(match[1]);
      if ((button & 3) !== 3) pointer.current = null;
      setHovered((button & 3) === 3 ? id : null);
      if (pressed.current && (point.x !== pressed.current.point.x || point.y !== pressed.current.point.y)) {
        pressed.current = null;
      }
    } else if (key.name === 'mouseclick') {
      pressed.current = id ? { id, point } : null;
    } else {
      const down = pressed.current;
      pressed.current = null;
      if (!down || down.id !== id || down.point.x !== point.x || down.point.y !== point.y) return;
      const link = links.find(item => item.id === id);
      if (!link) return;
      request.current?.abort();
      const controller = new AbortController();
      request.current = controller;
      setError(false);
      void openExternalUrl(link.url, controller.signal).catch(cause => {
        if (controller.signal.aborted) return;
        logger.warn('Unable to open banner link', { link: link.id, error: String(cause) });
        setError(true);
      });
    }
  });
  return <Box flexDirection="column" width={columns}>
    {children({ hovered, nodes })}
    {error && <Text color="red" wrap="wrap">{t('无法打开链接，请检查系统浏览器设置。', 'Could not open link. Check your system browser settings.')}</Text>}
  </Box>;
}

export function BannerHeader(props: HeaderProps) {
  const { stdout } = useStdout();
  return props.interactive && stdout.isTTY
    ? <BannerLinkInteraction columns={props.columns} links={[{ id: 'title', url: BANNER_TITLE_URL }, ...BANNER_LINKS]}>
      {state => <HeaderFrame {...props} {...state} />}
    </BannerLinkInteraction>
    : <HeaderFrame {...props} />;
}