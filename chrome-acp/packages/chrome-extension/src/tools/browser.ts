// Browser tool handler - executes in the extension context
// Communicates with content scripts to access page DOM

import type {
  BrowserToolParams,
  BrowserToolResult,
  BrowserTabsResult,
  BrowserReadResult,
  BrowserExecuteResult,
  BrowserReplayResult,
  BrowserScreenshotResult,
  BrowserParagraphsResult,
  BrowserAnnotateResult,
  BrowserParagraph,
  AnnotateItem,
  ReplayStep,
} from "@chrome-acp/shared/acp";
import { executePdfRender } from "../pdf/pdf-render";

// Execute browser_tabs: List all open tabs
async function executeBrowserTabs(): Promise<BrowserTabsResult> {
  console.log("[BrowserTool] Listing tabs...");
  const allTabs = await chrome.tabs.query({});

  const tabs = allTabs
    .filter((tab) => tab.id !== undefined)
    .map((tab) => ({
      id: tab.id!,
      url: tab.url || "",
      title: tab.title || "",
      active: tab.active || false,
    }));

  console.log(`[BrowserTool] Found ${tabs.length} tabs`);
  return { action: "tabs", tabs };
}

// Default page size for browser_read DOM content. Large pages can serialize
// to millions of chars; returning them whole can blow the agent's context.
const DEFAULT_READ_LIMIT = 50_000;

// PDF viewer tabs (chrome-extension://…/dist/pdf/web/viewer.html) cannot be
// injected into with chrome.scripting (extension pages are off-limits even
// to their own extension). The vendored viewer ships acp-bridge.js, which
// exposes read/paragraphs/annotate/execute handlers over
// chrome.tabs.sendMessage — route those tools through it.

async function isViewerTab(tabId: number): Promise<{ url: string } | null> {
  const tab = await chrome.tabs.get(tabId);
  if (!tab) {
    throw new Error(`Tab ${tabId} not found`);
  }
  const prefix = chrome.runtime.getURL("dist/pdf/web/viewer.html");
  return tab.url?.startsWith(prefix) ? { url: tab.url } : null;
}

async function messageViewerTab<T extends object>(tabId: number, message: object): Promise<T> {
  try {
    return (await chrome.tabs.sendMessage(tabId, message)) as T;
  } catch (e) {
    throw new Error(
      `PDF viewer bridge unreachable (reload the PDF tab after updating the extension): ${e}`,
    );
  }
}

// Execute browser_read: Get DOM info from specific tab
async function executeBrowserRead(
  tabId: number,
  offset = 0,
  limit?: number,
): Promise<BrowserReadResult> {
  console.log(`[BrowserTool] Reading tab ${tabId} (offset=${offset}, limit=${limit})...`);

  const viewer = await isViewerTab(tabId);
  if (viewer) {
    const r = await messageViewerTab<{
      error?: string; url?: string; title?: string; page?: number; pages?: number; text?: string;
    }>(tabId, { type: "acp_pdf_read" });
    if (r.error) {
      throw new Error(r.error);
    }
    const dom = r.text ?? "";
    const effectiveLimit = limit ?? DEFAULT_READ_LIMIT;
    const slice = dom.slice(offset, offset + effectiveLimit);
    return {
      action: "read",
      tabId,
      url: r.url ?? viewer.url,
      title: r.title ?? "",
      dom: slice,
      domTotalLength: dom.length,
      domOffset: offset,
      hasMore: offset + slice.length < dom.length,
      viewport: { width: 0, height: 0, scrollX: 0, scrollY: 0 },
      selection: null,
    };
  }

  const tab = await chrome.tabs.get(tabId);
  if (!tab) {
    throw new Error(`Tab ${tabId} not found`);
  }

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: collectPageInfo,
  });

  const pageInfo = results[0]?.result;
  if (!pageInfo) {
    throw new Error("Failed to collect page info");
  }

  // Paginate the serialized DOM here in the extension so oversized pages
  // never cross the WebSocket. Agents page through with offset/limit.
  const fullDom = pageInfo.dom;
  const totalLength = fullDom.length;
  const safeOffset = Math.max(0, Math.min(offset, totalLength));
  const effectiveLimit = limit === undefined ? DEFAULT_READ_LIMIT : Math.max(1, limit);
  const slicedDom = fullDom.slice(safeOffset, safeOffset + effectiveLimit);

  console.log(
    `[BrowserTool] Read complete: ${totalLength} chars total, returning [${safeOffset}, ${safeOffset + slicedDom.length})`,
  );
  return {
    action: "read",
    tabId,
    ...pageInfo,
    dom: slicedDom,
    domTotalLength: totalLength,
    domOffset: safeOffset,
    hasMore: safeOffset + slicedDom.length < totalLength,
  };
}

// Execute browser_execute: Run script in specific tab
async function executeBrowserExecute(
  tabId: number,
  script: string,
): Promise<BrowserExecuteResult> {
  console.log(`[BrowserTool] Executing script in tab ${tabId}...`);

  const viewer = await isViewerTab(tabId);
  if (viewer) {
    // Extension pages cannot run arbitrary scripts (MV3 CSP); the bridge
    // serves a fixed command set instead. The script argument must be a
    // JSON command object, e.g. {"cmd":"goto","page":5}.
    let cmd: { cmd?: string } | null = null;
    try {
      cmd = JSON.parse(script);
    } catch {
      /* fall through */
    }
    if (!cmd || typeof cmd.cmd !== "string") {
      return {
        action: "execute",
        tabId,
        url: viewer.url,
        error:
          "PDF viewer tabs support JSON commands only (MV3 CSP forbids eval), " +
          'e.g. {"cmd":"state"} / {"cmd":"goto","page":5} / {"cmd":"zoom","scale":"page-fit"} / ' +
          '{"cmd":"rotate","deg":90} / {"cmd":"save"}',
      };
    }
    const r = await messageViewerTab<{ error?: string; result?: unknown }>(tabId, {
      type: "acp_pdf_execute",
      ...cmd,
    });
    return {
      action: "execute",
      tabId,
      url: viewer.url,
      result: r,
      error: r?.error,
    };
  }

  const tab = await chrome.tabs.get(tabId);
  if (!tab) {
    throw new Error(`Tab ${tabId} not found`);
  }

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      world: "MAIN", // Execute in page's main world
      func: executeScriptInMainWorld,
      args: [script],
    });

    const scriptResult = results[0]?.result;
    console.log("[BrowserTool] Script executed");

    return {
      action: "execute",
      tabId,
      url: tab.url || "",
      result: scriptResult?.result,
      error: scriptResult?.error,
    };
  } catch (error) {
    console.error("[BrowserTool] Script execution failed:", error);
    return {
      action: "execute",
      tabId,
      url: tab.url || "",
      error: (error as Error).message,
    };
  }
}

// Execute browser_replay: deterministically replay one pipeline step in a tab.
// The replay executor is injected as a file, then invoked in the same world.
async function executeBrowserReplay(
  tabId: number,
  step: ReplayStep,
): Promise<BrowserReplayResult> {
  console.log(`[BrowserTool] Replaying ${step.kind} in tab ${tabId}...`);

  const tab = await chrome.tabs.get(tabId);
  if (!tab) {
    throw new Error(`Tab ${tabId} not found`);
  }

  try {
    // Idempotent injection: inject.ts only defines window.__acpReplay once
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["dist/replay/inject.js"],
    });

    interface InjectedResult {
      ok: boolean;
      error?: string;
      response?: string;
      url: string;
    }
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: (s: ReplayStep): Promise<InjectedResult> => {
        const replay = (
          window as unknown as {
            __acpReplay?: { run: (step: ReplayStep) => Promise<InjectedResult> };
          }
        ).__acpReplay;
        if (!replay) {
          return Promise.resolve({ ok: false, error: "executor_not_injected", url: location.href });
        }
        return replay.run(s);
      },
      args: [step],
    });

    const replayResult = results[0]?.result;
    if (!replayResult) {
      throw new Error("Replay returned no result");
    }

    console.log("[BrowserTool] Replay result:", replayResult);
    return {
      action: "replay",
      tabId,
      url: replayResult.url,
      ok: replayResult.ok,
      error: replayResult.error,
      response: replayResult.response,
    };
  } catch (error) {
    console.error("[BrowserTool] Replay failed:", error);
    return {
      action: "replay",
      tabId,
      url: tab.url || "",
      ok: false,
      error: (error as Error).message,
    };
  }
}

// Execute browser_screenshot: capture the visible viewport of a tab as JPEG.
// captureVisibleTab only captures the ACTIVE tab of a window, so background
// tabs are activated (and their window focused) before capturing.
const DEFAULT_SCREENSHOT_MAX_WIDTH = 1280;
const DEFAULT_SCREENSHOT_QUALITY = 70;

async function executeBrowserScreenshot(
  tabId: number,
  maxWidth = DEFAULT_SCREENSHOT_MAX_WIDTH,
  quality = DEFAULT_SCREENSHOT_QUALITY,
): Promise<BrowserScreenshotResult> {
  console.log(`[BrowserTool] Capturing screenshot of tab ${tabId}...`);

  let tab = await chrome.tabs.get(tabId);
  if (!tab) {
    throw new Error(`Tab ${tabId} not found`);
  }

  if (!tab.active) {
    await chrome.tabs.update(tabId, { active: true });
    await chrome.windows.update(tab.windowId, { focused: true });
    // Give the tab a moment to render after being brought to front
    await new Promise((resolve) => setTimeout(resolve, 150));
    tab = await chrome.tabs.get(tabId);
  }

  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format: "jpeg",
    quality: Math.max(0, Math.min(100, Math.round(quality))),
  });

  const { base64, width, height } = await downscaleScreenshot(
    dataUrl,
    Math.max(1, Math.round(maxWidth)),
    quality,
  );

  console.log(`[BrowserTool] Screenshot captured: ${width}x${height}, ${base64.length} base64 chars`);
  return {
    action: "screenshot",
    tabId,
    url: tab.url || "",
    title: tab.title || "",
    data: base64,
    mimeType: "image/jpeg",
    width,
    height,
  };
}

// Downscale a data-URL image to maxWidth using OffscreenCanvas.
// Works in both extension pages and the MV3 service worker.
// Note: fetch(dataUrl) is blocked by the extension CSP (connect-src has no
// data:), so decode the base64 payload manually with atob.
async function downscaleScreenshot(
  dataUrl: string,
  maxWidth: number,
  quality: number,
): Promise<{ base64: string; width: number; height: number }> {
  const base64Data = dataUrl.slice(dataUrl.indexOf(",") + 1);
  const binary = atob(base64Data);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  const blob = new Blob([bytes], { type: "image/jpeg" });
  const bitmap = await createImageBitmap(blob);

  try {
    const scale = Math.min(1, maxWidth / bitmap.width);
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);

    const canvas = new OffscreenCanvas(width, height);
    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("Failed to get 2d context for screenshot resize");
    }
    ctx.drawImage(bitmap, 0, 0, width, height);

    const outBlob = await canvas.convertToBlob({
      type: "image/jpeg",
      quality: Math.max(0, Math.min(1, quality / 100)),
    });

    const outDataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = () => reject(new Error("Failed to encode screenshot"));
      reader.readAsDataURL(outBlob);
    });

    return {
      base64: outDataUrl.slice(outDataUrl.indexOf(",") + 1),
      width,
      height,
    };
  } finally {
    bitmap.close();
  }
}

// Execute browser_paragraphs: extract the page's main readable paragraphs as
// an indexed list, tagging each element with data-acp-para so later
// browser_annotate calls can locate it without fuzzy text matching.
async function executeBrowserParagraphs(
  tabId: number,
): Promise<BrowserParagraphsResult> {
  console.log(`[BrowserTool] Extracting paragraphs of tab ${tabId}...`);

  const viewer = await isViewerTab(tabId);
  if (viewer) {
    const r = await messageViewerTab<{
      error?: string; paragraphs?: BrowserParagraph[]; truncated?: boolean;
    }>(tabId, { type: "acp_pdf_paragraphs" });
    if (r.error) {
      throw new Error(r.error);
    }
    console.log(`[BrowserTool] Extracted ${r.paragraphs?.length ?? 0} pages`);
    return {
      action: "paragraphs",
      tabId,
      url: viewer.url,
      title: "",
      paragraphs: r.paragraphs ?? [],
      truncated: !!r.truncated,
    };
  }

  const tab = await chrome.tabs.get(tabId);
  if (!tab) {
    throw new Error(`Tab ${tabId} not found`);
  }

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: extractParagraphs,
  });

  const extracted = results[0]?.result;
  if (!extracted) {
    throw new Error("Failed to extract paragraphs");
  }

  console.log(`[BrowserTool] Extracted ${extracted.paragraphs.length} paragraphs`);
  return {
    action: "paragraphs",
    tabId,
    url: tab.url || "",
    title: tab.title || "",
    paragraphs: extracted.paragraphs,
    truncated: extracted.truncated,
  };
}

// Execute browser_annotate: insert translation/explanation blocks into the
// page, immersive-translate style (below the tagged paragraph), or into a
// page-level floating card when the item has no paragraph index.
async function executeBrowserAnnotate(
  tabId: number,
  items?: AnnotateItem[],
  clear?: boolean,
): Promise<BrowserAnnotateResult> {
  console.log(
    `[BrowserTool] Annotating tab ${tabId} (${items?.length ?? 0} items, clear=${!!clear})...`,
  );

  const viewer = await isViewerTab(tabId);
  if (viewer) {
    const r = await messageViewerTab<{
      error?: string; inserted?: number; missing?: number[]; cleared?: boolean; errors?: string[];
    }>(tabId, { type: "acp_pdf_annotate", items: items ?? [], clear: !!clear });
    if (r.error) {
      throw new Error(r.error);
    }
    if (r.errors?.length) {
      console.warn("[BrowserTool] PDF annotation issues:", r.errors);
    }
    return {
      action: "annotate",
      tabId,
      url: viewer.url,
      inserted: r.inserted ?? 0,
      missing: r.missing ?? [],
      cleared: !!r.cleared,
      ...(r.errors?.length ? { note: r.errors.join("; ") } : {}),
    };
  }

  const tab = await chrome.tabs.get(tabId);
  if (!tab) {
    throw new Error(`Tab ${tabId} not found`);
  }

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: applyAnnotations,
    args: [items ?? [], !!clear],
  });

  const applied = results[0]?.result;
  if (!applied) {
    throw new Error("Failed to apply annotations");
  }

  return {
    action: "annotate",
    tabId,
    url: tab.url || "",
    inserted: applied.inserted,
    missing: applied.missing,
    cleared: applied.cleared,
  };
}

// Main entry point - routes to appropriate action
export async function executeBrowserTool(
  params: BrowserToolParams,
): Promise<BrowserToolResult> {
  console.log("[BrowserTool] Action:", params.action);

  switch (params.action) {
    case "tabs":
      return executeBrowserTabs();
    case "read":
      if (params.tabId === undefined) {
        throw new Error("tabId is required for read action");
      }
      return executeBrowserRead(params.tabId, params.offset, params.limit);
    case "execute":
      if (params.tabId === undefined) {
        throw new Error("tabId is required for execute action");
      }
      if (!params.script) {
        throw new Error("script is required for execute action");
      }
      return executeBrowserExecute(params.tabId, params.script);
    case "replay":
      if (params.tabId === undefined) {
        throw new Error("tabId is required for replay action");
      }
      if (!params.step) {
        throw new Error("step is required for replay action");
      }
      return executeBrowserReplay(params.tabId, params.step);
    case "screenshot":
      if (params.tabId === undefined) {
        throw new Error("tabId is required for screenshot action");
      }
      return executeBrowserScreenshot(params.tabId, params.maxWidth, params.quality);
    case "paragraphs":
      if (params.tabId === undefined) {
        throw new Error("tabId is required for paragraphs action");
      }
      return executeBrowserParagraphs(params.tabId);
    case "annotate":
      if (params.tabId === undefined) {
        throw new Error("tabId is required for annotate action");
      }
      return executeBrowserAnnotate(params.tabId, params.items, params.clear);
    case "pdf_render":
      if (!params.pdfUrl) {
        throw new Error("pdfUrl is required for pdf_render action");
      }
      return executePdfRender(params.pdfUrl, params.page);
    default:
      throw new Error(`Unknown action: ${params.action}`);
  }
}

// Page info type for collectPageInfo return
interface PageInfo {
  url: string;
  title: string;
  dom: string;
  viewport: { width: number; height: number; scrollX: number; scrollY: number };
  selection: string | null;
}

// This function is serialized and executed in the page context (ISOLATED world)
// It only collects DOM info, does NOT execute user scripts
function collectPageInfo(): PageInfo {
  // Serialize DOM to a simplified text representation
  function serializeDOM(): string {
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
      {
        acceptNode: (node) => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            const el = node as Element;
            const tagName = el.tagName.toLowerCase();
            if (
              ["script", "style", "noscript", "svg", "path"].includes(tagName)
            ) {
              return NodeFilter.FILTER_REJECT;
            }
            const style = window.getComputedStyle(el);
            if (style.display === "none" || style.visibility === "hidden") {
              return NodeFilter.FILTER_REJECT;
            }
          }
          return NodeFilter.FILTER_ACCEPT;
        },
      },
    );

    const parts: string[] = [];
    let currentNode: Node | null;

    while ((currentNode = walker.nextNode())) {
      if (currentNode.nodeType === Node.TEXT_NODE) {
        const text = currentNode.textContent?.trim();
        if (text) {
          parts.push(text);
        }
      } else if (currentNode.nodeType === Node.ELEMENT_NODE) {
        const el = currentNode as Element;
        const tagName = el.tagName.toLowerCase();

        if (["h1", "h2", "h3", "h4", "h5", "h6"].includes(tagName)) {
          parts.push(`\n\n## `);
        } else if (tagName === "p" || tagName === "div") {
          parts.push("\n");
        } else if (tagName === "li") {
          parts.push("\n- ");
        } else if (tagName === "button") {
          parts.push(`[Button: `);
        } else if (tagName === "input") {
          const type = el.getAttribute("type") || "text";
          const name = el.getAttribute("name") || el.getAttribute("id") || "";
          const value = (el as HTMLInputElement).value || "";
          parts.push(`[Input ${type} "${name}": "${value}"]`);
        } else if (tagName === "img") {
          const alt = el.getAttribute("alt") || "";
          parts.push(`[Image: ${alt}]`);
        }
      }
    }

    return parts.join("").replace(/\n{3,}/g, "\n\n").trim();
  }

  return {
    url: window.location.href,
    title: document.title,
    dom: serializeDOM(),
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
    },
    selection: window.getSelection()?.toString() || null,
  };
}

// This function executes user script in the MAIN world (page context)
// When called with world: "MAIN", it runs directly in the page's JavaScript context
// which means it uses the PAGE's CSP, not the extension's CSP
function executeScriptInMainWorld(script: string): { result?: unknown; error?: string } {
  try {
    // Use Function constructor to execute the script
    // This works because we're in the MAIN world with the page's CSP
    // Most pages allow eval/Function (unlike our extension which is MV3)
    const fn = new Function(script);
    const result = fn();
    return { result };
  } catch (error) {
    return { error: (error as Error).message };
  }
}

// ============================================================================
// Immersive annotate: serialized page functions
// ============================================================================
// Both functions are serialized (via Function.prototype.toString) and executed
// in the page context, so they must be FULLY self-contained: every constant
// they use is declared inside the function body, no module-level references.
// Paragraph elements are tagged with a `data-acp-para="<index>"` attribute
// (invisible, harmless to the page) so annotate calls can relocate them.

function extractParagraphs(): { paragraphs: BrowserParagraph[]; truncated: boolean } {
  const PARA_ATTR = "data-acp-para";
  const ANNOTATION_ATTR = "data-acp-annotation";
  const PARA_CAP = 150; // max paragraphs returned per extraction
  const PARA_TEXT_CAP = 4000; // max chars per paragraph text (paper abstracts/sections are long)
  const MIN_PARA_TEXT = 30; // shorter blocks are not worth translating

  // Prefer the main content root; fall back to body
  const root =
    document.querySelector("article") ??
    document.querySelector("main") ??
    document.querySelector('[role="main"]') ??
    document.body;

  // Clear tags from a previous extraction so indices stay fresh
  document.querySelectorAll(`[${PARA_ATTR}]`).forEach((el) => el.removeAttribute(PARA_ATTR));

  const candidates = Array.from(
    root.querySelectorAll("p, h1, h2, h3, h4, h5, h6, li, blockquote, figcaption, summary"),
  );

  const paragraphs: BrowserParagraph[] = [];
  let truncated = false;

  for (const el of candidates) {
    // Skip invisible elements
    const style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") continue;
    if (el.getClientRects().length === 0) continue;

    // Skip chrome of the page itself (nav/menus/footers) and our own UI
    if (el.closest("nav, header, footer, aside, [aria-hidden='true']")) continue;
    if (el.closest(`[${ANNOTATION_ATTR}]`)) continue;

    // Skip containers of other candidates (avoid nested duplicates)
    if (
      el.querySelector("p, h1, h2, h3, h4, h5, h6, li, blockquote, figcaption, summary")
    ) {
      continue;
    }

    const text = (el.textContent ?? "").replace(/\s+/g, " ").trim();
    if (text.length < MIN_PARA_TEXT) continue;

    if (paragraphs.length >= PARA_CAP) {
      truncated = true;
      break;
    }

    const index = paragraphs.length;
    el.setAttribute(PARA_ATTR, String(index));
    paragraphs.push({
      index,
      tag: el.tagName.toLowerCase(),
      text: text.length > PARA_TEXT_CAP ? text.slice(0, PARA_TEXT_CAP) + "…" : text,
    });
  }

  return { paragraphs, truncated };
}

function applyAnnotations(
  items: AnnotateItem[],
  clear: boolean,
): { inserted: number; missing: number[]; cleared: boolean } {
  const PARA_ATTR = "data-acp-para";
  const ANNOTATION_ATTR = "data-acp-annotation";

  let inserted = 0;
  const missing: number[] = [];
  let cleared = false;

  if (clear) {
    document.querySelectorAll(`[${ANNOTATION_ATTR}]`).forEach((el) => el.remove());
    cleared = true;
  }

  for (const item of items) {
    if (!item || typeof item.text !== "string" || !item.text.trim()) continue;

    // Page-level answer card (no paragraph index)
    if (item.index === undefined) {
      let card = document.querySelector<HTMLElement>(`[${ANNOTATION_ATTR}="page-card"]`);
      if (!card) {
        const created = document.createElement("div");
        created.setAttribute(ANNOTATION_ATTR, "page-card");
        created.style.cssText =
          "position:fixed;top:16px;right:16px;z-index:2147483647;width:340px;" +
          "max-height:50vh;overflow-y:auto;background:rgba(17,24,39,0.96);color:#e5e7eb;" +
          "border:1px solid #374151;border-radius:10px;padding:10px 12px;" +
          "box-shadow:0 8px 30px rgba(0,0,0,0.45);" +
          "font:13px/1.6 -apple-system,'PingFang SC','Segoe UI',sans-serif;" +
          "white-space:pre-wrap;word-break:break-word;";
        const close = document.createElement("button");
        close.textContent = "✕";
        close.style.cssText =
          "position:absolute;top:4px;right:8px;background:none;border:none;" +
          "color:#9ca3af;cursor:pointer;font-size:13px;padding:2px;";
        close.addEventListener("click", () => created.remove());
        created.appendChild(close);
        document.documentElement.appendChild(created);
        card = created;
      }
      const block = document.createElement("div");
      block.textContent = item.text;
      card.appendChild(block);
      inserted++;
      continue;
    }

    // Paragraph-level block
    const target = document.querySelector(`[${PARA_ATTR}="${item.index}"]`);
    if (!target) {
      missing.push(item.index);
      continue;
    }

    // Idempotent: replace an existing annotation for this paragraph
    let block = target.nextElementSibling as HTMLElement | null;
    if (!block || block.getAttribute(ANNOTATION_ATTR) !== String(item.index)) {
      block = document.createElement("div");
      block.setAttribute(ANNOTATION_ATTR, String(item.index));
      block.setAttribute("translate", "no");
      target.insertAdjacentElement("afterend", block);
    }

    // Match the original paragraph's typography (like immersive-translate):
    // same font family/size/weight/line-height/alignment, only slightly
    // dimmed with a thin color hint on the left edge.
    const orig = window.getComputedStyle(target);
    block.style.fontFamily = orig.fontFamily;
    block.style.fontSize = orig.fontSize;
    block.style.fontWeight = orig.fontWeight;
    block.style.fontStyle = orig.fontStyle;
    block.style.lineHeight = orig.lineHeight;
    block.style.letterSpacing = orig.letterSpacing;
    block.style.textAlign = orig.textAlign;
    block.style.marginTop = "0";
    block.style.marginBottom = orig.marginBottom;
    block.style.whiteSpace = "pre-wrap";
    block.style.wordBreak = "break-word";
    block.style.opacity = "0.85";
    block.style.borderLeft =
      item.kind === "explanation" ? "2px solid #fcd34d" : "2px solid #93c5fd";
    block.style.paddingLeft = "8px";
    block.textContent = item.text;
    inserted++;
  }

  return { inserted, missing, cleared };
}
