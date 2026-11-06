import { createHash, randomUUID } from "node:crypto";
import { mkdir, readFile, readdir, realpath, rename, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { dirname, extname, isAbsolute, join, relative, resolve, sep } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import * as esbuild from "esbuild";
import { InteractivePageStore, MAX_HTML_BYTES, PAGE_ID, validateState } from "./store.js";

interface UiProject {
  version: 1;
  id: string;
  title: string;
  template: string;
  entry: string;
  pageId?: string;
  builds: number;
}
const ASSETS = dirname(fileURLToPath(new URL("./templates/viewer.js", import.meta.url)));
const MAX_SOURCE_BYTES = 1024 * 1024;
const MAX_EDIT_BYTES = 256 * 1024;
const require = createRequire(import.meta.url);
const inside = (root: string, path: string) => path === root || path.startsWith(root + sep);

/** Model-selected source workspaces. No prompt classification or nested model. */
export class InteractiveUiProjects {
  private operations = new Map<string, Promise<unknown>>();
  constructor(readonly pages: InteractivePageStore, readonly directory = join(pages.directory, "projects")) {}

  private root(id: string): string {
    if (!PAGE_ID.test(id)) throw new Error("Invalid UI project id");
    return join(this.directory, id);
  }
  private async ownedRoot(id: string): Promise<string> {
    const root = this.root(id);
    const actual = await realpath(root);
    if (actual !== join(await realpath(this.directory), id)) throw new Error("UI project symlinks are not allowed");
    return actual;
  }
  private async read(id: string): Promise<UiProject> {
    const root = await this.ownedRoot(id);
    const project = JSON.parse(await readFile(join(root, "project.json"), "utf8")) as UiProject;
    if (project.version !== 1 || project.id !== id) throw new Error("Invalid UI project");
    return project;
  }
  private async save(project: UiProject): Promise<void> {
    const root = await this.ownedRoot(project.id);
    const temp = join(root, `project.${randomUUID()}.tmp`);
    await writeFile(temp, JSON.stringify(project), { mode: 0o600 });
    await rename(temp, join(root, "project.json"));
  }
  private async serialized<T>(id: string, action: () => Promise<T>): Promise<T> {
    const previous = this.operations.get(id) ?? Promise.resolve();
    const work = previous.catch(() => {}).then(action);
    this.operations.set(id, work);
    try { return await work; }
    finally { if (this.operations.get(id) === work) this.operations.delete(id); }
  }
  private sourcePath(root: string, name: string): string {
    if (typeof name !== "string" || name.length > 180 || isAbsolute(name)
      || name.includes("\\") || name.split("/").some(part => !part || part === "." || part === ".." || part.startsWith("."))
      || ![".js", ".ts", ".css", ".json", ".glb", ".png", ".jpg", ".webp"].includes(extname(name))) throw new Error("Invalid UI source path");
    const path = resolve(root, name);
    if (!inside(root, path)) throw new Error("UI source path escapes the project");
    return path;
  }
  private async sources(root: string): Promise<string[]> {
    const files: string[] = [];
    let total = 0;
    const visit = async (path: string) => {
      for (const item of await readdir(path, { withFileTypes: true })) {
        if (item.isSymbolicLink()) throw new Error("UI source symlinks are not allowed");
        const file = join(path, item.name);
        if (item.isDirectory()) await visit(file);
        else if (item.isFile()) {
          total += (await stat(file)).size;
          if (total > MAX_SOURCE_BYTES || files.length >= 256) throw new Error("UI source workspace exceeds its limit");
          files.push(relative(root, file).split(sep).join("/"));
        }
      }
    };
    await visit(root);
    return files;
  }
  private async copySources(source: string, target: string): Promise<void> {
    await mkdir(target, { recursive: true, mode: 0o700 });
    for (const item of await readdir(source, { withFileTypes: true })) {
      if (item.isSymbolicLink()) throw new Error("Teardown source symlinks are not supported");
      if (item.isDirectory()) await this.copySources(join(source, item.name), join(target, item.name));
      else if ([".js", ".css"].includes(extname(item.name))) {
        await writeFile(join(target, item.name), await readFile(join(source, item.name)), { mode: 0o600 });
      }
    }
  }
  private async teardownDirectory(): Promise<string> {
    const candidates = process.env.SIADA_TEARDOWN_DIR
      ? [process.env.SIADA_TEARDOWN_DIR]
      : [join(homedir(), ".siada-cli", "skills", "teardown"), join(homedir(), ".agents", "skills", "teardown")];
    for (const path of candidates) {
      try {
        const root = await realpath(path);
        await stat(join(root, "sims", "kit", "runtime.js"));
        await stat(join(root, "LICENSE"));
        return root;
      } catch { /* Try the next public skill installation location. */ }
    }
    throw new Error("Teardown skill is unavailable. Install elvarofficial/teardown, or set SIADA_TEARDOWN_DIR to its installation.");
  }

  async create(input: { title?: unknown; template?: unknown }): Promise<object> {
    if (typeof input.title !== "string" || !input.title.trim() || input.title.length > 200) throw new Error("title must be 1–200 characters");
    const template = input.template ?? "blank";
    if (!["blank", "teardown", "teardown-v8"].includes(String(template))) throw new Error("Unknown UI template");
    const teardown = template === "blank" ? undefined : await this.teardownDirectory();
    const project: UiProject = { version: 1, id: randomUUID(), title: input.title, template: String(template), entry: "main.js", builds: 0 };
    await mkdir(this.root(project.id), { recursive: true, mode: 0o700 });
    const root = await this.ownedRoot(project.id), source = join(root, "src");
    await mkdir(source, { recursive: true, mode: 0o700 });
    await writeFile(join(source, "viewer.js"), await readFile(join(ASSETS, "viewer.js")), { mode: 0o600 });
    if (teardown) {
      await this.copySources(join(teardown, "sims", "kit"), join(source, "kit"));
      for (const name of ["v8-shared", "cessna-shared", "strandbeest-shared"]) {
        await this.copySources(join(teardown, "sims", name), join(source, name));
      }
      await writeFile(join(root, "teardown-license.txt"), await readFile(join(teardown, "LICENSE")), { mode: 0o600 });
      const guide = "# Chrome ACP integration\n\nThis workspace already supplies dependencies and copied source modules under src/. browser_ui_build presents the working page immediately inside the current chat. Do not require a separate page or an inspection step to see it. Inspect only when useful for a specific uncertainty, reuse findings, and avoid repeated unchanged checks. Do not run upstream first-run installers here. Import ./viewer.js for responsive controls and siadaUI capture/restore. The upstream guide below describes the original skill layout and is reference material. Model the mechanism from references and refine useful details. Share only when requested.\n\n";
      await writeFile(join(root, "GUIDE.md"), guide + await readFile(join(teardown, "SKILL.md"), "utf8"), { mode: 0o600 });
    }
    if (template === "teardown-v8") {
      await writeFile(join(source, "main.js"), await readFile(join(ASSETS, "v8.js")), { mode: 0o600 });
    } else await writeFile(join(source, "main.js"), await readFile(join(ASSETS, "blank.js")), { mode: 0o600 });
    await this.save(project);
    return {
      id: project.id, title: project.title, sourceDirectory: source, entry: project.entry,
      files: await this.sources(source), guide: teardown ? join(root, "GUIDE.md") : undefined,
      instructions: "Edit small modules with browser_ui_build files or normal file tools. Import three, three/addons/*, teardown-kit/* or ./viewer.js. mountViewer bridges capture, restore, visibility and responsive controls. Build presents inline immediately. Inspection and further refinement are optional decisions based on useful evidence, not a fixed sequence. Do not paste bundled HTML back into a tool.",
    };
  }

  async build(id: string, edits: unknown = {}, entry?: unknown, initialState?: unknown): Promise<object> {
    return this.serialized(id, async () => {
      const project = await this.read(id), root = await this.ownedRoot(id), source = join(root, "src");
      if (await realpath(source) !== resolve(source)) throw new Error("UI source directory is not owned");
      await this.sources(source);
      if (!edits || typeof edits !== "object" || Array.isArray(edits)) throw new Error("files must be an object of source text");
      if (Buffer.byteLength(JSON.stringify(edits)) > MAX_EDIT_BYTES) throw new Error("UI source edit exceeds 256 KiB");
      for (const [name, text] of Object.entries(edits)) {
        if (typeof text !== "string") throw new Error("UI source edits must be text");
        const path = this.sourcePath(source, name);
        await mkdir(dirname(path), { recursive: true, mode: 0o700 });
        await writeFile(path, text, { mode: 0o600 });
      }
      if (entry !== undefined) {
        if (typeof entry !== "string") throw new Error("entry must be a relative source file");
        this.sourcePath(source, entry); project.entry = entry;
      }
      await this.sources(source);
      const sourceRoot = await realpath(source);
      if (sourceRoot !== resolve(source)) throw new Error("UI source directory is not owned");
      const threeRoot = await realpath(resolve(dirname(require.resolve("three")), ".."));
      const started = performance.now();
      const context = await esbuild.context({
        entryPoints: [this.sourcePath(source, project.entry)], bundle: true, write: false,
        outdir: join(root, "bundle"),
        platform: "browser", format: "esm", target: "es2022", minify: true,
        nodePaths: [dirname(threeRoot)], legalComments: "inline",
        loader: { ".glb": "base64", ".png": "dataurl", ".jpg": "dataurl", ".webp": "dataurl" },
        plugins: [{
          name: "owned-ui-sources",
          setup(build) {
            build.onResolve({ filter: /^teardown-kit\// }, args => ({ path: resolve(sourceRoot, "kit", args.path.slice("teardown-kit/".length)) }));
            build.onResolve({ filter: /^(https?:|file:|node:)/ }, () => ({ errors: [{ text: "External and Node imports are not allowed in UI artifacts" }] }));
            build.onLoad({ filter: /.*/ }, async args => {
              const path = await realpath(args.path);
              if (!inside(sourceRoot, path) && !inside(threeRoot, path)) return { errors: [{ text: "UI imports must stay within the project or the installed Three.js package" }] };
              return undefined;
            });
          },
        }],
        logLevel: "silent",
      });
      const timer = setTimeout(() => { void context.cancel(); }, 30000);
      let result: esbuild.BuildResult;
      try { result = await context.rebuild(); }
      finally { clearTimeout(timer); await context.dispose(); }
      let license = await readFile(join(threeRoot, "LICENSE"), "utf8");
      if (project.template !== "blank") license += await readFile(join(root, "teardown-license.txt"), "utf8");
      const javascript = result.outputFiles?.find(file => !file.path.endsWith(".css"))?.text;
      if (!javascript) throw new Error("UI build produced no script");
      const css = result.outputFiles?.filter(file => file.path.endsWith(".css")).map(file => file.text).join("\n") ?? "";
      const html = `<style>${css.replace(/<\/style/gi, "<\\/style")}</style><div id="app"></div><script type="module">${javascript.replace(/<\/script/gi, "<\\/script")}</script><!-- ${license.replace(/--/g, "- -")} -->`;
      if (Buffer.byteLength(html) > MAX_HTML_BYTES) throw new Error("Built UI exceeds the 2 MiB artifact limit");
      const revision = createHash("sha256").update(html).digest("hex");
      const page = project.pageId
        ? await this.pages.replaceContent(project.pageId, html, revision)
        : await this.pages.create({ title: project.title, html, state: initialState === undefined ? {} : validateState(initialState), revision });
      project.pageId = page.id; project.builds++;
      await this.save(project);
      return {
        id: page.id, title: page.title, revision, projectId: project.id,
        htmlBytes: Buffer.byteLength(html), buildMilliseconds: Math.round(performance.now() - started),
        builds: project.builds, next: "The UI is now displayed inline in the current chat. Explain it here. Decide whether targeted edits or optional inspection would help; avoid redundant checks. Share only if requested.",
      };
    });
  }
}