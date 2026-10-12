import { mkdir } from "fs/promises";
import { join } from "path";
import { copyLicenses } from "../../scripts/copy-licenses.mjs";

const outdir = join(import.meta.dir, "../proxy-server/public");

// Read version from proxy-server package.json for cache versioning
const proxyPkg = await Bun.file(join(import.meta.dir, "../proxy-server/package.json")).json();
const version = proxyPkg.version as string;

// Copy PWA assets (manifest.json, logo, icons)
const pwaAssets = ["manifest.json", "icon-192.png", "icon-512.png"];
for (const asset of pwaAssets) {
  const src = join(import.meta.dir, "src", asset);
  const dest = join(outdir, asset);
  try {
    await Bun.write(dest, Bun.file(src));
  } catch {
    // Asset may not exist yet
  }
}

// Process sw.js - inject version for cache busting
// This ensures SW updates when proxy-server version changes
const swSrc = join(import.meta.dir, "src", "sw.js");
const swDest = join(outdir, "sw.js");
try {
  let swContent = await Bun.file(swSrc).text();
  // Replace __VERSION__ placeholder with actual version
  swContent = swContent.replace(/__VERSION__/g, version);
  await Bun.write(swDest, swContent);
  console.log(`✓ Service Worker updated with version ${version}`);
} catch {
  // sw.js may not exist yet
}

// Copy icons folder
const iconsDir = join(import.meta.dir, "src/icons");
const iconsOutDir = join(outdir, "icons");
try {
  await mkdir(iconsOutDir, { recursive: true });
  const iconFiles = await Array.fromAsync(new Bun.Glob("*.png").scan(iconsDir));
  for (const icon of iconFiles) {
    await Bun.write(join(iconsOutDir, icon), Bun.file(join(iconsDir, icon)));
  }
} catch {
  // Icons may not exist yet
}

// Ship the canonical LICENSE + THIRD_PARTY_NOTICES.md with the PWA served by
// the proxy (installer._PROXY_ITEMS includes public/, and the notices document
// requires both files inside packages/proxy-server/public/). The helper
// verifies each copy and throws on any missing/empty source, so a failed copy
// fails `build:web` (never a license-less PWA/proxy tarball).
await copyLicenses([outdir]);

console.log("✓ PWA assets copied to", outdir);

