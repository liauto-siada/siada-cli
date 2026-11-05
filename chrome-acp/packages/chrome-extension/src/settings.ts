// Persisted ACP settings for the Chrome extension.
// The sidepanel writes the effective settings here so the background service
// worker (e.g. the immersive explain feature) can reach the same proxy
// without the panel being open.

import { DEFAULT_SETTINGS, type ACPSettings } from "@chrome-acp/shared/acp";

export const ACP_SETTINGS_KEY = "acp_settings";

/**
 * Merge persisted settings over the built-in defaults. Both the tool channel
 * and the trajectory channel must resolve their endpoint from the same
 * effective settings so remote deployments (custom proxyUrl) stay consistent.
 */
export function resolveProxySettings(
  stored: Partial<ACPSettings> | undefined,
): ACPSettings {
  return { ...DEFAULT_SETTINGS, ...stored };
}

/**
 * Build the trajectory WebSocket URL from the user-configured proxy URL:
 * keep the scheme/host/port and only replace the pathname with
 * /ws/trajectory (no token needed — the trajectory endpoint has none).
 */
export function trajectoryWsUrlFor(proxyUrl: string): string {
  const url = new URL(proxyUrl);
  url.pathname = "/ws/trajectory";
  return url.toString();
}

/**
 * Flip a ws:// URL to wss:// (or vice versa) when it targets a loopback
 * host; returns null for non-loopback or non-WS URLs. Mirrors ACPClient's
 * connect-time fallback: the proxy's dual-protocol listener serves
 * plaintext to loopback peers even in --https mode, while Chrome rejects
 * the self-signed certificate for wss://localhost
 * (ERR_CERT_AUTHORITY_INVALID).
 */
export function flipLoopbackWsScheme(url: string): string | null {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.replace(/^\[|\]$/g, "");
    const isLoopback =
      host === "localhost" || host === "127.0.0.1" || host === "::1";
    if (!isLoopback || (parsed.protocol !== "ws:" && parsed.protocol !== "wss:")) {
      return null;
    }
    parsed.protocol = parsed.protocol === "ws:" ? "wss:" : "ws:";
    return parsed.toString();
  } catch {
    return null;
  }
}

export async function loadStoredSettings(): Promise<Partial<ACPSettings> | undefined> {
  try {
    const stored = await chrome.storage.local.get(ACP_SETTINGS_KEY);
    return stored[ACP_SETTINGS_KEY] as Partial<ACPSettings> | undefined;
  } catch {
    return undefined;
  }
}

export function persistSettings(settings: ACPSettings): void {
  chrome.storage.local.set({ [ACP_SETTINGS_KEY]: settings }).catch(() => {});
}

// ---------------------------------------------------------------------------
// Immersive explain toggle ("划词解释" floating button in pages).
// Stored separately from ACPSettings since it only concerns the extension's
// content script; defaults to OFF so pages are never disturbed unless the
// user explicitly opts in.
// ---------------------------------------------------------------------------

export const EXPLAIN_ENABLED_KEY = "explain_enabled";

export async function loadExplainEnabled(): Promise<boolean> {
  try {
    const stored = await chrome.storage.local.get(EXPLAIN_ENABLED_KEY);
    return stored[EXPLAIN_ENABLED_KEY] === true;
  } catch {
    return false;
  }
}

export function persistExplainEnabled(enabled: boolean): void {
  chrome.storage.local.set({ [EXPLAIN_ENABLED_KEY]: enabled }).catch(() => {});
}

// ---------------------------------------------------------------------------
// PDF handler toggle ("使用 Siada 打开 PDF"): when ON, declarativeNetRequest
// rules redirect PDF navigations to the extension's built-in pdf.js viewer
// (see src/pdf/pdf-handler.ts). Default OFF so the browser's built-in PDF
// viewer keeps working unless the user explicitly opts in.
// ---------------------------------------------------------------------------

export const PDF_HANDLER_ENABLED_KEY = "pdf_handler_enabled";

export async function loadPdfHandlerEnabled(): Promise<boolean> {
  try {
    const stored = await chrome.storage.local.get(PDF_HANDLER_ENABLED_KEY);
    return stored[PDF_HANDLER_ENABLED_KEY] === true;
  } catch {
    return false;
  }
}

export function persistPdfHandlerEnabled(enabled: boolean): void {
  chrome.storage.local.set({ [PDF_HANDLER_ENABLED_KEY]: enabled }).catch(() => {});
}
