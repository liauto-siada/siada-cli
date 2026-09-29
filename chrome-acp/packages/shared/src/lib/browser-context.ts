// Browser awareness for the chat input (Chrome extension only).
// Collects the current active tab's title/url, the user's text selection on
// the page, and a short excerpt of the visible page content so they can be
// attached to outgoing prompts as context. Resolves to null outside the
// Chrome extension (e.g. web-client) or when the tab cannot be accessed
// (chrome:// pages, etc.).

export interface BrowserContextInfo {
  tabId: number;
  url: string;
  title: string;
  /** Text currently selected on the page (trimmed), if any */
  selection?: string;
  /** Meta description of the page, if present */
  description?: string;
  /** Short excerpt of visible page text (capped, see PAGE_EXCERPT_LIMIT) */
  excerpt?: string;
}

export const PAGE_EXCERPT_LIMIT = 1500;
export const SELECTION_LIMIT = 4000;

interface ChromeScriptingApi {
  executeScript?: <T>(injection: {
    target: { tabId: number };
    func: () => T;
  }) => Promise<{ result?: T }[]>;
}

interface ChromeTabsApi {
  query?: (queryInfo: object) => Promise<{ id?: number; url?: string; title?: string }[]>;
}

function getChromeApi(): { tabs?: ChromeTabsApi; scripting?: ChromeScriptingApi } | undefined {
  return (
    globalThis as {
      chrome?: { tabs?: ChromeTabsApi; scripting?: ChromeScriptingApi };
    }
  ).chrome;
}

export function isBrowserContextAvailable(): boolean {
  const chromeApi = getChromeApi();
  return Boolean(chromeApi?.tabs?.query && chromeApi?.scripting?.executeScript);
}

// Serialized and executed in the page context (ISOLATED world). Must be
// self-contained: no closures over module state.
function collectPageContext(): {
  selection?: string;
  description?: string;
  excerpt?: string;
} {
  const selection = window.getSelection()?.toString().trim() || undefined;
  const description =
    document
      .querySelector('meta[name="description"]')
      ?.getAttribute("content")
      ?.trim() || undefined;
  const text = (document.body?.innerText || "").replace(/\s+\n/g, "\n").trim();
  const excerpt = text
    ? text.slice(0, 1500) + (text.length > 1500 ? "…" : "")
    : undefined;
  return { selection, description, excerpt };
}

/**
 * Best-effort snapshot of the browser context around the active tab.
 * Returns null when not running inside the Chrome extension.
 */
export async function fetchBrowserContext(): Promise<BrowserContextInfo | null> {
  const chromeApi = getChromeApi();
  if (!chromeApi?.tabs?.query) return null;

  try {
    const tabs = await chromeApi.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];
    if (!tab?.id) return null;

    const info: BrowserContextInfo = {
      tabId: tab.id,
      url: tab.url || "",
      title: tab.title || "",
    };

    if (chromeApi.scripting?.executeScript) {
      try {
        const results = await chromeApi.scripting.executeScript({
          target: { tabId: tab.id },
          func: collectPageContext,
        });
        const page = results[0]?.result;
        if (page) {
          if (page.selection) {
            info.selection =
              page.selection.length > SELECTION_LIMIT
                ? page.selection.slice(0, SELECTION_LIMIT) + "…"
                : page.selection;
          }
          if (page.description) info.description = page.description;
          if (page.excerpt) info.excerpt = page.excerpt;
        }
      } catch {
        // Tab not scriptable (chrome://, Web Store, etc.) - tab info still useful
      }
    }

    return info;
  } catch {
    return null;
  }
}

/**
 * Render the browser context as a prompt preamble. Only the parts the user
 * kept enabled are included.
 */
export function formatBrowserContextPrompt(
  info: BrowserContextInfo,
  include: { tab: boolean; selection: boolean; excerpt: boolean },
): string {
  const lines: string[] = [];
  if (include.tab) {
    lines.push(`Current tab: ${info.title || "(untitled)"}`);
    if (info.url) lines.push(`URL: ${info.url}`);
    if (info.description) lines.push(`Page description: ${info.description}`);
  }
  if (include.selection && info.selection) {
    lines.push("", "Selected text on the page:", info.selection);
  }
  if (include.excerpt && info.excerpt) {
    lines.push("", "Page content excerpt:", info.excerpt);
  }
  if (lines.length === 0) return "";
  return `<browser-context>\n${lines.join("\n")}\n</browser-context>\n\n`;
}
