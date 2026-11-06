import { afterEach, expect, test } from "bun:test";
import { cp, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { BUNDLED_TEARDOWN, bundledTeardown, loadTeardownToolkit } from "../src/interactive-ui/teardown.js";
import { InteractiveUiProjects } from "../src/interactive-ui/project.js";
import { InteractivePageStore } from "../src/interactive-ui/store.js";

const directories: string[] = [];
const originalOverride = process.env.SIADA_TEARDOWN_DIR;
afterEach(async () => {
  if (originalOverride === undefined) delete process.env.SIADA_TEARDOWN_DIR;
  else process.env.SIADA_TEARDOWN_DIR = originalOverride;
  await Promise.all(directories.splice(0).map(path => rm(path, { recursive: true, force: true })));
});
async function temporary() {
  const path = await mkdtemp(join(tmpdir(), "teardown-bundle-"));
  directories.push(path); return path;
}
test("the default toolkit contains all source families and original attribution", async () => {
  delete process.env.SIADA_TEARDOWN_DIR;
  const toolkit = await loadTeardownToolkit();
  expect(toolkit.source).toBe("bundled");
  expect(Object.keys(toolkit.files)).toHaveLength(25);
  expect(toolkit.files["kit/runtime.js"]).toContain("runSim");
  expect(toolkit.files["v8-shared/kin.js"]).toContain("piston");
  expect(toolkit.files["cessna-shared/gear.js"]).toContain("buildGear");
  expect(toolkit.files["strandbeest-shared/jansen.js"]).toContain("solveLeg");
  expect(toolkit.license).toContain("Copyright (c) 2026 elvarofficial");
  expect(toolkit.license).toContain("Copyright (c) 2026 whaleyxbt");
});
test("corrupted resources fail before sources are extracted", async () => {
  const path = await temporary();
  await cp(BUNDLED_TEARDOWN, path, { recursive: true });
  await writeFile(join(path, "sources.json.gz"), Buffer.from("corrupt"));
  await expect(bundledTeardown(path)).rejects.toThrow("integrity");
});
test("a bundled V8 project builds and retains the upstream license", async () => {
  delete process.env.SIADA_TEARDOWN_DIR;
  const pages = new InteractivePageStore(await temporary());
  const projects = new InteractiveUiProjects(pages);
  const project = await projects.create({ title: "Bundled V8", template: "teardown-v8" }) as { id: string; toolkitSource: string; sourceDirectory: string };
  expect(project.toolkitSource).toBe("bundled");
  const built = await projects.build(project.id) as { id: string };
  expect((await pages.read(built.id)).html).toContain("Copyright (c) 2026 elvarofficial");
  expect(await readFile(join(project.sourceDirectory, "v8-shared", "engine.js"), "utf8")).toContain("buildEngine");
});
test("custom projects can bundle both other machine families", async () => {
  delete process.env.SIADA_TEARDOWN_DIR;
  const projects = new InteractiveUiProjects(new InteractivePageStore(await temporary()));
  const project = await projects.create({ title: "Other mechanisms", template: "teardown" }) as { id: string };
  const result = await projects.build(project.id, { "main.js": `
    import {createCessnaStage} from './cessna-shared/stage.js';
    import {createBeestStage} from './strandbeest-shared/stage.js';
    window.mechanisms = {createCessnaStage, createBeestStage};
  ` }) as { htmlBytes: number };
  expect(result.htmlBytes).toBeGreaterThan(10000);
});
test("an explicit invalid override fails instead of silently using another source", async () => {
  process.env.SIADA_TEARDOWN_DIR = join(await temporary(), "missing");
  await expect(loadTeardownToolkit()).rejects.toThrow();
});