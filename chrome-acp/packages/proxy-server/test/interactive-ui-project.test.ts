import { afterEach, expect, test } from "bun:test";
import { mkdtemp, readFile, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { InteractiveUiProjects } from "../src/interactive-ui/project.js";
import { InteractivePageStore } from "../src/interactive-ui/store.js";

const directories: string[] = [];
afterEach(async () => { await Promise.all(directories.splice(0).map(path => rm(path, { recursive: true, force: true }))); });
async function setup() {
  const directory = await mkdtemp(join(tmpdir(), "ui-project-test-")); directories.push(directory);
  const pages = new InteractivePageStore(directory);
  return { pages, projects: new InteractiveUiProjects(pages) };
}
const source = `document.getElementById("app").textContent="First working version";`;

test("incremental builds retain page identity and user state, with no bundled source in results", async () => {
  const { projects, pages } = await setup();
  const project = await projects.create({ title: "Source UI" }) as { id: string };
  const first = await projects.build(project.id, { "main.js": source }) as { id: string; revision: string };
  await pages.updateState(first.id, { amount: 42 });
  const second = await projects.build(project.id, { "main.js": source.replace("First", "Second") }) as { id: string; revision: string };
  expect(second.id).toBe(first.id);
  expect(second.revision).not.toBe(first.revision);
  expect((await pages.read(first.id)).state).toEqual({ amount: 42 });
  expect((await pages.read(first.id)).html).toContain("Second working version");
  expect(JSON.stringify(second)).not.toContain("document.getElementById");
});

test("a failed build does not overwrite the last functioning page", async () => {
  const { projects, pages } = await setup();
  const project = await projects.create({ title: "Source UI" }) as { id: string };
  const first = await projects.build(project.id, { "main.js": source }) as { id: string };
  const html = (await pages.read(first.id)).html;
  await expect(projects.build(project.id, { "main.js": "export const broken = ;" })).rejects.toThrow();
  expect((await pages.read(first.id)).html).toBe(html);
  const repaired = await projects.build(project.id, { "main.js": source }) as { id: string };
  expect(repaired.id).toBe(first.id);
});

test("source edits and imports cannot escape the owned project", async () => {
  const { projects } = await setup();
  const project = await projects.create({ title: "Source UI" }) as { id: string; sourceDirectory: string };
  await expect(projects.build(project.id, { "../outside.js": source })).rejects.toThrow("Invalid UI source path");
  await symlink("/etc", join(project.sourceDirectory, "outside"));
  await expect(projects.build(project.id, { "outside/passwd.js": source })).rejects.toThrow("symlinks");
  await rm(join(project.sourceDirectory, "outside"));
  await expect(projects.build(project.id, { "main.js": 'import "node:fs";' })).rejects.toThrow("Node imports");
  await expect(projects.build(project.id, { "main.js": 'import data from "/etc/passwd"; console.log(data);' })).rejects.toThrow("within the project");
});

test("new service instances can rebuild the same persisted project", async () => {
  const { projects, pages } = await setup();
  const project = await projects.create({ title: "Source UI" }) as { id: string };
  const first = await projects.build(project.id, { "main.js": source }) as { id: string };
  const reopened = new InteractiveUiProjects(pages, projects.directory);
  const second = await reopened.build(project.id, { "main.js": source.replace("First", "After restart") }) as { id: string };
  expect(second.id).toBe(first.id);
  expect(await readFile(join(pages.directory, `${first.id}.html`), "utf8")).toContain("After restart");
});