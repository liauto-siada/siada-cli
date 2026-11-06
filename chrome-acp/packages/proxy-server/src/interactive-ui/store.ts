import { randomUUID } from "node:crypto";
import { mkdir, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import { join } from "node:path";
import { standaloneDocument, type InteractivePage } from "./document.js";

export const PAGE_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
export const MAX_HTML_BYTES = 2 * 1024 * 1024;
export const MAX_STATE_BYTES = 64 * 1024;

export function validateState(state: unknown): Record<string, unknown> {
  if (!state || typeof state !== "object" || Array.isArray(state)) throw new Error("state must be a JSON object");
  const json = JSON.stringify(state);
  if (Buffer.byteLength(json) > MAX_STATE_BYTES) throw new Error("UI state exceeds 64 KiB");
  return JSON.parse(json) as Record<string, unknown>;
}

export class InteractivePageStore {
  // Serialize read-modify-write per page, including updates from multiple views.
  private writes = new Map<string, Promise<unknown>>();
  constructor(
    readonly directory = process.env.SIADA_UI_DIR || join(homedir(), ".chrome-acp", "pages"),
    private readonly shared = false,
  ) {}

  private file(id: string, suffix = "json"): string {
    if (!PAGE_ID.test(id)) throw new Error("Invalid UI page id");
    return join(this.directory, `${id}.${suffix}`);
  }

  async read(id: string): Promise<InteractivePage> {
    const page = JSON.parse(await readFile(this.file(id), "utf8")) as InteractivePage;
    if (page.version !== 1 || page.id !== id || typeof page.html !== "string" || typeof page.title !== "string") throw new Error("Invalid UI page");
    validateState(page.state);
    return page;
  }

  async list(): Promise<Pick<InteractivePage, "id" | "title" | "updatedAt">[]> {
    await mkdir(this.directory, { recursive: true, mode: 0o700 });
    const names = await readdir(this.directory);
    const pages = await Promise.all(names.filter(name => name.endsWith(".json") && PAGE_ID.test(name.slice(0, -5))).map(async name => {
      const { id, title, updatedAt } = await this.read(name.slice(0, -5));
      return { id, title, updatedAt };
    }));
    return pages.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  async create(input: { title?: unknown; html?: unknown; state?: unknown; revision?: string }): Promise<InteractivePage> {
    if (typeof input.title !== "string" || !input.title.trim() || input.title.length > 200) throw new Error("title must be 1–200 characters");
    if (typeof input.html !== "string" || !input.html.trim() || Buffer.byteLength(input.html) > MAX_HTML_BYTES) throw new Error("html must be nonempty and at most 2 MiB");
    const page: InteractivePage = {
      version: 1, id: randomUUID(), title: input.title, html: input.html,
      state: validateState(input.state ?? {}), updatedAt: new Date().toISOString(),
      ...(input.revision ? { revision: input.revision } : {}),
    };
    await this.persist(page);
    return page;
  }

  async updateState(id: string, state?: unknown): Promise<InteractivePage> {
    this.file(id);
    const validated = state === undefined ? undefined : validateState(state);
    const previous = this.writes.get(id) ?? Promise.resolve();
    const work = previous.catch(() => {}).then(async () => {
      const page = await this.read(id);
      if (validated !== undefined) page.state = validated;
      page.updatedAt = new Date().toISOString();
      await this.persist(page);
      return page;
    });
    this.writes.set(id, work);
    try { return await work; }
    finally { if (this.writes.get(id) === work) this.writes.delete(id); }
  }

  async replaceContent(id: string, html: string, revision: string): Promise<InteractivePage> {
    this.file(id);
    if (!html.trim() || Buffer.byteLength(html) > MAX_HTML_BYTES) throw new Error("UI artifact exceeds 2 MiB");
    if (!/^[0-9a-f]{64}$/.test(revision)) throw new Error("Invalid UI revision");
    const previous = this.writes.get(id) ?? Promise.resolve();
    const work = previous.catch(() => {}).then(async () => {
      const page = await this.read(id);
      page.html = html; page.revision = revision; page.updatedAt = new Date().toISOString();
      await this.persist(page);
      return page;
    });
    this.writes.set(id, work);
    try { return await work; }
    finally { if (this.writes.get(id) === work) this.writes.delete(id); }
  }

  private async persist(page: InteractivePage): Promise<void> {
    await mkdir(this.directory, { recursive: true, mode: 0o700 });
    // JSON is canonical. Routes regenerate HTML from it if a crash interrupts
    // the second rename; the next save repairs the on-disk export.
    const temp = `${this.file(page.id)}.${randomUUID()}.tmp`;
    const htmlTemp = `${temp}.html`;
    try {
      await writeFile(temp, JSON.stringify(page), { mode: 0o600 });
      await writeFile(htmlTemp, standaloneDocument(page, this.shared), { mode: 0o600 });
      await rename(temp, this.file(page.id));
      await rename(htmlTemp, this.file(page.id, "html"));
    } finally {
      await rm(temp, { force: true });
      await rm(htmlTemp, { force: true });
    }
  }
}

export const interactivePages = new InteractivePageStore();