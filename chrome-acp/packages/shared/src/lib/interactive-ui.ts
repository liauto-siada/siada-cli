export interface InteractiveUiReference {
  id: string;
  title: string;
  revision?: string;
}

export type InteractiveMessagePart =
  | { type: "text"; text: string }
  | { type: "ui"; page: InteractiveUiReference };

const PAGE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** Only complete, valid fences become executable views, including during streaming. */
export function splitInteractiveMessage(text: string): InteractiveMessagePart[] {
  const parts: InteractiveMessagePart[] = [];
  const fences = /(?:^|\n)```siada-ui[ \t]*\r?\n([\s\S]*?)\r?\n```(?=\s|$)/g;
  let end = 0;
  for (const match of text.matchAll(fences)) {
    try {
      const page = JSON.parse(match[1]!) as InteractiveUiReference;
      if (!PAGE_ID.test(page.id) || typeof page.title !== "string" || !page.title.trim() || page.title.length > 200) continue;
      if (match.index! > end) parts.push({ type: "text", text: text.slice(end, match.index) });
      parts.push({ type: "ui", page: { id: page.id, title: page.title, ...(typeof page.revision === "string" && /^[0-9a-f]{64}$/.test(page.revision) ? { revision: page.revision } : {}) } });
      end = match.index! + match[0].length;
    } catch { /* Malformed model output stays readable as Markdown. */ }
  }
  if (end < text.length) parts.push({ type: "text", text: text.slice(end) });
  return parts;
}

/** Decode only the SDK's text dictionary repr; never evaluate Python literals. */
function sdkTextDictionary(text: string): string | null {
  const prefix = /^\{\s*(['"])type\1\s*:\s*(['"])text\2\s*,\s*(['"])text\3\s*:\s*(['"])/.exec(text);
  if (!prefix) return null;
  const quote = prefix[4];
  let result = "";
  for (let index = prefix[0].length; index < text.length; index++) {
    const char = text[index]!;
    if (char === quote) return /^\s*\}$/.test(text.slice(index + 1)) ? result : null;
    if (char !== "\\") { result += char; continue; }
    const escaped = text[++index];
    const simple: Record<string, string> = { n: "\n", r: "\r", t: "\t", b: "\b", f: "\f", v: "\v", a: "\x07", "\\": "\\", "'": "'", '"': '"' };
    if (escaped && Object.hasOwn(simple, escaped)) { result += simple[escaped]; continue; }
    const count = escaped === "x" ? 2 : escaped === "u" ? 4 : escaped === "U" ? 8 : 0;
    if (!count) return null;
    const hex = text.slice(index + 1, index + 1 + count);
    if (hex.length !== count || !/^[0-9a-f]+$/i.test(hex)) return null;
    const point = Number.parseInt(hex, 16);
    if (point > 0x10ffff) return null;
    result += String.fromCodePoint(point);
    index += count;
  }
  return null;
}

/** Read each ACP/MCP block before display formatting joins progress and output. */
export function interactiveToolText(output: unknown): string {
  const seen = new WeakSet<object>();
  function read(value: unknown, depth: number): string {
    if (depth > 24 || value == null) return "";
    if (typeof value === "string") {
      try { return read(JSON.parse(value), depth + 1); } catch { /* Plain text or an SDK repr. */ }
      const decoded = sdkTextDictionary(value.trim());
      if (decoded !== null) return read(decoded, depth + 1);
      return value.split(/\r?\n/).map(line => {
        const block = sdkTextDictionary(line.trim());
        return block === null ? line : read(block, depth + 1);
      }).join("\n");
    }
    if (typeof value !== "object" || seen.has(value)) return "";
    seen.add(value);
    if (Array.isArray(value)) return value.map(item => read(item, depth + 1)).join("\n");
    const block = value as Record<string, unknown>;
    if (block.type === "text" && typeof block.text === "string") return read(block.text, depth + 1);
    if (block.content) return read(block.content, depth + 1);
    if (block.result) return read(block.result, depth + 1);
    return "";
  }
  return read(output, 0);
}

export function interactiveToolReferences(content: unknown, rawOutput?: unknown): InteractiveUiReference[] {
  const references = (value: unknown) => splitInteractiveMessage(interactiveToolText(value))
    .flatMap(part => part.type === "ui" ? [part.page] : []);
  const fromContent = references(content);
  const pages = fromContent.length ? fromContent : references(rawOutput);
  return [...new Map(pages.map(page => [page.id, page])).values()];
}

export function uiActionPrompt(page: InteractiveUiReference, prompt: string, state: Record<string, unknown>): string {
  return `${prompt.trim()}\n\n<siada-ui-action>\n${JSON.stringify({ id: page.id, title: page.title, state })}\n</siada-ui-action>`;
}

export function validUiState(state: unknown): state is Record<string, unknown> {
  try {
    return !!state && typeof state === "object" && !Array.isArray(state) && new TextEncoder().encode(JSON.stringify(state)).length <= 65536;
  } catch { return false; }
}