#!/usr/bin/env bun
import plugin from "bun-plugin-tailwind";
import { existsSync } from "fs";
import { cp, readFile, rm, writeFile } from "fs/promises";
import path from "path";
import { vendorPdfViewer, VENDOR_DIR } from "./scripts/vendor-pdf-viewer";

if (process.argv.includes("--help") || process.argv.includes("-h")) {
  console.log(`
🏗️  Bun Build Script

Usage: bun run build.ts [options]

Common Options:
  --outdir <path>          Output directory (default: "dist")
  --minify                 Enable minification (or --minify.whitespace, --minify.syntax, etc)
  --sourcemap <type>      Sourcemap type: none|linked|inline|external
  --target <target>        Build target: browser|bun|node
  --format <format>        Output format: esm|cjs|iife
  --splitting              Enable code splitting
  --packages <type>        Package handling: bundle|external
  --public-path <path>     Public path for assets
  --env <mode>             Environment handling: inline|disable|prefix*
  --conditions <list>      Package.json export conditions (comma separated)
  --external <list>        External packages (comma separated)
  --banner <text>          Add banner text to output
  --footer <text>          Add footer text to output
  --define <obj>           Define global constants (e.g. --define.VERSION=1.0.0)
  --help, -h               Show this help message

Example:
  bun run build.ts --outdir=dist --minify --sourcemap=linked --external=react,react-dom
`);
  process.exit(0);
}

const toCamelCase = (str: string): string => str.replace(/-([a-z])/g, (_, c: string) => c.toUpperCase());

const parseValue = (value: string): any => {
  if (value === "true") return true;
  if (value === "false") return false;

  if (/^\d+$/.test(value)) return parseInt(value, 10);
  if (/^\d*\.\d+$/.test(value)) return parseFloat(value);

  if (value.includes(",")) return value.split(",").map(v => v.trim());

  return value;
};

function parseArgs(): Record<string, unknown> {
  const config: Record<string, unknown> = {};
  const args = process.argv.slice(2);

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === undefined) continue;
    if (!arg.startsWith("--")) continue;

    if (arg.startsWith("--no-")) {
      const key = toCamelCase(arg.slice(5));
      config[key] = false;
      continue;
    }

    if (!arg.includes("=") && (i === args.length - 1 || args[i + 1]?.startsWith("--"))) {
      const key = toCamelCase(arg.slice(2));
      config[key] = true;
      continue;
    }

    let key: string;
    let value: string;

    if (arg.includes("=")) {
      [key, value] = arg.slice(2).split("=", 2) as [string, string];
    } else {
      key = arg.slice(2);
      value = args[++i] ?? "";
    }

    key = toCamelCase(key);

    if (key.includes(".")) {
      const parts = key.split(".");
      const parentKey = parts[0];
      const childKey = parts[1];
      if (parentKey && childKey) {
        config[parentKey] = config[parentKey] || {};
        (config[parentKey] as Record<string, unknown>)[childKey] = parseValue(value);
      }
    } else {
      config[key] = parseValue(value);
    }
  }

  return config;
}

const formatFileSize = (bytes: number): string => {
  const units = ["B", "KB", "MB", "GB"];
  let size = bytes;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex++;
  }

  return `${size.toFixed(2)} ${units[unitIndex]}`;
};

console.log("\n🚀 Starting build process...\n");

const cliConfig = parseArgs();
const outdir = (typeof cliConfig.outdir === "string" ? cliConfig.outdir : null) || path.join(process.cwd(), "dist");

if (existsSync(outdir)) {
  console.log(`🗑️ Cleaning previous build at ${outdir}`);
  await rm(outdir, { recursive: true, force: true });
}

const start = performance.now();

const entrypoints = [...new Bun.Glob("**.html").scanSync("src")]
  .map(a => path.resolve("src", a))
  .filter(dir => !dir.includes("node_modules"));
console.log(`📄 Found ${entrypoints.length} HTML ${entrypoints.length === 1 ? "file" : "files"} to process\n`);

const result = await Bun.build({
  entrypoints,
  outdir,
  plugins: [plugin],
  minify: true,
  target: "browser",
  sourcemap: "linked",
  naming: {
    chunk: "[name]-[hash].[ext]",
    asset: "[name]-[hash].[ext]",
  },
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  ...cliConfig,
});

const end = performance.now();

// Build background service worker, content scripts and replay injector separately
// NOTE: format "iife" is REQUIRED for content scripts — they all run in the
// same isolated world, and with the default (top-level) output their minified
// var/function names collide across bundles (e.g. the explain bundle's
// `var m = "explain_enabled"` overwrote the recorder's event queue, silently
// killing all post-boot recording in top frames).
const bgResult = await Bun.build({
  entrypoints: [
    path.resolve("src", "background.ts"),
    path.resolve("src", "recorder", "content-script.ts"),
    path.resolve("src", "explain", "content-script.ts"),
    path.resolve("src", "replay", "inject.ts"),
  ],
  outdir,
  minify: true,
  target: "browser",
  format: "iife",
  sourcemap: "linked",
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
});

// Vendored pdf.js viewer (see scripts/vendor-pdf-viewer.ts): copied as-is to
// dist/pdf/ — these assets are pre-built and must NOT go through the bundler.
// Our acp-bridge.js is added next to them and injected into viewer.html as a
// CLASSIC script right before the deferred viewer.mjs module, so its DNR URL
// rewrite runs before the viewer app initializes.
await vendorPdfViewer();
const pdfOutDir = path.join(outdir, "pdf");
await cp(VENDOR_DIR, pdfOutDir, { recursive: true });
await cp(
  path.resolve("src", "pdf", "acp-bridge.js"),
  path.join(pdfOutDir, "web", "acp-bridge.js"),
);
const viewerHtmlPath = path.join(pdfOutDir, "web", "viewer.html");
let viewerHtml = await readFile(viewerHtmlPath, "utf8");
// The stock meta CSP is `connect-src * blob: data:` — but CSP `*` only covers
// network schemes (http/https/ws/wss), never file:. The viewer must fetch
// file:// PDFs (DNR redirects local PDF navigations here), so add it
// explicitly. The manifest extension_pages CSP applies on top of this meta.
const metaConnectSrc = "connect-src * blob: data:";
if (!viewerHtml.includes("connect-src * file: blob: data:")) {
  if (!viewerHtml.includes(metaConnectSrc)) {
    throw new Error("vendored viewer.html meta CSP changed — adjust the file: connect-src patch");
  }
  viewerHtml = viewerHtml.replace(metaConnectSrc, "connect-src * file: blob: data:");
  await writeFile(viewerHtmlPath, viewerHtml);
}
if (!viewerHtml.includes("acp-bridge.js")) {
  const bridgeTag = '<script src="./acp-bridge.js"></script>';
  const viewerModuleTag = '<script src="viewer.mjs" type="module">';
  if (!viewerHtml.includes(viewerModuleTag)) {
    throw new Error("vendored viewer.html has no viewer.mjs tag — bridge injection failed");
  }
  await writeFile(
    viewerHtmlPath,
    viewerHtml.replace(viewerModuleTag, `${bridgeTag}\n  ${viewerModuleTag}`),
  );
}
console.log("📄 pdf.js viewer copied to dist/pdf/ (with acp-bridge)\n");

const allOutputs = [...result.outputs, ...bgResult.outputs];
const outputTable = allOutputs.map(output => {
  return {
    File: path.relative(process.cwd(), output.path),
    Type: output.kind,
    Size: formatFileSize(output.size),
  };
});

console.table(outputTable);
const buildTime = (end - start).toFixed(2);

console.log(`\n✅ Build completed in ${buildTime}ms\n`);
