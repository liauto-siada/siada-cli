import {
  Range, getBoundingBox, getText,
  toStyledCharacters, wrapStyledChars, type DOMElement, type DOMNode, type Selection,
} from '@jrichman/ink';
import Yoga from 'yoga-layout';
import stringWidth from './terminalWidth.js';

export interface SelectionPoint { x: number; y: number }
type TextPoint = { node: Extract<DOMNode, { nodeName: '#text' }>; offset: number };
const graphemes = new Intl.Segmenter(undefined, { granularity: 'grapheme' });
const words = new Intl.Segmenter(undefined, { granularity: 'word' });
export const SELECTION_FRAME_MS = 16;

export interface TextAnchor { id: string; offset: number }
export type SelectionUnit = 'character' | 'word' | 'line';
export interface SelectionTextSource {
  /** Source offsets omit the rendered cursor and preserve logical newlines. */
  text: string;
  fragments: ReadonlyMap<DOMElement, { start: number; end: number }>;
}
export interface SelectionSurface {
  root: DOMElement | null;
  source?: SelectionTextSource;
  onUpdate?: () => void;
}
type Bounds = ReturnType<typeof getBoundingBox>;
interface Leaf { node: TextPoint['node']; start: number; end: number }
interface Glyph { column: number; endColumn: number; start: number; end: number }
interface TextRow { glyphs: Glyph[]; start: number; end: number }
interface Fragment {
  node: DOMElement; text: string; leaves: Leaf[]; rows: TextRow[];
  bounds: Bounds; id: string; start: number;
}
interface VisibleRow { fragment: Fragment; row: TextRow }
interface EntryText { text: string; fragments: Fragment[] }
interface TextBoundaries { graphemes: number[]; words: number[]; lines: number[] }

function lowerBound(values: number[], offset: number): number {
  let low = 0, high = values.length;
  while (low < high) {
    const middle = (low + high) >>> 1;
    if (values[middle] < offset) low = middle + 1;
    else high = middle;
  }
  return low;
}

function leavesOf(node: DOMNode, result: Leaf[], offset: { value: number }): void {
  if (node.nodeName === '#text') {
    const length = toStyledCharacters(node.nodeValue).reduce((sum, char) => sum + char.value.length, 0);
    result.push({ node, start: offset.value, end: offset.value + length });
    offset.value += length;
  } else {
    for (const child of node.childNodes) leavesOf(child, result, offset);
  }
}

function fragmentRows(text: string, width: number, truncate: boolean): TextRow[] {
  const characters = toStyledCharacters(text);
  const offsets = new Map<object, number>();
  let offset = 0;
  for (const character of characters) {
    offsets.set(character, offset);
    offset += character.value.length;
  }
  const lines = truncate ? [characters] : wrapStyledChars(characters, Math.max(1, width));
  let previousEnd = 0;
  return lines.map(line => {
    let column = 0;
    const glyphs: Glyph[] = [];
    for (const character of line) {
      const start = offsets.get(character)!;
      const width = stringWidth(character.value);
      glyphs.push({ column, endColumn: column + width, start, end: start + character.value.length });
      column += width;
    }
    const start = glyphs[0]?.start ?? previousEnd;
    const end = glyphs.at(-1)?.end ?? start;
    previousEnd = end < text.length && text[end] === '\n' ? end + 1 : end;
    return { glyphs, start, end };
  });
}

/** Cache geometry after layout commits; pointer motion only consults the visible row index. */
export class ConversationSelectionLayout {
  readonly entries = new Map<string, EntryText>();
  private readonly fragments = new WeakMap<DOMElement, {
    text: string; width: number; truncate: boolean; rows: TextRow[];
  }>();
  private rows = new Map<number, VisibleRow[]>();
  private clip: Bounds = { x: 0, y: 0, width: 0, height: 0 };

  refresh(
    nodes: ReadonlyMap<string, DOMElement>,
    clip: Bounds,
    sources?: ReadonlyMap<string, SelectionTextSource>,
  ): void {
    this.clip = clip;
    this.rows = new Map();
    this.entries.clear();
    for (const [id, root] of nodes) {
      const entry: EntryText = { text: '', fragments: [] };
      const source = sources?.get(id);
      let sourceStarted = false;
      let previous: Fragment | undefined;
      const visit = (node: DOMElement) => {
        if (node.style.userSelect === 'none') return;
        if (node.nodeName !== 'ink-text') {
          for (const child of node.childNodes) if (child.nodeName !== '#text') visit(child);
          return;
        }
        const bounds = getBoundingBox(node);
        if (!bounds.width || !bounds.height) return;
        const span = source?.fragments.get(node);
        const text = span && source ? source.text.slice(span.start, span.end)
          : toStyledCharacters(getText(node)).map(character => character.value).join('');
        const leaves: Leaf[] = [];
        leavesOf(node, leaves, { value: 0 });
        const yoga = node.yogaNode;
        const width = bounds.width - (yoga?.getComputedPadding(Yoga.EDGE_LEFT) ?? 0) -
          (yoga?.getComputedPadding(Yoga.EDGE_RIGHT) ?? 0);
        const truncate = node.style.textWrap?.startsWith('truncate') ?? false;
        let cached = this.fragments.get(node);
        if (!cached || cached.text !== text || cached.width !== width || cached.truncate !== truncate) {
          cached = { text, width, truncate, rows: fragmentRows(text, width, truncate) };
          this.fragments.set(node, cached);
        }
        if (span && source && !sourceStarted) {
          entry.text = source.text;
          sourceStarted = true;
        } else if (!span && previous && bounds.y >= previous.bounds.y + previous.bounds.height) {
          entry.text += '\n'.repeat(Math.max(1, bounds.y - previous.bounds.y - previous.bounds.height + 1));
        } else if (!span && previous && bounds.x > previous.bounds.x + previous.bounds.width) {
          entry.text += ' '.repeat(bounds.x - previous.bounds.x - previous.bounds.width);
        }
        const fragment: Fragment = { node, id, text, leaves, rows: cached.rows, bounds,
          start: span?.start ?? entry.text.length };
        if (!span) entry.text += text;
        entry.fragments.push(fragment);
        previous = fragment;
        for (let index = 0; index < fragment.rows.length; index++) {
          const y = Math.floor(bounds.y + index);
          if (y < clip.y || y >= clip.y + clip.height) continue;
          const row = this.rows.get(y) ?? [];
          row.push({ fragment, row: fragment.rows[index] });
          this.rows.set(y, row);
        }
      };
      visit(root);
      this.entries.set(id, entry);
    }
    for (const row of this.rows.values()) row.sort((a, b) => a.fragment.bounds.x - b.fragment.bounds.x);
  }

  /** Pointer anchors may begin in padding; multi-click selection requires a visible text glyph. */
  hit(point: SelectionPoint, snap = true, snapRows = true): TextAnchor | undefined {
    const y = Math.max(this.clip.y, Math.min(this.clip.y + this.clip.height - 1, point.y));
    if (!snapRows && point.y !== y) return undefined;
    let rows = this.rows.get(y);
    if (!rows && snap && snapRows) {
      let distance = Infinity;
      for (const [row, candidates] of this.rows) {
        if (Math.abs(row - y) < distance) { rows = candidates; distance = Math.abs(row - y); }
      }
    }
    if (!rows) return undefined;
    let nearest: VisibleRow | undefined, distance = Infinity;
    for (const candidate of rows) {
      const x = candidate.fragment.bounds.x;
      const width = candidate.fragment.bounds.width;
      const next = Math.max(x - point.x, point.x - (x + width - 1), 0);
      if (next < distance) { nearest = candidate; distance = next; }
    }
    if (!nearest || (!snap && (distance > 0 || point.y !== y))) return undefined;
    const { fragment, row } = nearest;
    const x = point.x - fragment.bounds.x;
    let low = 0, high = row.glyphs.length;
    while (low < high) {
      const middle = (low + high) >>> 1;
      if (x >= row.glyphs[middle].endColumn) low = middle + 1;
      else high = middle;
    }
    const glyph = row.glyphs[low];
    if (!snap && (!glyph || x < glyph.column ||
      /^\s*$/u.test(fragment.text.slice(glyph.start, glyph.end)))) return undefined;
    return { id: fragment.id, offset: fragment.start + (glyph?.start ?? row.end) };
  }

  project(from: TextAnchor, to: TextAnchor, order: ReadonlyMap<string, number>): {
    range: Range | undefined; textRanges: Map<DOMElement, { start: number; end: number }>;
  } {
    const textRanges = new Map<DOMElement, { start: number; end: number }>();
    let first: TextPoint | undefined, last: TextPoint | undefined;
    for (const [id, entry] of [...this.entries].sort(([a], [b]) => order.get(a)! - order.get(b)!)) {
      const index = order.get(id)!;
      if (index < order.get(from.id)! || index > order.get(to.id)!) continue;
      const start = id === from.id ? from.offset : 0;
      const end = id === to.id ? to.offset : entry.text.length;
      for (const fragment of entry.fragments) {
        const begin = Math.max(0, start - fragment.start);
        const finish = Math.min(fragment.text.length, end - fragment.start);
        if (begin >= finish || fragment.bounds.y + fragment.bounds.height <= this.clip.y ||
          fragment.bounds.y >= this.clip.y + this.clip.height) continue;
        textRanges.set(fragment.node, { start: begin, end: finish });
        const at = (offset: number, end: boolean): TextPoint | undefined => {
          const leaf = fragment.leaves.find(leaf => end ? offset <= leaf.end : offset < leaf.end) ??
            fragment.leaves.at(-1);
          return leaf ? { node: leaf.node, offset: Math.min(leaf.node.nodeValue.length, Math.max(0, offset - leaf.start)) } : undefined;
        };
        first ??= at(begin, false);
        last = at(finish, true);
      }
    }
    let range: Range | undefined;
    if (first && last) {
      range = new Range();
      range.setStart(first.node, first.offset); range.setEnd(last.node, last.offset);
    }
    return { range, textRanges };
  }
}

/** Source anchors survive remounts and viewport eviction; Ink only receives the visible projection. */
export class ConversationTextSelection {
  readonly order: ReadonlyMap<string, number>;
  private readonly sources = new Map<string, string>();
  private readonly origin: { from: TextAnchor; to: TextAnchor };
  private readonly unit: SelectionUnit;
  private readonly boundaries = new Map<string, TextBoundaries>();
  private from: TextAnchor;
  private to: TextAnchor;

  constructor(
    ids: string[], point: TextAnchor, unit: SelectionUnit, layout: ConversationSelectionLayout,
    private readonly continuations: ReadonlySet<string> = new Set(),
    private readonly toolTreeContinuations: ReadonlySet<string> = new Set(),
  ) {
    this.order = new Map(ids.map((id, index) => [id, index]));
    this.observe(layout);
    this.unit = unit;
    const range = this.span(point);
    this.origin = { from: { id: point.id, offset: range.start }, to: { id: point.id, offset: range.end } };
    this.from = this.origin.from;
    this.to = unit === 'character' ? this.origin.from : this.origin.to;
  }

  observe(layout: ConversationSelectionLayout): void {
    for (const [id, entry] of layout.entries) if (!this.sources.has(id)) this.sources.set(id, entry.text);
  }

  private span(point: TextAnchor): { start: number; end: number } {
    const text = this.sources.get(point.id) ?? '';
    let boundaries = this.boundaries.get(point.id);
    if (!boundaries) {
      const graphemeStarts = [...graphemes.segment(text)].map(part => part.index);
      const wordStarts = [...words.segment(text)].map(part => part.index);
      boundaries = {
        graphemes: [...graphemeStarts, text.length],
        words: [...wordStarts, text.length],
        lines: [0, ...[...text.matchAll(/\n/g)].map(match => match.index! + 1), text.length],
      };
      this.boundaries.set(point.id, boundaries);
    }
    const values = this.unit === 'line' ? boundaries.lines : this.unit === 'word' ? boundaries.words : boundaries.graphemes;
    const offset = Math.max(0, Math.min(text.length, point.offset));
    const candidate = lowerBound(values, offset);
    const index = Math.max(0, values[candidate] === offset ? candidate : candidate - 1);
    const start = values[index], next = values[index + 1] ?? text.length;
    // Character gestures use insertion boundaries with an exclusive end.
    if (this.unit === 'character') return { start, end: start };
    return { start, end: this.unit === 'line' && next > start && text[next - 1] === '\n' ? next - 1 : next };
  }

  get empty(): boolean { return this.from.id === this.to.id && this.from.offset === this.to.offset; }

  /** Unselected live status text may change without invalidating a draft selection. */
  matchesSource(layout: ConversationSelectionLayout): boolean {
    for (const [id, index] of this.order) {
      if (index < this.order.get(this.from.id)! || index > this.order.get(this.to.id)!) continue;
      const source = this.sources.get(id), current = layout.entries.get(id)?.text;
      if (source === undefined || current === undefined) return false;
      const start = id === this.from.id ? this.from.offset : 0;
      const end = id === this.to.id ? this.to.offset : source.length;
      if (source.slice(start, end) !== current.slice(start, end)) return false;
    }
    return true;
  }

  extend(point: TextAnchor, layout: ConversationSelectionLayout): boolean {
    if (!this.sources.has(point.id)) this.observe(layout);
    const span = this.span(point);
    const backward = this.order.get(point.id)! < this.order.get(this.origin.from.id)! ||
      (point.id === this.origin.from.id && point.offset < this.origin.from.offset);
    const from = backward ? { id: point.id, offset: span.start } : this.origin.from;
    const to = backward ? { ...this.origin.to } : { id: point.id, offset: span.end };
    if (this.unit === 'character' && point.id === this.origin.from.id && span.start === this.origin.from.offset) {
      to.offset = from.offset;
    }
    if (this.from.id === from.id && this.from.offset === from.offset &&
      this.to.id === to.id && this.to.offset === to.offset) return false;
    this.from = from; this.to = to;
    return true;
  }

  text(): string {
    let text = '';
    for (const [id, index] of this.order) {
      if (index < this.order.get(this.from.id)! || index > this.order.get(this.to.id)!) continue;
      const source = this.sources.get(id);
      // Never copy a partial range when an intervening entry has not been displayed.
      if (source === undefined) return '';
      if (text && !this.continuations.has(id)) {
        text += this.toolTreeContinuations.has(id) ? '\n' : '\n\n';
      }
      text += source.slice(id === this.from.id ? this.from.offset : 0, id === this.to.id ? this.to.offset : undefined);
    }
    return text.replace(/[ \t]+(?=\n)/g, '');
  }

  paint(layout: ConversationSelectionLayout, selection: Selection | undefined): void {
    if (!selection) return;
    if (this.empty) { selection.setRange(undefined); return; }
    const { range, textRanges } = layout.project(this.from, this.to, this.order);
    selection.setRange(range ?? (selection.rangeCount ? selection.getRangeAt(0) : undefined), textRanges);
  }
}

/** Replace queued pointer positions rather than processing every motion event. Release always flushes. */
export function createSelectionFrame(update: (point: SelectionPoint) => void) {
  let pending: SelectionPoint | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const flush = () => {
    if (timer) clearTimeout(timer);
    timer = undefined;
    const point = pending; pending = undefined;
    if (point) update(point);
  };
  return {
    queue(point: SelectionPoint) {
      pending = point;
      timer ??= setTimeout(flush, SELECTION_FRAME_MS);
    },
    flush,
    cancel() { if (timer) clearTimeout(timer); timer = undefined; pending = undefined; },
  };
}