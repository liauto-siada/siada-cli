/** Generate dependency notices from the installed tree and copy them to artifacts. */
import {readFileSync, writeFileSync, readdirSync, existsSync, realpathSync, statSync, mkdirSync, copyFileSync} from "node:fs";
import {resolve, join, dirname, relative, isAbsolute} from "node:path";
import {fileURLToPath} from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const installed = join(root, "node_modules");
let installedRoots = [installed];
const seen = new Set();
const packages = new Map();

function collect(directory) {
  const real = realpathSync(directory);
  if (seen.has(real)) return;
  seen.add(real);
  if (!installedRoots.some(base => {
    const path = relative(base, real);
    return path === "" || (path !== ".." && !path.startsWith(".." + (process.platform === "win32" ? "\\" : "/")) && !isAbsolute(path));
  })) return;
  const manifest = join(real, "package.json");
  if (existsSync(manifest)) {
    const pkg = JSON.parse(readFileSync(manifest, "utf8"));
    if (pkg.name && pkg.version) {
      const texts = readdirSync(real)
        .filter(name => /^(licen[cs]e|copying|notice)(\.|$|-)/i.test(name))
        .filter(name => statSync(join(real, name)).isFile())
        .map(name => readFileSync(join(real, name), "utf8"));
      // Some packages place their license declaration in their README.
      if (!texts.length) {
        const readme = readdirSync(real).find(name => /^readme(\.|$)/i.test(name));
        if (readme) texts.push(readFileSync(join(real, readme), "utf8"));
      }
      if (!pkg.license && !texts.length) throw new Error(`No license information for ${pkg.name}@${pkg.version}`);
      packages.set(`${pkg.name}@${pkg.version}`, {
        name: pkg.name, version: pkg.version, license: pkg.license ?? "See included notice", texts,
      });
    }
    const nested = join(real, "node_modules");
    if (existsSync(nested)) collect(nested);
    return;
  }
  for (const entry of readdirSync(real, {withFileTypes: true})) {
    if (entry.name === ".bin" || !(entry.isDirectory() || entry.isSymbolicLink())) continue;
    const child = join(real, entry.name);
    if (statSync(child).isDirectory()) collect(child);
  }
}

export function generateNotices({additionalInstalled = [], outputPath = join(root, "THIRD_PARTY_NOTICES.md")} = {}) {
  seen.clear();
  packages.clear();
  installedRoots = [installed, ...additionalInstalled].map(directory => realpathSync(directory));
  for (const directory of installedRoots) collect(directory);
  if (!packages.size) throw new Error("Install browser dependencies before generating notices");
  const text = ("# Third-party notices\n\nGenerated from the installed browser dependency tree.\n\n"
    + [...packages].sort(([a], [b]) => a.localeCompare(b)).map(([id, pkg]) =>
      `## ${id}\n\nLicense: ${typeof pkg.license === "string" ? pkg.license : JSON.stringify(pkg.license)}\n\n`
      + pkg.texts.join("\n\n") + "\n"
    ).join("\n")).replace(/\r\n/g, "\n").replace(/[ \t]+$/gm, "").trimEnd() + "\n";
  writeFileSync(outputPath, text);
}

export function copyLicenses(targetDirs) {
  if (!existsSync(join(root, "THIRD_PARTY_NOTICES.md"))) generateNotices();
  for (const target of targetDirs) {
    mkdirSync(target, {recursive: true});
    for (const name of ["LICENSE", "THIRD_PARTY_NOTICES.md"]) {
      const text = readFileSync(join(root, name), "utf8");
      if (!text.trim()) throw new Error(`Empty ${name}`);
      const source = Buffer.from(text.trimEnd() + "\n");
      const destination = join(target, name);
      writeFileSync(destination, source);
      if (!readFileSync(destination).equals(source)) throw new Error(`License copy failed: ${name}`);
    }
  }
}

if (process.argv[1] && realpathSync(process.argv[1]) === fileURLToPath(import.meta.url)) {
  generateNotices();
  copyLicenses([
    join(root, "packages/proxy-server"), join(root, "packages/proxy-server/public"),
    join(root, "packages/chrome-extension"),
  ]);
}