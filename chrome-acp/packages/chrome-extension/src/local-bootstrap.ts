import type { ACPSettings } from "@chrome-acp/shared/acp";

export function localBootstrapUrl(proxyUrl: string): string | null {
  try {
    const url = new URL(proxyUrl);
    if (!["ws:", "wss:"].includes(url.protocol)
      || !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) return null;
    url.protocol = "http:";
    url.pathname = "/local-bootstrap";
    url.search = "";
    url.hash = "";
    return url.toString();
  } catch {
    return null;
  }
}

export async function discoverLocalSettings(
  settings: ACPSettings,
  extensionId: string,
  fetcher: (input: string, init?: RequestInit) => Promise<Response> = fetch,
  openLogin = false,
): Promise<ACPSettings | { loginRequired: true; terminalOpened?: boolean } | null> {
  const endpoint = localBootstrapUrl(settings.proxyUrl);
  if (!endpoint) return null;
  try {
    const response = await fetcher(endpoint, {
      method: openLogin ? "POST" : "GET",
      headers: { "X-Siada-Extension-Id": extensionId },
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      signal: AbortSignal.timeout(15_000),
    });
    if (!response.ok) return null;
    const data = await response.json();
    if (data?.schemaVersion === 1 && data.authStatus === "login_required") {
      return { loginRequired: true, terminalOpened: data.terminalOpened };
    }
    if (data?.schemaVersion !== 1 || typeof data.token !== "string"
      || typeof data.proxyUrl !== "string" || !localBootstrapUrl(data.proxyUrl)) return null;
    const current = new URL(settings.proxyUrl);
    const discovered = new URL(data.proxyUrl);
    if (current.port !== discovered.port || discovered.pathname !== "/ws") return null;
    return { ...settings, proxyUrl: data.proxyUrl, token: data.token };
  } catch {
    return null;
  }
}