// browser_pdf_render: open a PDF (http/https/file URL) in the vendored pdf.js
// viewer and report once the document has finished loading.
//
// The viewer page (dist/pdf/web/viewer.html) carries acp-bridge.mjs, which
// posts `pdf_viewer_event` runtime messages back to this service worker.
// We park one resolver per freshly opened tab and resolve it when that tab's
// viewer reports `pagesloaded` (or `documenterror`), with a timeout fallback
// so a slow/hung document never leaves the tool call hanging.

import type { BrowserPdfRenderResult } from "@chrome-acp/shared/acp";

// The proxy's MCP layer times out browser tool calls at 30s; stay under that.
const LOAD_WAIT_MS = 20_000;

interface PdfViewerEvent {
  type: "pdf_viewer_event";
  event: "loaded" | "pagechanging" | "documenterror";
  fileUrl?: string;
  pages?: number;
  title?: string;
  page?: number;
  message?: string;
}

interface PendingRender {
  resolve: (result: { pages?: number; title?: string; error?: string }) => void;
  timer: ReturnType<typeof setTimeout>;
}

const pendingByTab = new Map<number, PendingRender>();

// Registered at module scope: background.ts imports this module (via
// tools/browser.ts), so the listener is live from service worker startup.
chrome.runtime.onMessage.addListener((message: unknown, sender) => {
  const msg = message as PdfViewerEvent;
  if (msg?.type !== "pdf_viewer_event") return;

  const tabId = sender.tab?.id;
  if (tabId === undefined) return;

  const pending = pendingByTab.get(tabId);
  if (!pending) return;

  if (msg.event === "loaded") {
    clearTimeout(pending.timer);
    pendingByTab.delete(tabId);
    pending.resolve({ pages: msg.pages, title: msg.title });
  } else if (msg.event === "documenterror") {
    clearTimeout(pending.timer);
    pendingByTab.delete(tabId);
    pending.resolve({ error: msg.message || "documenterror" });
  }
});

// Drop the pending entry when the tab is closed before finishing load.
chrome.tabs.onRemoved.addListener((tabId) => {
  const pending = pendingByTab.get(tabId);
  if (!pending) return;
  clearTimeout(pending.timer);
  pendingByTab.delete(tabId);
  pending.resolve({ error: "viewer tab closed before the document loaded" });
});

export async function executePdfRender(
  pdfUrl: string,
  page?: number,
  loadWaitMs: number = LOAD_WAIT_MS,
): Promise<BrowserPdfRenderResult> {
  let parsed: URL;
  try {
    parsed = new URL(pdfUrl);
  } catch {
    throw new Error(`Invalid PDF URL: ${pdfUrl}`);
  }
  // file: works because the extension-page CSP allows connect-src file:; it
  // still requires the user grant "Allow access to file URLs" — otherwise the
  // viewer reports documenterror and we surface that below.
  if (!["http:", "https:", "file:"].includes(parsed.protocol)) {
    throw new Error(
      `Unsupported PDF URL protocol for browser_pdf_render: ${parsed.protocol} (use http/https/file)`,
    );
  }

  const viewerUrl =
    chrome.runtime.getURL("dist/pdf/web/viewer.html") +
    `?file=${encodeURIComponent(pdfUrl)}` +
    (page && page > 0 ? `#page=${page}` : "");

  const tab = await chrome.tabs.create({ url: viewerUrl, active: true });
  if (tab.id === undefined) {
    throw new Error("Failed to open PDF viewer tab");
  }
  const tabId = tab.id;

  const outcome = await new Promise<{ pages?: number; title?: string; error?: string }>(
    (resolve) => {
      const timer = setTimeout(() => {
        pendingByTab.delete(tabId);
        resolve({}); // timed out: report "opened" without page info
      }, loadWaitMs);
      pendingByTab.set(tabId, { resolve, timer });
    },
  );

  if (outcome.error) {
    throw new Error(`PDF viewer failed to load ${pdfUrl}: ${outcome.error}`);
  }

  return {
    action: "pdf_render",
    tabId,
    url: viewerUrl,
    pdfUrl,
    pages: outcome.pages,
    title: outcome.title,
    status: outcome.pages !== undefined ? "loaded" : "opened",
  };
}
