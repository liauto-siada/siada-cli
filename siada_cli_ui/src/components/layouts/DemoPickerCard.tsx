import React, { useRef, useState } from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { Box, Text, getBoundingBox, type DOMElement } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { colors } from '../../utils/colors.js';

export function DemoPickerCard({ title, items, current, onSelect, onClose, pageHeight, inspectOnly = false }: {
  title: string; items: string[]; current?: string; onSelect: (item: string, index: number) => void; onClose: () => void;
  pageHeight?: number;
  inspectOnly?: boolean;
}) {
  const [index, setIndex] = useState(Math.max(0, items.indexOf(current ?? '')));
  const refs = useRef(new Map<number, DOMElement>());
  const pressed = useRef<number | null>(null);
  useKeypress(key => {
    const point = /^\x1b\[<\d+;(\d+);(\d+)[Mm]$/.exec(key.sequence);
    if (point && ['mousemove', 'mouseclick', 'mouserelease'].includes(key.name)) {
      const x = Number(point[1]) - 1, y = Number(point[2]) - 1;
      const hit = [...refs.current].find(([, node]) => {
        const box = getBoundingBox(node);
        return x >= box.x && x < box.x + box.width && y >= box.y && y < box.y + box.height;
      })?.[0];
      if (key.name === 'mousemove') { if (hit !== undefined) setIndex(hit); }
      else if (key.name === 'mouseclick') { pressed.current = hit ?? null; if (hit !== undefined) setIndex(hit); }
      else if (hit !== undefined && hit === pressed.current) { pressed.current = null; if (!inspectOnly) onSelect(items[hit], hit); }
      return;
    }
    if (key.name === 'escape' || key.ctrl && key.name === 'c') onClose();
    else if (key.name === 'up') setIndex(value => Math.max(0, value - 1));
    else if (key.name === 'down') setIndex(value => Math.min(items.length - 1, value + 1));
    else if (key.name === 'return') { if (!inspectOnly && items[index]) onSelect(items[index], index); }
  });
  const visibleCount = pageHeight ? Math.max(1, pageHeight - 5) : 5;
  const start = Math.max(0, index - visibleCount + 1);
  // Row labels are composed from free-form content (todo text, sub-agent title +
  // status + error summary), so two rows can legitimately render the same text —
  // e.g. the same instruction spawned twice and failing with the same error.
  // A row's identity is therefore its position in the list, not its text: a
  // text-only key makes React warn on every render, and the CLI runs Ink with
  // `patchConsole: false`, so each warning is written straight to the terminal
  // and repaints the whole frame — the picker scrolls itself away while open.
  // Labels are also flattened to one line so a multi-line summary cannot
  // overflow its fixed-height row.
  const label = (item: string) => item.replace(/\s+/g, ' ').trim();
  return <Box flexDirection="column" paddingX={1} height={pageHeight}
    borderStyle={pageHeight ? undefined : 'round'} borderColor={colors.content.border}
    backgroundColor={colors.content.surface}>
    <Box height={2} flexShrink={0}><Text bold>{title}</Text></Box>
    <Box flexGrow={pageHeight ? 1 : 0} flexDirection="column">
    {items.slice(start, start + visibleCount).map((item, offset) => <Box key={start + offset} height={1}
      backgroundColor={index === start + offset && pageHeight ? '#8aa8c8' : undefined}
      ref={node => { if (node) refs.current.set(start + offset, node); else refs.current.delete(start + offset); }}>
      <Text wrap="truncate-end"
      bold={index === start + offset} color={index === start + offset && pageHeight ? '#1f2328' : colors.content.secondary}>
      {index === start + offset ? '›' : ' '} {pageHeight ? `${start + offset + 1}. ` : ''}{label(item)}{item === current ? ' ✓' : ''}
    </Text></Box>)}
    </Box>
    <Text color={colors.content.tertiary} wrap="truncate-end">
      {inspectOnly ? PANEL_TIPS.demoInspect : PANEL_TIPS.demoSelect}
    </Text>
  </Box>;
}