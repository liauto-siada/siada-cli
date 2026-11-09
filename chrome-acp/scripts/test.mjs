/** Run test files with their package configuration and isolated globals. */
import {readdirSync} from "node:fs";
import {spawnSync} from "node:child_process";
import {dirname, join, relative, resolve} from "node:path";
import {fileURLToPath} from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const domSetup = join(root, "packages/chrome-extension/test/setup.ts");
const excluded = new Set(["node_modules", "dist", "public", "release"]);

function testFiles(directory) {
  const files = [];
  for (const entry of readdirSync(directory, {withFileTypes: true})) {
    if (excluded.has(entry.name)) continue;
    const path = join(directory, entry.name);
    if (entry.isDirectory()) files.push(...testFiles(path));
    else if (entry.isFile() && /\.test\.[jt]sx?$/.test(entry.name)) files.push(path);
  }
  return files.sort();
}

let count = 0;
let failed = 0;
for (const name of ["shared", "chrome-extension", "web-client", "proxy-server"]) {
  const directory = join(root, "packages", name);
  for (const file of testFiles(directory)) {
    const args = ["test"];
    if (name === "shared" || name === "web-client") args.push("--preload", domSetup);
    args.push(relative(directory, file));
    const result = spawnSync("bun", args, {cwd: directory, stdio: "inherit"});
    count++;
    if (result.error) throw result.error;
    if (result.status !== 0) failed++;
  }
}
if (!count) throw new Error("No browser tests found");
console.log(`Browser tests: ${count - failed}/${count} files passed`);
if (failed) process.exitCode = 1;