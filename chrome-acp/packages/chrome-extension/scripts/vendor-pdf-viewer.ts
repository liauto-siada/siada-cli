#!/usr/bin/env bun
/**
 * Vendor the official Mozilla pdf.js "generic" viewer into `vendor/pdf/`.
 *
 * The npm `pdfjs-dist` package only ships the viewer *components* library,
 * not the full viewer app (viewer.html + toolbar/sidebar). The complete app
 * is published as `pdfjs-<version>-dist.zip` on the pdf.js GitHub releases
 * page (Apache-2.0, LICENSE included in the archive).
 *
 * Layout produced (consumed by build.ts, which copies it to `dist/pdf/`):
 *
 *   vendor/pdf/
 *     LICENSE
 *     .version               marker, enables skip-if-current
 *     build/pdf.mjs          sets globalThis.pdfjsLib (loaded by viewer.html)
 *     build/pdf.worker.mjs   default workerSrc of the viewer
 *     build/pdf.sandbox.mjs
 *     web/viewer.html        the full viewer app
 *     web/viewer.mjs         has no static imports; uses global pdfjsLib
 *     web/viewer.css
 *     web/{images,locale,cmaps,standard_fonts,iccs,wasm}/...
 *
 * Source maps and the bundled demo PDF are excluded to keep the extension
 * zip small.
 *
 * Usage: bun run scripts/vendor-pdf-viewer.ts [--force]
 */
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

export const PDFJS_VERSION = "6.3.289";
export const PDFJS_ZIP_URL = `https://github.com/mozilla/pdf.js/releases/download/v${PDFJS_VERSION}/pdfjs-${PDFJS_VERSION}-dist.zip`;
export const PDFJS_ZIP_SHA256 = "98c5832ffe7af4edd59853476a478c0d4d4d76dd49c1701f4c86f7182725cdf9";

export const VENDOR_DIR = path.resolve(import.meta.dir, "..", "vendor", "pdf");
const VERSION_MARKER = path.join(VENDOR_DIR, ".version");

async function readVersionMarker(): Promise<string | null> {
  try {
    return (await readFile(VERSION_MARKER, "utf8")).trim();
  } catch {
    return null;
  }
}

function run(cmd: string[], description: string): void {
  const result = Bun.spawnSync(cmd, { stdout: "pipe", stderr: "pipe" });
  if (result.exitCode !== 0) {
    throw new Error(
      `${description} failed (exit ${result.exitCode}): ${result.stderr.toString().slice(0, 500)}`,
    );
  }
}

export async function vendorPdfViewer(force = false): Promise<void> {
  if (!force && (await readVersionMarker()) === PDFJS_VERSION) {
    console.log(`📄 pdf.js viewer already vendored at ${PDFJS_VERSION}, skipping`);
    return;
  }

  console.log(`⬇️  Downloading pdf.js viewer ${PDFJS_VERSION}...`);
  const response = await fetch(PDFJS_ZIP_URL);
  if (!response.ok) {
    throw new Error(`Download failed: HTTP ${response.status} for ${PDFJS_ZIP_URL}`);
  }
  const zipBytes = new Uint8Array(await response.arrayBuffer());

  const actualHash = createHash("sha256").update(zipBytes).digest("hex");
  if (actualHash !== PDFJS_ZIP_SHA256) {
    throw new Error(
      `sha256 mismatch for ${PDFJS_ZIP_URL}: expected ${PDFJS_ZIP_SHA256}, got ${actualHash}`,
    );
  }

  const tmp = await mkdtemp(path.join(tmpdir(), "pdfjs-vendor-"));
  try {
    const zipPath = path.join(tmp, "dist.zip");
    await writeFile(zipPath, zipBytes);

    const extracted = path.join(tmp, "extracted");
    run(["unzip", "-q", zipPath, "-d", extracted], "unzip");

    // Rebuild the vendor dir from scratch for determinism.
    await rm(VENDOR_DIR, { recursive: true, force: true });
    run(["mkdir", "-p", path.join(VENDOR_DIR, "build")], "mkdir");

    // build/: runtime modules only (skip .map files).
    for (const file of ["pdf.mjs", "pdf.worker.mjs", "pdf.sandbox.mjs"]) {
      run(
        ["cp", path.join(extracted, "build", file), path.join(VENDOR_DIR, "build", file)],
        `copy build/${file}`,
      );
    }

    // web/: everything except source maps and the bundled demo PDF.
    run(["cp", "-R", path.join(extracted, "web"), path.join(VENDOR_DIR, "web")], "copy web/");
    run(
      ["find", path.join(VENDOR_DIR, "web"), "-name", "*.map", "-delete"],
      "strip web/*.map",
    );
    await rm(path.join(VENDOR_DIR, "web", "compressed.tracemonkey-pldi-09.pdf"), {
      force: true,
    });

    run(["cp", path.join(extracted, "LICENSE"), path.join(VENDOR_DIR, "LICENSE")], "copy LICENSE");

    // Patch: allow the viewer to open cross-origin files. The stock generic
    // viewer rejects `?file=` whose origin differs from the viewer origin —
    // correct for the mozilla.github.io web demo, but wrong for an extension
    // page (chrome-extension://…) whose host_permissions already authorize
    // cross-origin fetches. The reference "PDF Viewer" extension ships the
    // same relaxation. Exact-anchor replace; fail loudly if pdf.js changes
    // the anchor on upgrade.
    const viewerMjsPath = path.join(VENDOR_DIR, "web", "viewer.mjs");
    const viewerMjs = await readFile(viewerMjsPath, "utf8");
    const anchor =
      'const HOSTED_VIEWER_ORIGINS = new Set(["null", "http://mozilla.github.io", "https://mozilla.github.io"]);';
    if (!viewerMjs.includes(anchor)) {
      throw new Error(
        "pdf.js anchor not found in viewer.mjs (HOSTED_VIEWER_ORIGINS) — " +
          "the vendored version changed; adjust the patch in vendor-pdf-viewer.ts",
      );
    }
    const patched = viewerMjs.replace(
      anchor,
      // URL.parse(window.location) is what validateFileURL itself uses.
      'const HOSTED_VIEWER_ORIGINS = new Set(["null", "http://mozilla.github.io", "https://mozilla.github.io", URL.parse(window.location)?.origin || "null"]);',
    );
    await writeFile(viewerMjsPath, patched);

    await writeFile(VERSION_MARKER, `${PDFJS_VERSION}\n`);

    console.log(`✅ pdf.js viewer ${PDFJS_VERSION} vendored to ${path.relative(process.cwd(), VENDOR_DIR)}`);
  } finally {
    await rm(tmp, { recursive: true, force: true });
  }
}

if (import.meta.main) {
  await vendorPdfViewer(process.argv.includes("--force"));
}
