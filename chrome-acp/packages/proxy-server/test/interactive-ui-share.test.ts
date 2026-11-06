import { afterEach, expect, test } from "bun:test";
import { createServer } from "node:http";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Hono } from "hono";
import { InteractivePageShares } from "../src/interactive-ui/share.js";
import { InteractivePageStore } from "../src/interactive-ui/store.js";
import { interactiveUiRoutes } from "../src/interactive-ui/routes.js";

const services: InteractivePageShares[] = [];
const directories: string[] = [];
afterEach(async () => {
  await Promise.all(services.splice(0).map(service => service.stop()));
  await Promise.all(directories.splice(0).map(path => rm(path, { recursive: true, force: true })));
});
async function setup(port = 0, addresses = () => ["192.168.1.20"]) {
  const directory = await mkdtemp(join(tmpdir(), "siada-share-test-"));
  directories.push(directory);
  const pages = new InteractivePageStore(directory);
  const shares = new InteractivePageShares(join(directory, "shared"), port, addresses);
  services.push(shares);
  const page = await pages.create({ title: "Shared budget", html: "<output>Budget</output>", state: { amount: 10 } });
  return { pages, shares, page, app: new Hono().route("/ui", interactiveUiRoutes(pages, "owner-secret", shares)) };
}

test("Share requires owner authorization and exposes only the published snapshot", async () => {
  const { app, page, shares, pages } = await setup();
  const path = `/ui/${page.id}/share`;
  const options = { method: "POST", body: JSON.stringify({ state: { amount: 99 } }), headers: { "Content-Type": "application/json" } };
  expect((await app.request(path, options)).status).toBe(401);
  expect(shares.listening).toBe(false);
  const response = await app.request(path, { ...options, headers: { ...options.headers, Authorization: "Bearer owner-secret" } });
  expect(response.status).toBe(201);
  const result = await response.json();
  expect(result.id).not.toBe(page.id);
  expect(result.url).toBe(`http://192.168.1.20:${shares.port}/share/${result.id}`);
  expect(JSON.stringify(result)).not.toContain("owner-secret");
  const html = await (await fetch(`http://127.0.0.1:${shares.port}/share/${result.id}`)).text();
  expect(html).toContain('"amount":99');
  expect(html).toContain('sandbox="allow-scripts"');
  expect(html).not.toContain('<button id="export">');
  expect(html).not.toContain("owner-secret");
  for (const resource of ["/", "/mcp", "/ws", "/ui", `/share/${page.id}`, `/ui/${page.id}/state`]) {
    expect((await shares.app.request(resource)).status).toBe(404);
  }
  expect((await shares.app.request(`/share/${result.id}`, { method: "POST" })).status).toBe(404);
  await pages.updateState(page.id, { amount: 500 });
  expect((await shares.pages.read(result.id)).state).toEqual({ amount: 99 });
});

test("published files and snapshot identity survive restarting the sharing service", async () => {
  const { shares, page } = await setup();
  const result = await shares.publish(page);
  await shares.stop();
  const reopened = new InteractivePageShares(shares.pages.directory, 0, () => ["192.168.1.20"]);
  services.push(reopened);
  await reopened.restore();
  expect(reopened.listening).toBe(true);
  const response = await fetch(`http://127.0.0.1:${reopened.port}/share/${result.id}`);
  expect(response.status).toBe(200);
  expect(await response.text()).toContain('"amount":10');
  expect(await readFile(join(shares.pages.directory, `${result.id}.html`), "utf8")).not.toContain('<button id="export">');
});

test("concurrent publication starts one listener and preserves independent states", async () => {
  const { shares, page } = await setup();
  const results = await Promise.all([1, 2, 3].map(amount => shares.publish({ ...page, state: { amount } })));
  expect(new Set(results.map(result => result.url)).size).toBe(3);
  expect(new Set(results.map(result => new URL(result.url).port)).size).toBe(1);
  for (let index = 0; index < results.length; index++) expect((await shares.pages.read(results[index]!.id)).state.amount).toBe(index + 1);
});

test("missing network and invalid state do not publish a webpage", async () => {
  const { shares, page, app } = await setup(0, () => []);
  await expect(shares.publish(page)).rejects.toThrow("局域网地址");
  expect(shares.listening).toBe(false);
  const response = await app.request(`/ui/${page.id}/share`, {
    method: "POST", headers: { Authorization: "Bearer owner-secret", "Content-Type": "application/json" }, body: '{"state":[]}',
  });
  expect(response.status).toBe(400);
  expect(await shares.pages.list()).toEqual([]);
});

test("a busy share port fails visibly and can be retried after it is released", async () => {
  const blocker = createServer();
  await new Promise<void>(resolve => blocker.listen(0, "0.0.0.0", resolve));
  const port = (blocker.address() as { port: number }).port;
  const { shares, page } = await setup(port);
  try {
    await expect(shares.publish(page)).rejects.toThrow(`分享服务无法监听端口 ${port}`);
    expect(await shares.pages.list()).toEqual([]);
  } finally {
    await new Promise<void>(resolve => blocker.close(() => resolve()));
  }
  const result = await shares.publish(page);
  expect((await fetch(`http://127.0.0.1:${port}/share/${result.id}`)).status).toBe(200);
});