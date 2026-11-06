import { afterEach, describe, expect, test } from "bun:test";
import { mkdtemp, readFile, rm, stat } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Hono } from "hono";
import { InteractivePageStore, MAX_HTML_BYTES, MAX_STATE_BYTES } from "../src/interactive-ui/store.js";
import { frameDocument, standaloneDocument } from "../src/interactive-ui/document.js";
import { interactiveUiRoutes } from "../src/interactive-ui/routes.js";
import { handleMcpRequest } from "../src/mcp/handler.js";

const directories: string[] = [];
afterEach(async () => { await Promise.all(directories.splice(0).map(path => rm(path, { recursive: true, force: true }))); });
async function store() {
  const directory = await mkdtemp(join(tmpdir(), "siada-ui-test-"));
  directories.push(directory);
  return new InteractivePageStore(directory);
}
const input = { title: "Budget", html: "<output id='total'></output><script>total.textContent=siadaUI.state.amount</script>", state: { amount: 10 } };

describe("interactive page persistence", () => {
  test("source, state and offline HTML survive a fresh store instance", async () => {
    const pages = await store();
    const page = await pages.create(input);
    await pages.updateState(page.id, { amount: 25, label: "</script><script>alert(1)</script>" });
    const reopened = new InteractivePageStore(pages.directory);
    expect((await reopened.read(page.id)).state.amount).toBe(25);
    expect((await reopened.list())[0]?.id).toBe(page.id);
    const html = await readFile(join(pages.directory, `${page.id}.html`), "utf8");
    expect(html).toContain('sandbox="allow-scripts"');
    expect(html).toContain('\\u003c/script>');
    expect(html).not.toContain('allow-same-origin');
    expect(html).not.toContain('http://');
    expect((await stat(join(pages.directory, `${page.id}.json`))).mode & 0o777).toBe(0o600);
  });
  test("parallel saves leave one complete final state and valid HTML", async () => {
    const pages = await store();
    const page = await pages.create(input);
    await Promise.all([1, 2, 3].map(amount => pages.updateState(page.id, { amount })));
    expect((await pages.read(page.id)).state).toEqual({ amount: 3 });
    expect(await readFile(join(pages.directory, `${page.id}.html`), "utf8")).toContain('"amount":3');
    await pages.updateState(page.id);
    expect((await pages.read(page.id)).state.amount).toBe(3);
  });
  test("rejects traversal, invalid state and oversized source", async () => {
    const pages = await store();
    await expect(pages.read("../secret")).rejects.toThrow("Invalid UI page id");
    await expect(pages.create({ ...input, state: [] })).rejects.toThrow("JSON object");
    await expect(pages.create({ ...input, state: { text: "x".repeat(65536) } })).rejects.toThrow("64 KiB");
    await expect(pages.create({ ...input, html: "x".repeat(MAX_HTML_BYTES + 1) })).rejects.toThrow("2 MiB");
  });
  test("policies precede authored markup, and serialized title/state cannot escape the host", async () => {
    const pages = await store();
    const page = await pages.create({ ...input, title: '</title><script>alert("host")</script>', state: { label: "</script>" } });
    expect(frameDocument(page).indexOf("Content-Security-Policy")).toBeLessThan(frameDocument(page).indexOf(input.html));
    expect(standaloneDocument(page)).toContain("&lt;/title&gt;");
    expect(standaloneDocument(page)).not.toContain('</title><script>alert("host")');
    expect(frameDocument(page)).toContain("connect-src 'none'");
  });
});

describe("interactive UI HTTP and MCP", () => {
  test("writes/list require auth, capability pages are readable, export retains state", async () => {
    const pages = await store();
    const app = new Hono().route("/ui", interactiveUiRoutes(pages, "test-ui-token"));
    const page = await pages.create(input);
    expect((await app.request("/ui")).status).toBe(401);
    expect((await app.request("/ui/")).status).toBe(401);
    expect((await app.request(`/ui/${page.id}/state`, { method: "POST", body: JSON.stringify({ state: {} }), headers: { "Content-Type": "application/json" } })).status).toBe(401);
    const saved = await app.request(`/ui/${page.id}/state`, {
      method: "POST", headers: { Authorization: "Bearer test-ui-token", "Content-Type": "application/json" },
      body: JSON.stringify({ state: { amount: 99 } }),
    });
    expect(saved.status).toBe(200);
    expect(saved.headers.get("Access-Control-Allow-Origin")).toBe("*");
    const frame = await app.request(`/ui/${page.id}/frame`);
    expect(frame.headers.get("Content-Security-Policy")).toBe("sandbox allow-scripts");
    expect(await frame.text()).toContain('"amount":99');
    const download = await app.request(`/ui/${page.id}/download`);
    expect(download.headers.get("Content-Disposition")).toContain("attachment");
    expect(await download.text()).not.toContain("test-ui-token");
    expect((await app.request(`/ui/${page.id}`)).status).toBe(200);
    expect((await app.request("/ui/invalid", { headers: { Authorization: "Bearer test-ui-token" } })).status).toBe(404);
  });
  test("body limits and bad payloads fail without changing existing state", async () => {
    const pages = await store();
    const page = await pages.create(input);
    const app = new Hono().route("/ui", interactiveUiRoutes(pages));
    const options = { method: "POST", headers: { "Content-Type": "application/json" } };
    expect((await app.request(`/ui/${page.id}/state`, { ...options, body: "{}" })).status).toBe(400);
    expect((await app.request(`/ui/${page.id}/state`, { ...options, body: JSON.stringify({ state: [] }) })).status).toBe(400);
    expect((await app.request("/ui/", { ...options, body: "x".repeat(MAX_HTML_BYTES + MAX_STATE_BYTES + 16385) })).status).toBe(413);
    expect((await pages.read(page.id)).state).toEqual({ amount: 10 });
  });
  test("ACP-provided browser MCP advertises all UI tools without an extension executor", async () => {
    const app = new Hono().post("/mcp", handleMcpRequest);
    const response = await app.request("/mcp", { method: "POST", body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/list" }), headers: { "Content-Type": "application/json" } });
    const body = await response.json();
    expect(body.result.tools.map((tool: { name: string }) => tool.name)).toEqual(expect.arrayContaining(["browser_present_ui", "browser_ui_project", "browser_ui_build", "browser_ui_inspect", "browser_share_ui", "browser_save_ui", "browser_list_ui", "browser_read"]));
    const bad = await app.request("/mcp", { method: "POST", body: JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name: "browser_present_ui", arguments: { title: "Bad", html: "" } } }), headers: { "Content-Type": "application/json" } });
    expect((await bad.json()).result.isError).toBe(true);
  });
});