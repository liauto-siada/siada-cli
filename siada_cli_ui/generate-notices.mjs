/** Generate notices for the packages whose files enter the esbuild bundle. */
import {existsSync, readFileSync, readdirSync, statSync, writeFileSync} from "node:fs";
import {dirname, join, resolve} from "node:path";

export function generateBundleNotices(metafile, root) {
  const packages = new Map();
  for (const input of Object.keys(metafile.inputs)) {
    if (!input.includes("node_modules/")) continue;
    let directory = dirname(resolve(root, input));
    while (directory !== dirname(directory)) {
      const file = join(directory, "package.json");
      if (existsSync(file)) {
        const pkg = JSON.parse(readFileSync(file, "utf8"));
        if (pkg.name && pkg.version) {
          packages.set(`${pkg.name}@${pkg.version}`, {directory, pkg});
          break;
        }
      }
      directory = dirname(directory);
    }
  }
  if (!packages.size) throw new Error("No bundle input packages found");
  const sections = [];
  for (const [id, {directory, pkg}] of [...packages].sort(([a], [b]) => a.localeCompare(b))) {
    const names = readdirSync(directory)
      .filter(name => /^(licen[cs]e|copying|notice)(\.|$|-)/i.test(name))
      .filter(name => statSync(join(directory, name)).isFile());
    if (!names.length) {
      const readme = readdirSync(directory).find(name => /^readme(\.|$)/i.test(name));
      if (readme) names.push(readme);
    }
    if (!names.length) throw new Error(`No redistribution notice found for ${id}`);
    sections.push(`## ${id}\n\nLicense: ${typeof pkg.license === "string" ? pkg.license : JSON.stringify(pkg.license)}\n\n`
      + names.map(name => readFileSync(join(directory, name), "utf8")).join("\n\n"));
  }
  const content = ("# Terminal UI third-party notices\n\nGenerated from the esbuild input package closure.\n\n"
    + sections.join("\n\n")).replace(/\r\n/g, "\n").replace(/[ \t]+$/gm, "").trimEnd() + "\n";
  writeFileSync(join(root, "THIRD_PARTY_NOTICES.md"), content);
  writeFileSync(join(root, "bundle/siada-ui.LEGAL.txt"), content);
}