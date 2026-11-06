import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const source = join(root, "packages/proxy-server/src/interactive-ui/resources/teardown");
const target = join(root, "packages/proxy-server/dist/interactive-ui/resources/teardown");
const manifest = JSON.parse(await readFile(join(source, "manifest.json"), "utf8"));
const archive = await readFile(join(source, "sources.json.gz"));
if (createHash("sha256").update(archive).digest("hex") !== manifest.archiveSha256) {
  throw new Error("Bundled teardown source archive does not match its manifest");
}
await mkdir(target, { recursive: true });
for (const name of ["sources.json.gz", "manifest.json", "GUIDE.md", "LICENSE", "README.md"]) {
  await copyFile(join(source, name), join(target, name));
}
console.log(`Bundled teardown resources copied (${archive.length} archive bytes)`);