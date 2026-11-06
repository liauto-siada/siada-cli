import { Hono } from "hono";
import { bodyLimit } from "hono/body-limit";
import { cors } from "hono/cors";
import { frameDocument, standaloneDocument } from "./document.js";
import { InteractivePageStore, MAX_HTML_BYTES, MAX_STATE_BYTES, PAGE_ID, validateState } from "./store.js";
import type { InteractivePageShares } from "./share.js";

export function interactiveUiRoutes(store: InteractivePageStore, token?: string, shares?: InteractivePageShares): Hono {
  const app = new Hono();
  app.use("*", async (c, next) => {
    c.header("Referrer-Policy", "no-referrer");
    c.header("X-Content-Type-Options", "nosniff");
    c.header("Cache-Control", "no-store");
    await next();
  });
  app.use("*", cors({ origin: "*", allowMethods: ["GET", "POST", "OPTIONS"], allowHeaders: ["Authorization", "Content-Type"] }));
  app.use("*", bodyLimit({ maxSize: MAX_HTML_BYTES + MAX_STATE_BYTES + 16384 }));
  app.use("*", async (c, next) => {
    // UUID URLs are read-only capabilities. Writes and the library listing
    // require the proxy token; never put that token in page HTML or links.
    const segments = c.req.path.split("/").filter(Boolean);
    const last = segments.at(-1) ?? "";
    const pageId = last === "frame" || last === "download" ? segments.at(-2) ?? "" : last;
    const capabilityRead = c.req.method === "GET" && PAGE_ID.test(pageId);
    if (!capabilityRead && token && c.req.header("Authorization") !== `Bearer ${token}`) {
      return c.json({ error: "Unauthorized" }, 401);
    }
    await next();
  });
  app.get("/", async c => c.json(await store.list()));
  app.post("/", async c => {
    try { return c.json(await store.create(await c.req.json()), 201); }
    catch (error) { return c.json({ error: (error as Error).message }, 400); }
  });
  app.post("/:id/state", async c => {
    try {
      const body = await c.req.json();
      if (!Object.hasOwn(body, "state")) return c.json({ error: "state is required" }, 400);
      return c.json(await store.updateState(c.req.param("id"), body.state));
    } catch (error) { return c.json({ error: (error as Error).message }, 400); }
  });
  app.post("/:id/share", async c => {
    if (!shares) return c.json({ error: "UI sharing is unavailable" }, 503);
    try {
      const body = await c.req.json();
      const page = await store.read(c.req.param("id"));
      if (Object.hasOwn(body, "state")) page.state = validateState(body.state);
      return c.json(await shares.publish(page), 201);
    } catch (error) { return c.json({ error: (error as Error).message }, 400); }
  });
  app.get("/:id/frame", async c => {
    try {
      const page = await store.read(c.req.param("id"));
      // A response sandbox also protects this URL when opened as a top-level tab.
      c.header("Content-Security-Policy", "sandbox allow-scripts");
      return c.html(frameDocument(page));
    } catch { return c.text("UI page not found", 404); }
  });
  app.get("/:id/download", async c => {
    try {
      const page = await store.read(c.req.param("id"));
      c.header("Content-Disposition", `attachment; filename="siada-ui-${page.id}.html"`);
      return c.html(standaloneDocument(page));
    } catch { return c.text("UI page not found", 404); }
  });
  app.get("/:id", async c => {
    try { return c.html(standaloneDocument(await store.read(c.req.param("id")))); }
    catch { return c.text("UI page not found", 404); }
  });
  return app;
}