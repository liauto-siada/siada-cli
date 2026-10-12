#!/usr/bin/env node
/**
 * Copy the canonical license artifacts into build output directories.
 *
 * `chrome-acp/LICENSE` (project MIT license) and
 * `chrome-acp/THIRD_PARTY_NOTICES.md` (complete third-party notices) are the
 * single source of truth. Every redistribution path must ship both next to the
 * built output:
 *
 *   - packages/proxy-server/{LICENSE,THIRD_PARTY_NOTICES.md}
 *       required by siada.browser_addon.installer._PROXY_ITEMS; also listed in
 *       the package's `files`, so `prepublishOnly` -> `build` must create them
 *       before `npm pack`/`npm publish`;
 *   - packages/chrome-extension/{LICENSE,THIRD_PARTY_NOTICES.md}
 *       required by installer._EXT_ITEMS and added to the zip by
 *       `just pack-extension`;
 *   - packages/proxy-server/public/{LICENSE,THIRD_PARTY_NOTICES.md}
 *       served by the proxy PWA (`/app/LICENSE`, `/app/THIRD_PARTY_NOTICES.md`).
 *
 * Every copy is verified by re-reading the destination, and a missing/empty
 * source or a mismatching destination is a hard error, so a build can never
 * "succeed" while silently dropping the license files.
 *
 * Usage:
 *   node scripts/copy-licenses.mjs <target-dir> [<target-dir> ...]
 *
 * Importable (build.ts / copy-pwa-assets.ts):
 *   import { copyLicenses } from "../../scripts/copy-licenses.mjs";
 *   await copyLicenses([import.meta.dir]);
 *
 * No dependencies beyond node: builtins; runs under both node and bun.
 */
import { copyFileSync, mkdirSync, readFileSync, realpathSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

export const CHROME_ACP_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const LICENSE_FILES = Object.freeze(["LICENSE", "THIRD_PARTY_NOTICES.md"]);

function readSource(name) {
  const src = join(CHROME_ACP_ROOT, name);
  let stat;
  try {
    stat = statSync(src);
  } catch {
    throw new Error(`missing source file ${src} — cannot build a redistributable artifact`);
  }
  if (!stat.isFile() || stat.size === 0) {
    throw new Error(`source ${src} is not a non-empty file — refusing to ship an empty license artifact`);
  }
  return { name, src, bytes: readFileSync(src) };
}

/**
 * Copy LICENSE + THIRD_PARTY_NOTICES.md into each target directory.
 * Throws (fails the build) on any missing source or failed/incorrect copy.
 *
 * @param {string[]} targetDirs
 * @returns {string[]} absolute paths of the written files
 */
export function copyLicenses(targetDirs) {
  if (!Array.isArray(targetDirs) || targetDirs.length === 0) {
    throw new Error("copyLicenses: at least one target directory is required");
  }
  const sources = LICENSE_FILES.map(readSource);
  const written = [];
  for (const dir of targetDirs) {
    const target = resolve(dir);
    mkdirSync(target, { recursive: true });
    for (const { name, bytes, src } of sources) {
      const dest = join(target, name);
      copyFileSync(src, dest);
      const copied = readFileSync(dest);
      if (!copied.equals(bytes)) {
        throw new Error(`copy verification failed: ${dest} does not match ${src}`);
      }
      const shown = dest.startsWith(CHROME_ACP_ROOT) ? relative(CHROME_ACP_ROOT, dest) : dest;
      console.log(`✓ ${name} (${bytes.length} bytes) -> ${shown}`);
      written.push(dest);
    }
  }
  return written;
}

function main(argv) {
  const targets = argv.filter((arg) => !arg.startsWith("-"));
  if (targets.length === 0) {
    console.error("usage: node scripts/copy-licenses.mjs <target-dir> [<target-dir> ...]");
    return 2;
  }
  copyLicenses(targets);
  return 0;
}

// Run as CLI only when executed directly (not when imported by build scripts).
// Compare realpaths: node canonicalizes module paths (e.g. /tmp -> /private/tmp
// on macOS), so a raw pathToFileURL(argv[1]) comparison can silently no-op.
const invokedDirectly = (() => {
  const entry = process.argv[1];
  if (entry === undefined) return false;
  try {
    return realpathSync(entry) === fileURLToPath(import.meta.url);
  } catch {
    return false;
  }
})();

if (invokedDirectly) {
  try {
    process.exitCode = main(process.argv.slice(2));
  } catch (err) {
    console.error(`✗ license copy failed: ${err instanceof Error ? err.message : String(err)}`);
    process.exitCode = 1;
  }
}