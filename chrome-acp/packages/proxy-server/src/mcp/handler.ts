import type { Context } from "hono";
import { createHash } from "node:crypto";
import { mkdir, readdir, rm, stat, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  type McpRequest,
  type McpResponse,
  type McpInitializeResult,
  type McpToolsListResult,
  type McpToolCallParams,
  type McpToolCallResult,
  type BrowserToolParams,
  type BrowserToolResult,
  type BrowserTabsResult,
  type BrowserReadResult,
  type BrowserExecuteResult,
  type BrowserReplayResult,
  type BrowserScreenshotResult,
  type BrowserParagraphsResult,
  type BrowserAnnotateResult,
  type BrowserPdfRenderResult,
  type AnnotateItem,
  MCP_METHODS,
  BROWSER_TOOLS,
} from "./types.js";
import { log } from "../logger.js";

const MCP_PROTOCOL_VERSION = "2024-11-05";

// Pending browser tool calls waiting for extension response
const pendingBrowserCalls = new Map<
  string,
  {
    resolve: (result: BrowserToolResult) => void;
    reject: (error: Error) => void;
  }
>();

// ============================================================================
// Executor registry
// ============================================================================
// Browser tools need a connected WebSocket client that can execute them.
// Two kinds register:
//   - Dedicated executors: the extension background service worker's tool
//     channel, announced via the `register_executor` message. Preferred.
//   - Fallback executors: any /ws client (legacy sidepanel behavior, kept so
//     older extensions keep working). Last one registered wins, as before.
// The old single-slot design breaks once both connect: a sidepanel close
// would unregister the still-connected service worker, killing every tool.

interface ExecutorLike {
  readyState: number;
  send(data: string): void;
}

let dedicatedExecutor: ExecutorLike | null = null;
let fallbackExecutor: ExecutorLike | null = null;

export function setDedicatedExecutor(ws: ExecutorLike | null): void {
  dedicatedExecutor = ws;
}

export function setFallbackExecutor(ws: ExecutorLike | null): void {
  fallbackExecutor = ws;
}

/** Remove a closing WS from whichever executor slot it occupies. */
export function unregisterExecutor(ws: ExecutorLike): void {
  if (dedicatedExecutor === ws) dedicatedExecutor = null;
  if (fallbackExecutor === ws) fallbackExecutor = null;
}

function pickExecutor(): ExecutorLike | null {
  if (dedicatedExecutor && dedicatedExecutor.readyState === 1) {
    return dedicatedExecutor;
  }
  if (fallbackExecutor && fallbackExecutor.readyState === 1) {
    return fallbackExecutor;
  }
  return null;
}

/** True when some client can execute browser tools (for /status). */
export function executorStatus(): {
  dedicated: boolean;
  fallback: boolean;
  connected: boolean;
} {
  return {
    dedicated: dedicatedExecutor !== null,
    fallback: fallbackExecutor !== null,
    connected: pickExecutor() !== null,
  };
}

// ============================================================================
// MCP endpoint auth
// ============================================================================

// Auth token for the /mcp endpoint (set by server.ts when auth is enabled).
// Without a check here, any local process — or a malicious webpage POSTing to
// http://localhost:9315/mcp — could drive the user's browser.
let mcpAuthToken: string | undefined;

export function setMcpAuthToken(token: string | undefined): void {
  mcpAuthToken = token;
}

/** Bearer header or ?token= query param must match when auth is enabled. */
export function isMcpRequestAuthorized(
  authorizationHeader: string | undefined,
  url: URL,
): boolean {
  if (!mcpAuthToken) return true;
  if (authorizationHeader === `Bearer ${mcpAuthToken}`) return true;
  return url.searchParams.get("token") === mcpAuthToken;
}

export function handleBrowserToolResponse(
  callId: string,
  result: BrowserToolResult | { error: string },
): void {
  log.debug("Browser tool response received", { callId });

  const pending = pendingBrowserCalls.get(callId);
  if (!pending) {
    log.warn("No pending call found", { callId });
    return;
  }

  pendingBrowserCalls.delete(callId);

  if ("error" in result && !("action" in result)) {
    log.error("Browser tool error", { error: result.error });
    pending.reject(new Error(result.error));
  } else {
    const browserResult = result as BrowserToolResult;
    log.debug("Browser tool result", {
      action: browserResult.action,
    });
    pending.resolve(browserResult);
  }
}

export async function executeBrowserTool(
  params: BrowserToolParams,
): Promise<BrowserToolResult> {
  log.debug("Browser tool called", { params });

  const executor = pickExecutor();
  if (!executor) {
    log.error("No browser extension connected");
    throw new Error("No browser extension connected");
  }

  const callId = crypto.randomUUID();
  log.debug("Browser tool call", { callId });

  // Send request to extension
  executor.send(
    JSON.stringify({
      type: "browser_tool_call",
      callId,
      params,
    }),
  );

  // Wait for response
  return new Promise((resolve, reject) => {
    pendingBrowserCalls.set(callId, { resolve, reject });

    // Timeout after 30 seconds
    setTimeout(() => {
      if (pendingBrowserCalls.has(callId)) {
        pendingBrowserCalls.delete(callId);
        log.error("Browser tool call timed out", { callId });
        reject(new Error("Browser tool call timed out"));
      }
    }, 30000);
  });
}

function handleInitialize(id: string | number): McpResponse {
  const result: McpInitializeResult = {
    protocolVersion: MCP_PROTOCOL_VERSION,
    capabilities: {
      tools: { listChanged: false },
    },
    serverInfo: {
      name: "chrome-acp-browser",
      version: "1.0.0",
    },
  };

  return { jsonrpc: "2.0", id, result };
}

function handleToolsList(id: string | number): McpResponse {
  const result: McpToolsListResult = {
    tools: BROWSER_TOOLS,
  };

  return { jsonrpc: "2.0", id, result };
}

function formatTabsResult(result: BrowserTabsResult): McpToolCallResult {
  const lines = [
    `# Browser Tabs`,
    ``,
    `Found ${result.tabs.length} open tab(s):`,
    ``,
    ...result.tabs.map(
      (tab) =>
        `- **Tab ${tab.id}**${tab.active ? " (active)" : ""}: ${tab.title}\n  URL: ${tab.url}`,
    ),
  ];

  log.debug("Tabs result", {
    count: result.tabs.length,
  });

  return {
    content: [{ type: "text", text: lines.join("\n") }],
  };
}

function formatReadResult(result: BrowserReadResult): McpToolCallResult {
  const domEnd = result.domOffset + result.dom.length;
  const textContent = [
    `# Browser Read Result`,
    ``,
    `## Page Info`,
    `- Tab ID: ${result.tabId}`,
    `- URL: ${result.url}`,
    `- Title: ${result.title}`,
    `- Viewport: ${result.viewport.width}x${result.viewport.height}`,
    `- Scroll Position: (${result.viewport.scrollX}, ${result.viewport.scrollY})`,
    result.selection ? `- Selected Text: "${result.selection}"` : null,
    `- Content: showing chars ${result.domOffset}–${domEnd} of ${result.domTotalLength}`,
    result.hasMore
      ? `- More content available: call browser_read again with offset=${domEnd} to continue.`
      : null,
    ``,
    `## Page Content`,
    ``,
    result.dom,
  ]
    .filter(Boolean)
    .join("\n");

  log.debug("Read result", {
    tabId: result.tabId,
    url: result.url,
    title: result.title,
    viewport: result.viewport,
    selection: result.selection,
    domLength: result.dom?.length || 0,
    totalChars: textContent.length,
  });

  return {
    content: [{ type: "text", text: textContent }],
  };
}

function formatReplayResult(result: BrowserReplayResult): McpToolCallResult {
  const textContent = [
    `# Browser Replay Result`,
    ``,
    `- Tab ID: ${result.tabId}`,
    `- URL: ${result.url}`,
    `- OK: ${result.ok}`,
    result.response
      ? `\n## Page Response\n${result.response}`
      : null,
    result.error
      ? `\n## Error\n${result.error}\n\nThe step could not be replayed deterministically. Fall back to browser_read/browser_execute to complete it autonomously.`
      : null,
  ]
    .filter(Boolean)
    .join("\n");

  return {
    content: [{ type: "text", text: textContent }],
    isError: !result.ok,
  };
}

// Screenshots are written to a temp dir instead of being embedded in the tool
// result, so the image never enters the LLM request (models behind OpenAI-compat
// gateways often reject image blocks with a 400). The agent reads the file
// itself with its file-reading tools (read_file / edit_file).
const SCREENSHOT_DIR = join(tmpdir(), "chrome-acp-screenshots");
const SCREENSHOT_MAX_FILES = 30;

async function saveScreenshot(base64: string): Promise<string> {
  await mkdir(SCREENSHOT_DIR, { recursive: true });

  // Key by content hash: re-capturing the same image reuses the same file,
  // so the directory does not accumulate duplicates.
  const hash = createHash("sha1").update(base64).digest("hex").slice(0, 12);
  const filePath = join(SCREENSHOT_DIR, `screenshot-${hash}.jpg`);

  try {
    await writeFile(filePath, Buffer.from(base64, "base64"), { flag: "wx" });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
  }

  // Keep the directory bounded: evict the oldest files beyond the cap.
  const entries = (await Promise.all(
    (await readdir(SCREENSHOT_DIR))
      .filter((f) => f.startsWith("screenshot-"))
      .map(async (f) => {
        const p = join(SCREENSHOT_DIR, f);
        const s = await stat(p);
        return { p, mtime: s.mtimeMs };
      }),
  )).sort((a, b) => a.mtime - b.mtime);

  for (const entry of entries.slice(0, Math.max(0, entries.length - SCREENSHOT_MAX_FILES))) {
    await rm(entry.p, { force: true });
  }

  return filePath;
}

async function formatScreenshotResult(result: BrowserScreenshotResult): Promise<McpToolCallResult> {
  log.debug("Screenshot result", {
    tabId: result.tabId,
    url: result.url,
    width: result.width,
    height: result.height,
    bytes: result.data.length,
  });

  const filePath = await saveScreenshot(result.data);

  return {
    content: [
      {
        type: "text",
        text: [
          `# Browser Screenshot`,
          ``,
          `- Tab ID: ${result.tabId}`,
          `- URL: ${result.url}`,
          `- Title: ${result.title}`,
          `- Image: ${result.width}x${result.height} JPEG, saved to ${filePath}`,
          ``,
          `To view the screenshot, read the file at the path above with your file-reading tool (e.g. read_file / edit_file).`,
        ].join("\n"),
      },
    ],
  };
}

function formatParagraphsResult(result: BrowserParagraphsResult): McpToolCallResult {
  const lines = [
    `# Browser Paragraphs`,
    ``,
    `- Tab ID: ${result.tabId}`,
    `- URL: ${result.url}`,
    `- Title: ${result.title}`,
    `- Paragraphs: ${result.paragraphs.length}${result.truncated ? " (truncated, page has more)" : ""}`,
    ``,
    `Each paragraph below shows its index for use with browser_annotate:`,
    ``,
    ...result.paragraphs.map((p) => `[${p.index}] <${p.tag}> ${p.text}`),
  ];

  return {
    content: [{ type: "text", text: lines.join("\n") }],
  };
}

function formatAnnotateResult(result: BrowserAnnotateResult): McpToolCallResult {
  const lines = [
    `# Browser Annotate Result`,
    ``,
    `- Tab ID: ${result.tabId}`,
    `- URL: ${result.url}`,
    `- Inserted/updated blocks: ${result.inserted}`,
    result.cleared ? `- Cleared existing annotations` : null,
    result.missing.length > 0
      ? `- Missing paragraph indices (DOM changed, re-run browser_paragraphs): ${result.missing.join(", ")}`
      : null,
  ]
    .filter(Boolean)
    .join("\n");

  return {
    content: [{ type: "text", text: lines }],
  };
}

function formatExecuteResult(result: BrowserExecuteResult): McpToolCallResult {
  const textContent = [
    `# Browser Execute Result`,
    ``,
    `- Tab ID: ${result.tabId}`,
    `- URL: ${result.url}`,
    result.result !== undefined
      ? `\n## Script Result\n\`\`\`\n${JSON.stringify(result.result, null, 2)}\n\`\`\``
      : null,
    result.error ? `\n## Script Error\n${result.error}` : null,
  ]
    .filter(Boolean)
    .join("\n");

  log.debug("Execute result", {
    tabId: result.tabId,
    url: result.url,
    result: result.result,
    error: result.error,
    isError: !!result.error,
    totalChars: textContent.length,
  });

  return {
    content: [{ type: "text", text: textContent }],
    isError: !!result.error,
  };
}

function formatPdfRenderResult(result: BrowserPdfRenderResult): McpToolCallResult {
  const lines = [
    `# Browser PDF Render`,
    ``,
    `- Tab ID: ${result.tabId}`,
    `- PDF: ${result.pdfUrl}`,
    `- Viewer: ${result.url}`,
    `- Status: ${result.status}`,
    result.pages !== undefined ? `- Pages: ${result.pages}` : null,
    result.title ? `- Title: ${result.title}` : null,
    ``,
    result.status === "loaded"
      ? `The document finished loading. Use browser_screenshot with the tab ID above to visually inspect rendered pages.`
      : `The viewer tab was opened but the load-wait timed out (large or slow document). It may still be rendering; retry browser_screenshot after a short wait.`,
  ]
    .filter(Boolean)
    .join("\n");

  return {
    content: [{ type: "text", text: lines }],
  };
}

async function handleToolCall(
  id: string | number,
  params: McpToolCallParams,
): Promise<McpResponse> {
  log.info("Tool call started", {
    id,
    tool: params.name,
    arguments: params.arguments,
  });

  // Map tool name to action
  const toolToAction: Record<string, BrowserToolParams["action"]> = {
    browser_tabs: "tabs",
    browser_read: "read",
    browser_execute: "execute",
    browser_replay: "replay",
    browser_screenshot: "screenshot",
    browser_paragraphs: "paragraphs",
    browser_annotate: "annotate",
    browser_pdf_render: "pdf_render",
  };

  const action = toolToAction[params.name];
  if (!action) {
    log.warn("Unknown tool requested", { tool: params.name });
    return {
      jsonrpc: "2.0",
      id,
      error: {
        code: -32602,
        message: `Unknown tool: ${params.name}`,
      },
    };
  }

  try {
    const args = params.arguments as {
      tabId?: number;
      script?: string;
      step?: BrowserToolParams["step"];
      offset?: number;
      limit?: number;
      maxWidth?: number;
      quality?: number;
      items?: AnnotateItem[];
      clear?: boolean;
      pdfUrl?: string;
      page?: number;
    };
    const browserParams: BrowserToolParams = {
      action,
      tabId: args?.tabId,
      script: args?.script,
      step: args?.step,
      offset: args?.offset,
      limit: args?.limit,
      maxWidth: args?.maxWidth,
      quality: args?.quality,
      items: args?.items,
      clear: args?.clear,
      pdfUrl: args?.pdfUrl,
      page: args?.page,
    };

    const startTime = Date.now();
    const browserResult = await executeBrowserTool(browserParams);
    const duration = Date.now() - startTime;

    log.info("Tool call completed", {
      id,
      tool: params.name,
      action,
      durationMs: duration,
    });

    let result: McpToolCallResult;

    switch (browserResult.action) {
      case "tabs":
        result = formatTabsResult(browserResult);
        break;
      case "read":
        result = formatReadResult(browserResult);
        break;
      case "execute":
        result = formatExecuteResult(browserResult);
        break;
      case "replay":
        result = formatReplayResult(browserResult);
        break;
      case "screenshot":
        result = await formatScreenshotResult(browserResult);
        break;
      case "paragraphs":
        result = formatParagraphsResult(browserResult);
        break;
      case "annotate":
        result = formatAnnotateResult(browserResult);
        break;
      case "pdf_render":
        result = formatPdfRenderResult(browserResult);
        break;
      default:
        throw new Error(`Unknown action: ${(browserResult as BrowserToolResult).action}`);
    }

    const response: McpResponse = { jsonrpc: "2.0", id, result };
    log.trace("MCP tool call response", { response });
    return response;
  } catch (error) {
    log.error("Tool call failed", {
      id,
      tool: params.name,
      error: (error as Error).message,
      stack: (error as Error).stack,
    });

    const result: McpToolCallResult = {
      content: [{ type: "text", text: (error as Error).message }],
      isError: true,
    };

    return { jsonrpc: "2.0", id, result };
  }
}

export async function handleMcpRequest(c: Context): Promise<Response> {
  if (!isMcpRequestAuthorized(c.req.header("Authorization"), new URL(c.req.url))) {
    return c.json({ error: "Unauthorized" }, 401);
  }

  const request = (await c.req.json()) as McpRequest;
  log.debug("MCP request received", { method: request.method });

  let response: McpResponse;

  switch (request.method) {
    case MCP_METHODS.INITIALIZE:
      response = handleInitialize(request.id);
      break;

    case MCP_METHODS.TOOLS_LIST:
      response = handleToolsList(request.id);
      break;

    case MCP_METHODS.TOOLS_CALL:
      response = await handleToolCall(
        request.id,
        request.params as unknown as McpToolCallParams,
      );
      break;

    default:
      response = {
        jsonrpc: "2.0",
        id: request.id,
        error: {
          code: -32601,
          message: `Method not found: ${request.method}`,
        },
      };
  }

  return c.json(response);
}
