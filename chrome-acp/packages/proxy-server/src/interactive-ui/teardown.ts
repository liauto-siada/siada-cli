import { createHash } from "node:crypto";
import { readFile, readdir, realpath } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gunzipSync } from "node:zlib";

export const BUNDLED_TEARDOWN = fileURLToPath(new URL("./resources/teardown/", import.meta.url));
const FAMILY = ["kit", "v8-shared", "cessna-shared", "strandbeest-shared"];
const SOURCE_PATH = /^(kit|v8-shared|cessna-shared|strandbeest-shared)\/[a-zA-Z0-9_-]+\.(js|css)$/;
const MAX_SOURCE = 1024 * 1024;
interface SourceManifest {
  version: number;
  archiveSha256: string;
  sourceBytes: number;
  files: { path: string; bytes: number; sha256: string }[];
}
export interface TeardownToolkit {
  source: "bundled" | "override";
  files: Record<string, string>;
  license: string;
  guide: string;
}
const digest = (data: string | Buffer) => createHash("sha256").update(data).digest("hex");

/** Validate bundled data before writing any source into an editable workspace. */
export async function bundledTeardown(directory = BUNDLED_TEARDOWN): Promise<TeardownToolkit> {
  const [archive, manifestText, license, guide] = await Promise.all([
    readFile(join(directory, "sources.json.gz")), readFile(join(directory, "manifest.json"), "utf8"),
    readFile(join(directory, "LICENSE"), "utf8"), readFile(join(directory, "GUIDE.md"), "utf8"),
  ]);
  const manifest = JSON.parse(manifestText) as SourceManifest;
  if (manifest.version !== 1 || digest(archive) !== manifest.archiveSha256 || !license.trim() || !guide.trim()) {
    throw new Error("Bundled teardown resources failed integrity validation");
  }
  const payload = JSON.parse(gunzipSync(archive, { maxOutputLength: MAX_SOURCE }).toString("utf8")) as { version: number; files: Record<string, unknown> };
  if (payload.version !== 1 || !payload.files || typeof payload.files !== "object"
    || !Array.isArray(manifest.files) || !manifest.files.length || manifest.files.length > 64
    || Object.keys(payload.files).length !== manifest.files.length) throw new Error("Invalid bundled teardown manifest");
  const files: Record<string, string> = {};
  let total = 0;
  for (const entry of manifest.files) {
    const content = payload.files[entry.path];
    if (!SOURCE_PATH.test(entry.path) || Object.hasOwn(files, entry.path) || typeof content !== "string"
      || Buffer.byteLength(content) !== entry.bytes || digest(content) !== entry.sha256) throw new Error("Bundled teardown source does not match its manifest");
    files[entry.path] = content;
    total += entry.bytes;
  }
  if (total !== manifest.sourceBytes || total > MAX_SOURCE) throw new Error("Bundled teardown source size is invalid");
  for (const family of FAMILY) {
    if (!Object.keys(files).some(path => path.startsWith(`${family}/`))) throw new Error(`Bundled teardown is missing ${family}`);
  }
  return { source: "bundled", files, license, guide };
}

/** An explicit override is supported; normal use never reads user skill roots. */
export async function loadTeardownToolkit(): Promise<TeardownToolkit> {
  if (!process.env.SIADA_TEARDOWN_DIR) return bundledTeardown();
  const root = await realpath(process.env.SIADA_TEARDOWN_DIR);
  const files: Record<string, string> = {};
  let total = 0;
  for (const family of FAMILY) {
    for (const item of await readdir(join(root, "sims", family), { withFileTypes: true })) {
      if (item.isSymbolicLink()) throw new Error("Teardown override source symlinks are not supported");
      const path = `${family}/${item.name}`;
      if (!item.isFile() || !SOURCE_PATH.test(path)) continue;
      const text = await readFile(join(root, "sims", path), "utf8");
      total += Buffer.byteLength(text);
      if (total > MAX_SOURCE || Object.keys(files).length >= 64) throw new Error("Teardown override exceeds source limits");
      files[path] = text;
    }
  }
  const [license, guide] = await Promise.all([
    readFile(join(root, "LICENSE"), "utf8"), readFile(join(root, "SKILL.md"), "utf8"),
  ]);
  if (!license.trim() || !guide.trim()) throw new Error("Teardown override needs a license and guide");
  return { source: "override", files, license, guide };
}