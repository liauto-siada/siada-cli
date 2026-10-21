/**
 * Decode one layer of HTML entities at the display boundary.
 * Keep unknown entities and terminal control characters literal.
 */
const namedEntities: Record<string, string> = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00a0',
  AMP: '&', LT: '<', GT: '>', QUOT: '"',
  ndash: '–', mdash: '—', hellip: '…', copy: '©', reg: '®',
  trade: '™', bull: '•', middot: '·', laquo: '«', raquo: '»',
  lsquo: '‘', rsquo: '’', ldquo: '“', rdquo: '”',
};

export function decodeHtmlEntities(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z][a-z0-9]+);/gi, (entity, name: string) => {
    if (!name.startsWith('#')) return Object.hasOwn(namedEntities, name) ? namedEntities[name] : entity;
    const hex = /^#x/i.test(name);
    const point = Number.parseInt(name.slice(hex ? 2 : 1), hex ? 16 : 10);
    // Decoding escape/newline entities must not inject terminal commands or rows.
    if (point < 0x20 || (point >= 0x7f && point <= 0x9f)
      || point > 0x10ffff || (point >= 0xd800 && point <= 0xdfff)
      || point === 0x2028 || point === 0x2029) return entity;
    return String.fromCodePoint(point);
  });
}