// MCP (Model Context Protocol) Types for Streamable HTTP Transport

// ============================================================================
// Browser Tool Types
// ============================================================================
// IMPORTANT: These types MUST stay in sync with @chrome-acp/shared/src/acp/types.ts
// They define the protocol between proxy-server and browser extension.
//
// Why duplicated? proxy-server uses NodeNext module resolution which requires
// .js extensions, while shared package is designed for bundlers (Bun/Vite).
// Until we have a proper @chrome-acp/protocol package, keep these in sync manually.
// ============================================================================

export interface BrowserToolParams {
  action: "tabs" | "read" | "execute" | "replay" | "screenshot" | "paragraphs" | "annotate" | "pdf_render";
  tabId?: number;   // Required for read/execute/replay/screenshot/paragraphs/annotate
  script?: string;  // Required for execute
  step?: ReplayStep; // Required for replay
  offset?: number;  // Optional for read: char offset into the serialized DOM (default 0)
  limit?: number;   // Optional for read: max chars of DOM to return (default 50000)
  maxWidth?: number; // Optional for screenshot: downscale to this width in px (default 1280)
  quality?: number;  // Optional for screenshot: JPEG quality 0-100 (default 70)
  items?: AnnotateItem[]; // For annotate: translation/explanation blocks to insert
  clear?: boolean;  // For annotate: remove all previously injected annotations
  pdfUrl?: string;  // Required for pdf_render: http/https/file URL of the PDF document
  page?: number;    // Optional for pdf_render: initial page to scroll to
}

// Mirrors AnnotateItem in packages/shared/src/acp/types.ts
export interface AnnotateItem {
  index?: number;
  text: string;
  kind?: "translation" | "explanation";
}

// Mirrors ReplayStep in packages/shared/src/acp/types.ts
export interface ReplayStep {
  kind: "click" | "input" | "select" | "keydown" | "scroll" | "navigate";
  target?: {
    tag: string;
    selector: string;
    xpath: string;
    text?: string;
    role?: string;
    ariaLabel?: string;
  };
  value?: string;
  key?: string;
  url?: string;
  scrollX?: number;
  scrollY?: number;
}

export interface BrowserTabInfo {
  id: number;
  url: string;
  title: string;
  active: boolean;
}

export interface BrowserTabsResult {
  action: "tabs";
  tabs: BrowserTabInfo[];
}

export interface BrowserReadResult {
  action: "read";
  tabId: number;
  url: string;
  title: string;
  dom: string;
  // Pagination: dom is the slice [domOffset, domOffset + dom.length) of the
  // full serialized DOM, which is domTotalLength chars long.
  domTotalLength: number;
  domOffset: number;
  hasMore: boolean;
  viewport: {
    width: number;
    height: number;
    scrollX: number;
    scrollY: number;
  };
  selection: string | null;
}

export interface BrowserExecuteResult {
  action: "execute";
  tabId: number;
  url: string;
  result?: unknown;
  error?: string;
}

export interface BrowserReplayResult {
  action: "replay";
  tabId: number;
  url: string;
  ok: boolean;
  error?: string;
  response?: string;
}

export interface BrowserScreenshotResult {
  action: "screenshot";
  tabId: number;
  url: string;
  title: string;
  /** Base64-encoded JPEG (no data: prefix), downscaled to <= maxWidth */
  data: string;
  mimeType: "image/jpeg";
  /** Pixel dimensions of the returned image */
  width: number;
  height: number;
}

// Mirrors BrowserParagraph / BrowserParagraphsResult / BrowserAnnotateResult
// in packages/shared/src/acp/types.ts
export interface BrowserParagraph {
  index: number;
  tag: string;
  text: string;
}

export interface BrowserParagraphsResult {
  action: "paragraphs";
  tabId: number;
  url: string;
  title: string;
  paragraphs: BrowserParagraph[];
  truncated: boolean;
}

export interface BrowserAnnotateResult {
  action: "annotate";
  tabId: number;
  url: string;
  inserted: number;
  missing: number[];
  cleared: boolean;
}

// Mirrors BrowserPdfRenderResult in packages/shared/src/acp/types.ts
export interface BrowserPdfRenderResult {
  action: "pdf_render";
  tabId: number;
  /** The chrome-extension:// viewer URL opened in the tab */
  url: string;
  /** The original PDF document URL */
  pdfUrl: string;
  /** Total page count, present when status is "loaded" */
  pages?: number;
  /** Document title (PDF metadata Title), present when status is "loaded" */
  title?: string;
  /** "loaded": viewer confirmed pagesloaded; "opened": tab opened but the
   * load-wait timed out (large/slow document) — the viewer may still be
   * rendering. */
  status: "loaded" | "opened";
}

export type BrowserToolResult =
  | BrowserTabsResult
  | BrowserReadResult
  | BrowserExecuteResult
  | BrowserReplayResult
  | BrowserScreenshotResult
  | BrowserParagraphsResult
  | BrowserAnnotateResult
  | BrowserPdfRenderResult;

export interface McpRequest {
  jsonrpc: "2.0";
  id: string | number;
  method: string;
  params?: Record<string, unknown>;
}

export interface McpResponse {
  jsonrpc: "2.0";
  id: string | number;
  result?: unknown;
  error?: McpError;
}

export interface McpError {
  code: number;
  message: string;
  data?: unknown;
}

// MCP Protocol Methods
export const MCP_METHODS = {
  INITIALIZE: "initialize",
  TOOLS_LIST: "tools/list",
  TOOLS_CALL: "tools/call",
} as const;

// MCP Initialize
export interface McpInitializeParams {
  protocolVersion: string;
  capabilities: {
    roots?: { listChanged?: boolean };
    sampling?: Record<string, never>;
  };
  clientInfo: {
    name: string;
    version: string;
  };
}

export interface McpInitializeResult {
  protocolVersion: string;
  capabilities: {
    tools?: { listChanged?: boolean };
  };
  serverInfo: {
    name: string;
    version: string;
  };
}

// MCP Tools
export interface McpTool {
  name: string;
  description: string;
  inputSchema: {
    type: "object";
    properties: Record<string, unknown>;
    required?: string[];
  };
}

export interface McpToolsListResult {
  tools: McpTool[];
}

export interface McpToolCallParams {
  name: string;
  arguments?: Record<string, unknown>;
}

export interface McpToolCallResult {
  content: McpToolContent[];
  isError?: boolean;
}

export type McpToolContent =
  | { type: "text"; text: string }
  | { type: "image"; data: string; mimeType: string };

// Browser Tabs Tool
export const BROWSER_TABS_TOOL: McpTool = {
  name: "browser_tabs",
  description:
    "List all open tabs in the browser. " +
    "Returns an array of tabs with their id, url, title, and whether it's the active tab. " +
    "Use this tool first to get the tabId before calling browser_read or browser_execute.",
  inputSchema: {
    type: "object",
    properties: {},
  },
};

// Browser Read Tool
export const BROWSER_READ_TOOL: McpTool = {
  name: "browser_read",
  description:
    "Read the content of a specific browser tab. " +
    "Returns page URL, title, simplified DOM content, viewport size, and selected text. " +
    "The DOM content is paginated: by default only the first 50000 chars are returned. " +
    "The response includes domTotalLength and hasMore — use offset/limit to read further sections. " +
    "PDF VIEWER TABS (chrome-extension://…/viewer.html, opened via browser_pdf_render): returns the " +
    "current page's full text (from the embedded pdf.js) plus page/pages state — the right tool " +
    "for interactive reading. For BULK full-document analysis prefer the preinstalled `pymupdf` " +
    "(see browser_pdf_render); use browser_paragraphs on the tab to get ALL pages' text, " +
    "browser_screenshot to visually inspect a rendered page (figures/diagrams), and " +
    'browser_execute with {"cmd":"goto","page":N} to turn pages. ' +
    "IMPORTANT: You must call browser_tabs first to get the tabId.",
  inputSchema: {
    type: "object",
    properties: {
      tabId: {
        type: "number",
        description:
          "The tab ID to read from. Get this from browser_tabs tool.",
      },
      offset: {
        type: "number",
        description:
          "Char offset into the serialized DOM content (default 0). " +
          "Use the value of offset + returned chars from a previous call to continue reading.",
      },
      limit: {
        type: "number",
        description:
          "Max chars of DOM content to return (default 50000).",
      },
    },
    required: ["tabId"],
  },
};

// Browser Execute Tool
export const BROWSER_EXECUTE_TOOL: McpTool = {
  name: "browser_execute",
  description:
    "Execute JavaScript code in a specific browser tab. " +
    "The script is executed via `new Function(script)()`, so the LAST EXPRESSION or explicit `return` statement becomes the tool result. " +
    "On PDF VIEWER tabs (opened via browser_pdf_render) arbitrary scripts are forbidden by " +
    "the extension CSP — pass a JSON command instead: {\"cmd\":\"state\"} (page/scale/rotation/annotation count), " +
    "{\"cmd\":\"goto\",\"page\":N}, {\"cmd\":\"zoom\",\"scale\":1.5|\"page-fit\"}, {\"cmd\":\"rotate\",\"deg\":90}, " +
    "{\"cmd\":\"save\"} (download annotated copy). " +
    "IMPORTANT: You must call browser_tabs first to get the tabId.",
  inputSchema: {
    type: "object",
    properties: {
      tabId: {
        type: "number",
        description:
          "The tab ID to execute the script in. Get this from browser_tabs tool.",
      },
      script: {
        type: "string",
        description:
          "JavaScript code to execute in the page context.\n\n" +
          "EXECUTION MODEL:\n" +
          "Your script runs as: `(new Function(script))()`. The return value becomes the tool result.\n" +
          "- Use `return { success: true, ... }` to report success with details\n" +
          "- Use `return { success: false, reason: '...' }` to report failure\n" +
          "- If no return, result will be undefined\n\n" +
          "EXAMPLE - Good script with clear return value:\n" +
          "```\n" +
          "const btn = document.querySelector('button.submit');\n" +
          "if (!btn) return { success: false, reason: 'Button not found' };\n" +
          "btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));\n" +
          "return { success: true, clicked: btn.textContent };\n" +
          "```\n\n" +
          "EVENT HANDLING for React/Vue/Angular:\n\n" +
          "1. CLICKING - Do NOT use element.click():\n" +
          "   element.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));\n\n" +
          "2. INPUT FIELDS - Setting .value alone won't work:\n" +
          "   input.value = 'text';\n" +
          "   input.dispatchEvent(new Event('input', { bubbles: true }));\n" +
          "   input.dispatchEvent(new Event('change', { bubbles: true }));\n\n" +
          "3. FORM SUBMIT - Do NOT use form.submit() (bypasses validation):\n" +
          "   form.dispatchEvent(new SubmitEvent('submit', { bubbles: true, cancelable: true }));\n\n" +
          "4. HOVER: element.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true, view: window }));\n\n" +
          "5. KEYBOARD: element.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));\n\n" +
          "Always use dispatchEvent with { bubbles: true } for framework compatibility.",
      },
    },
    required: ["tabId", "script"],
  },
};

// Browser Replay Tool
export const BROWSER_REPLAY_TOOL: McpTool = {
  name: "browser_replay",
  description:
    "Replay one recorded pipeline step (click/input/select/keydown/scroll/navigate) in a specific browser tab. " +
    "The target element is located by trying css selector, then xpath, then visible text. " +
    "Returns ok=true with a summary of the DOM changes the step triggered, or ok=false with error " +
    "(e.g. element_not_found) — in that case fall back to browser_read/browser_execute and complete the step autonomously. " +
    "IMPORTANT: You must call browser_tabs first to get the tabId.",
  inputSchema: {
    type: "object",
    properties: {
      tabId: {
        type: "number",
        description: "The tab ID to replay in. Get this from browser_tabs tool.",
      },
      step: {
        type: "object",
        description:
          "The pipeline step. kind: click|input|select|keydown|scroll|navigate. " +
          "target: {tag, selector, xpath, text?} for element steps. " +
          "value for input/select ('true'/'false' for checkbox), key for keydown, url for navigate, scrollX/scrollY for scroll.",
        properties: {
          kind: { type: "string" },
          target: { type: "object" },
          value: { type: "string" },
          key: { type: "string" },
          url: { type: "string" },
          scrollX: { type: "number" },
          scrollY: { type: "number" },
        },
        required: ["kind"],
      },
    },
    required: ["tabId", "step"],
  },
};

// Browser Screenshot Tool
export const BROWSER_SCREENSHOT_TOOL: McpTool = {
  name: "browser_screenshot",
  description:
    "Capture a screenshot of a browser tab's visible viewport and return it as an image. " +
    "Use this after actions (browser_execute/browser_replay) to visually verify the page state " +
    "when the text DOM is not enough — e.g. layout, styling, charts, canvas, or to confirm an effect actually rendered. " +
    "Requires a vision-capable model to interpret the image. " +
    "NOTE: the tab will be activated and its window focused before capture. " +
    "IMPORTANT: You must call browser_tabs first to get the tabId.",
  inputSchema: {
    type: "object",
    properties: {
      tabId: {
        type: "number",
        description: "The tab ID to capture. Get this from browser_tabs tool.",
      },
      maxWidth: {
        type: "number",
        description:
          "Downscale the screenshot to this width in px to reduce token cost (default 1280). " +
          "Raise it when you need fine detail (e.g. reading small text).",
      },
      quality: {
        type: "number",
        description: "JPEG quality 0-100 (default 70).",
      },
    },
    required: ["tabId"],
  },
};

// Browser Paragraphs Tool
export const BROWSER_PARAGRAPHS_TOOL: McpTool = {
  name: "browser_paragraphs",
  description:
    "Extract the main readable paragraphs of a page as an indexed list, for immersive " +
    "translation/explanation. Each returned paragraph is tagged inside the page with a " +
    "stable index; pass that index to browser_annotate to render content below it. " +
    "On PDF VIEWER TABS (opened via browser_pdf_render) this returns ONE entry per PAGE " +
    "(index = 1-based page number) with that page's full text — document-wide reading without " +
    "local tooling; for BULK analysis (search/tables/metadata) the preinstalled `pymupdf` " +
    "(see browser_pdf_render) is usually faster. " +
    "WHEN TO USE: whenever the user asks to translate the page/article/paper (翻译论文, " +
    "翻译这个页面, immersive translate) or to explain the page section by section — call " +
    "this first, then render with browser_annotate. " +
    "IMPORTANT: You must call browser_tabs first to get the tabId.",
  inputSchema: {
    type: "object",
    properties: {
      tabId: {
        type: "number",
        description: "The tab ID to extract paragraphs from. Get this from browser_tabs tool.",
      },
    },
    required: ["tabId"],
  },
};

// Browser Annotate Tool
export const BROWSER_ANNOTATE_TOOL: McpTool = {
  name: "browser_annotate",
  description:
    "Render AI-generated content INTO the page, immersive-translate style: each item with " +
    "an `index` is inserted as a styled block directly below the paragraph with that index " +
    "(from browser_paragraphs); an item without `index` goes to a floating page-level answer card. " +
    "WORKFLOW for translating a page/paper (翻译): 1) browser_paragraphs to get indexed paragraphs; " +
    "2) translate a batch of paragraphs (5-10 at a time; translate a long paragraph on its own); " +
    "3) call browser_annotate with items [{index, text, kind:'translation'}] for that batch; " +
    "4) repeat until done so translations appear progressively. " +
    "TRANSLATION RULES (mandatory): translate every paragraph FULLY and FAITHFULLY, sentence by " +
    "sentence to the end — NEVER summarize, compress, omit content, or use ellipsis ('...' / '……') " +
    "to skip text; the translation must cover 100% of the source. Keep technical terms, proper " +
    "nouns, URLs, and numbers intact. The `text` field must contain ONLY the translation — no " +
    "explanations, no prefixes like 'Here is the translation'. " +
    "For section explanations use kind:'explanation'. " +
    "Idempotent: annotating the same index again replaces the block. " +
    "Pass clear:true to remove all injected annotations. " +
    "PDF VIEWER TABS (URL chrome-extension://.../viewer.html, opened via browser_pdf_render): " +
    "items use native pdf.js annotation editors — kind 'highlight' highlights the given text " +
    "on the given page (index = 1-based page number); default kind adds a FreeText note at " +
    "x/y page fractions. To SAVE the annotated PDF, run browser_execute on the same tab with " +
    "script: `await app.save()` — this downloads an annotated copy to ~/Downloads. " +
    "IMPORTANT: You must call browser_tabs first to get the tabId.",
  inputSchema: {
    type: "object",
    properties: {
      tabId: {
        type: "number",
        description: "The tab ID to annotate. Get this from browser_tabs tool.",
      },
      items: {
        type: "array",
        description:
          "Blocks to render. On REGULAR pages: index = paragraph index from browser_paragraphs " +
          "(omit for the page-level answer card); text = the translation/explanation to display; " +
          "kind = 'translation' (default) or 'explanation'. " +
          "On PDF VIEWER tabs (opened via browser_pdf_render): index = 1-based PAGE number; " +
          "with kind 'highlight' (or text matching page text), text = the EXACT text on that page " +
          "to highlight (native pdf.js highlight); otherwise a native FreeText note is placed at " +
          "x/y (page fractions, top-left origin; default top-right corner) with optional " +
          "width/height/color [r,g,b]/fontSize/comment.",
        items: {
          type: "object",
          properties: {
            index: { type: "number" },
            text: { type: "string" },
            kind: { type: "string" },
            x: { type: "number" },
            y: { type: "number" },
            width: { type: "number" },
            height: { type: "number" },
            color: { type: "array", items: { type: "number" } },
            fontSize: { type: "number" },
            comment: { type: "string" },
          },
          required: ["text"],
        },
      },
      clear: {
        type: "boolean",
        description: "Remove all previously injected annotations from the page.",
      },
    },
    required: ["tabId"],
  },
};

// Browser PDF Render Tool
export const BROWSER_PDF_RENDER_TOOL: McpTool = {
  name: "browser_pdf_render",
  description:
    "Open a PDF document (http/https/file URL) in the extension's built-in pdf.js viewer " +
    "and wait until it finishes loading. Returns the viewer tab id, total page count " +
    "and document title. file:// URLs require the extension's \"Allow access to " +
    "file URLs\" toggle to be on in chrome://extensions. " +
    "TWO complementary ways to work with the opened PDF — " +
    "BULK ANALYSIS (full-text extraction, keyword search across pages, tables, extracting " +
    "links/metadata, rendering pages to images for local vision): use the PREINSTALLED " +
    "Python package `pymupdf` via run_cmd (`import pymupdf`; for remote URLs download the " +
    "file to a local path first, e.g. /tmp/doc.pdf). This is the fast path for reading a " +
    "whole datasheet/manual. " +
    "INTERACTIVE WORK on the viewer tab (turning pages, zooming, native highlight/freetext " +
    "annotations, screenshotting the rendered page for figures/diagrams, showing progress " +
    "to the user): use browser_read (current page text) / browser_paragraphs (all pages) / " +
    'browser_execute with {"cmd":"goto"|"zoom"|"rotate"} / browser_screenshot / ' +
    "browser_annotate with the returned tabId.",
  inputSchema: {
    type: "object",
    properties: {
      pdfUrl: {
        type: "string",
        description: "The URL (http/https/file) of the PDF document to render.",
      },
      page: {
        type: "number",
        description: "Optional 1-based page number to scroll to after loading.",
      },
    },
    required: ["pdfUrl"],
  },
};

// All browser tools
export const BROWSER_TOOLS = [
  BROWSER_TABS_TOOL,
  BROWSER_READ_TOOL,
  BROWSER_EXECUTE_TOOL,
  BROWSER_REPLAY_TOOL,
  BROWSER_SCREENSHOT_TOOL,
  BROWSER_PARAGRAPHS_TOOL,
  BROWSER_ANNOTATE_TOOL,
  BROWSER_PDF_RENDER_TOOL,
];

