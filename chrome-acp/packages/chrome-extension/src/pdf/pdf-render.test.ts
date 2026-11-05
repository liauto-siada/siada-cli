import { beforeEach, describe, expect, test } from "bun:test";

// Minimal chrome API stub for the background-context module under test.
// pdf-render.ts registers onMessage / tabs.onRemoved listeners at module
// scope, so the stub must exist before the module is imported.
type MessageListener = (message: unknown, sender: { tab?: { id?: number } }) => void;

let messageListeners: MessageListener[] = [];
let removedListeners: ((tabId: number) => void)[] = [];
let createdTabs: { url: string; id: number }[] = [];
let nextTabId = 100;

const chromeStub = {
  runtime: {
    id: "test-extension-id",
    getURL: (p: string) => `chrome-extension://test-extension-id/${p}`,
    onMessage: {
      addListener: (fn: MessageListener) => messageListeners.push(fn),
    },
  },
  tabs: {
    create: async (opts: { url: string }) => {
      const tab = { url: opts.url, id: nextTabId++ };
      createdTabs.push(tab);
      return tab;
    },
    onRemoved: {
      addListener: (fn: (tabId: number) => void) => removedListeners.push(fn),
    },
  },
};

(globalThis as { chrome?: unknown }).chrome = chromeStub;

const { executePdfRender } = await import("./pdf-render");

function emitViewerEvent(tabId: number, event: Record<string, unknown>) {
  for (const fn of messageListeners) {
    fn({ type: "pdf_viewer_event", ...event }, { tab: { id: tabId } });
  }
}

beforeEach(() => {
  createdTabs = [];
});

describe("executePdfRender", () => {
  test("rejects invalid URLs", async () => {
    await expect(executePdfRender("not-a-url")).rejects.toThrow("Invalid PDF URL");
  });

  test("rejects unsupported URL protocols", async () => {
    await expect(executePdfRender("ftp://x/a.pdf")).rejects.toThrow("Unsupported PDF URL protocol");
  });

  test("accepts file:// URLs (extension CSP allows connect-src file:)", async () => {
    const pdfUrl = "file:///tmp/some paper.pdf";
    const promise = executePdfRender(pdfUrl, undefined, 50);
    await new Promise((r) => setTimeout(r, 5));
    expect(createdTabs).toHaveLength(1);
    expect(createdTabs[0]!.url).toContain(encodeURIComponent(pdfUrl));
    const result = await promise;
    expect(result.pdfUrl).toBe(pdfUrl);
  });

  test("opens the vendored viewer with the encoded file param", async () => {
    const pdfUrl = "https://example.com/some paper.pdf";
    const promise = executePdfRender(pdfUrl, 2, 50);
    // Let the tab get created, then let the load-wait time out (50ms).
    await new Promise((r) => setTimeout(r, 5));
    expect(createdTabs).toHaveLength(1);
    const opened = createdTabs[0]!;
    expect(opened.url).toStartWith("chrome-extension://test-extension-id/dist/pdf/web/viewer.html?file=");
    expect(opened.url).toContain(encodeURIComponent(pdfUrl));
    expect(opened.url).toEndWith("#page=2");
    const result = await promise;
    expect(result.action).toBe("pdf_render");
    expect(result.tabId).toBe(opened.id);
    expect(result.pdfUrl).toBe(pdfUrl);
    expect(result.status).toBe("opened"); // timed out before pagesloaded
    expect(result.pages).toBeUndefined();
  });

  test("resolves loaded with pages/title when the bridge reports pagesloaded", async () => {
    const promise = executePdfRender("https://example.com/a.pdf", undefined, 5000);
    await new Promise((r) => setTimeout(r, 5));
    const tabId = createdTabs[0]!.id;
    emitViewerEvent(tabId, { event: "loaded", pages: 12, title: "Spec" });
    const result = await promise;
    expect(result.status).toBe("loaded");
    expect(result.pages).toBe(12);
    expect(result.title).toBe("Spec");
  });

  test("throws when the viewer reports documenterror", async () => {
    const promise = executePdfRender("https://example.com/broken.pdf", undefined, 5000);
    await new Promise((r) => setTimeout(r, 5));
    const tabId = createdTabs[0]!.id;
    emitViewerEvent(tabId, { event: "documenterror", message: "Invalid PDF structure" });
    await expect(promise).rejects.toThrow("Invalid PDF structure");
  });

  test("ignores events from other tabs", async () => {
    const promise = executePdfRender("https://example.com/c.pdf", undefined, 200);
    await new Promise((r) => setTimeout(r, 5));
    emitViewerEvent(99999, { event: "loaded", pages: 99, title: "Wrong tab" });
    const result = await promise;
    expect(result.status).toBe("opened");
  });

  test("resolves with error when the viewer tab is closed mid-load", async () => {
    const promise = executePdfRender("https://example.com/d.pdf", undefined, 5000);
    await new Promise((r) => setTimeout(r, 5));
    const tabId = createdTabs[0]!.id;
    for (const fn of removedListeners) fn(tabId);
    await expect(promise).rejects.toThrow("closed before the document loaded");
  });
});
