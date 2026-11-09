import { createAdaptorServer, type ServerType } from "@hono/node-server";
import { Hono } from "hono";
import { networkInterfaces } from "node:os";
import { standaloneDocument, type InteractivePage } from "./document.js";
import { InteractivePageStore, validateState } from "./store.js";

export function lanAddresses(): string[] {
  const addresses: string[] = [];
  for (const [name, entries] of Object.entries(networkInterfaces())) {
    // VPN/tunnel interfaces do not identify the local Wi-Fi/Ethernet network.
    if (/^(utun|tun|tap|tailscale|wg|docker|veth)/i.test(name)) continue;
    for (const entry of entries ?? []) {
      if (entry.internal || entry.family !== "IPv4") continue;
      if (/^(10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2\d|3[01])\.)/.test(entry.address)) addresses.push(entry.address);
    }
  }
  return [...new Set(addresses)];
}

export interface SharedUiPage {
  id: string;
  title: string;
  url: string;
  urls: string[];
  updatedAt: string;
}

/** Owns a read-only LAN listener and immutable, explicitly published snapshots. */
export class InteractivePageShares {
  readonly pages: InteractivePageStore;
  readonly app = new Hono();
  private server?: ServerType;
  private starting?: Promise<void>;
  private stopped = false;

  constructor(
    directory: string,
    private readonly requestedPort: number,
    private readonly addresses: () => string[] = lanAddresses,
  ) {
    if (!Number.isInteger(requestedPort) || requestedPort < 0 || requestedPort > 65535) throw new Error("Invalid UI share port");
    this.pages = new InteractivePageStore(directory, true);
    this.app.use("*", async (c, next) => {
      c.header("Referrer-Policy", "no-referrer");
      c.header("X-Content-Type-Options", "nosniff");
      c.header("Cache-Control", "no-store");
      await next();
    });
    this.app.get("/share/:id", async c => {
      try { return c.html(standaloneDocument(await this.pages.read(c.req.param("id")), true)); }
      catch { return c.text("Shared page not found", 404); }
    });
    this.app.all("*", c => c.text("Not found", 404));
  }

  get port(): number | null {
    const address = this.server?.address();
    return address && typeof address !== "string" ? address.port : null;
  }

  get listening(): boolean { return this.server?.listening ?? false; }

  async start(): Promise<void> {
    if (this.stopped) throw new Error("UI sharing service is closed");
    if (this.listening) return;
    if (!this.starting) {
      const server = createAdaptorServer({ fetch: this.app.fetch });
      this.server = server;
      this.starting = new Promise<void>((resolve, reject) => {
        server.once("error", reject);
        server.listen(this.requestedPort, "0.0.0.0", resolve);
      }).catch(() => {
        throw new Error(`分享服务无法监听端口 ${this.requestedPort}，请检查端口占用后重试`);
      }).finally(() => { this.starting = undefined; });
    }
    await this.starting;
  }

  /** Previously issued links remain available after a proxy restart. */
  async restore(): Promise<void> {
    if ((await this.pages.list()).length > 0) await this.start();
  }

  async publish(page: InteractivePage): Promise<SharedUiPage> {
    const snapshot = { title: page.title, html: page.html, state: validateState(page.state) };
    const addresses = this.addresses();
    if (!addresses.length) throw new Error("没有可用的局域网地址，请连接 Wi-Fi 或有线网络后重试");
    await this.start();
    if (this.stopped || !this.listening) throw new Error("UI sharing service is closed");
    const published = await this.pages.create(snapshot);
    const port = this.port;
    if (this.stopped || port === null) throw new Error("UI sharing service is closed");
    const urls = addresses.map(address => `http://${address}:${port}/share/${published.id}`);
    return { id: published.id, title: published.title, url: urls[0]!, urls, updatedAt: published.updatedAt };
  }

  async stop(): Promise<void> {
    this.stopped = true;
    await this.starting?.catch(() => {});
    const server = this.server;
    this.server = undefined;
    if (server?.listening) await new Promise<void>((resolve, reject) => {
      server.close(error => error ? reject(error) : resolve());
    });
  }
}