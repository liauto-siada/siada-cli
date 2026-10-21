import type { Context } from "hono";
import type { HttpBindings } from "@hono/node-server";
import { isIP } from "node:net";

export function isLoopbackAddress(address: string | undefined): boolean {
  const peer = (address ?? "").replace(/^::ffff:/, "");
  return peer === "::1" || (isIP(peer) === 4 && peer.startsWith("127."));
}

export function allowLocalBootstrap(
  request: { url: string; origin?: string; extensionId?: string; peer?: string; encrypted?: boolean },
  allowedIds: string[],
): boolean {
  // The dual-protocol proxy forwards remote TLS through a loopback socket.
  // Reject the TLS leg entirely; local Chrome always uses plaintext HTTP.
  if (request.encrypted || !isLoopbackAddress(request.peer)) return false;
  const url = new URL(request.url);
  if (url.protocol !== "http:" || !["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) return false;
  const id = request.extensionId ?? "";
  if (!/^[a-p]{32}$/.test(id) || !allowedIds.includes(id)) return false;
  // Chrome extension fetch may omit Origin. Websites cannot set this custom
  // header without a successful preflight, which this route never permits.
  return !request.origin || request.origin === `chrome-extension://${id}`;
}

export function localBootstrapHandler(
  token: string | undefined, port: number, allowedIds: string[],
  login?: { check: () => Promise<string>; open: () => Promise<boolean> },
) {
  return async (c: Context<{ Bindings: HttpBindings }>) => {
    const socket = c.env.incoming.socket;
    if (!allowLocalBootstrap({
      url: c.req.url,
      origin: c.req.header("Origin"),
      extensionId: c.req.header("X-Siada-Extension-Id"),
      peer: socket.remoteAddress,
      encrypted: "encrypted" in socket && socket.encrypted === true,
    }, allowedIds)) {
      return c.json({ error: "Forbidden" }, 403);
    }
    c.header("Cache-Control", "no-store");
    c.header("Vary", "Origin, X-Siada-Extension-Id");
    if (login) {
      const authStatus = await login.check();
      if (authStatus === "login_required") {
        const opened = c.req.method === "POST" ? await login.open() : undefined;
        return c.json({ schemaVersion: 1, authStatus, terminalOpened: opened });
      }
    }
    return c.json({ schemaVersion: 1, proxyUrl: `ws://127.0.0.1:${port}/ws`, token: token ?? "" });
  };
}