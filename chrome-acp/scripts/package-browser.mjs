/** Build a platform distribution and merge manifests for GitHub Releases. */
import {createHash} from "node:crypto";
import {spawnSync} from "node:child_process";
import {existsSync, readFileSync, writeFileSync, mkdirSync, rmSync, cpSync, mkdtempSync} from "node:fs";
import {tmpdir} from "node:os";
import {join, resolve, dirname} from "node:path";
import {fileURLToPath} from "node:url";

export const NODE_VERSION = "24.13.0";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(root, "..");
const platforms = {
  "darwin-arm64": "macos-arm64", "darwin-x64": "macos-x64",
  "linux-x64": "linux-x64", "linux-arm64": "linux-arm64",
  "win32-x64": "windows-x64",
};

function run(command, args, cwd = root) {
  const result = spawnSync(command, args, {cwd, stdio: "inherit"});
  if (result.error) throw result.error;
  if (result.status !== 0) throw new Error(`${command} exited ${result.status}`);
}

function python(args) {
  run(process.env.PYTHON || (process.platform === "win32" ? "python" : "python3"), args);
}

export function cliVersion() {
  const match = readFileSync(join(repo, "pyproject.toml"), "utf8").match(/^version = "([^"]+)"$/m);
  if (!match || !/^\d+\.\d+\.\d+$/.test(match[1])) throw new Error("Invalid CLI release version");
  return match[1];
}

async function download(url) {
  const response = await fetch(url, {signal: AbortSignal.timeout(300000)});
  if (!response.ok) throw new Error(`Download failed: ${url} (${response.status})`);
  return Buffer.from(await response.arrayBuffer());
}

const zipScript = `
import os, pathlib, sys, zipfile
source, output = map(pathlib.Path, sys.argv[1:])
staging = source.resolve().parent
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            if not path.resolve().is_relative_to(staging):
                raise RuntimeError("Archive symlink escapes staging directory: " + str(path.relative_to(source)) + " -> " + os.readlink(path))
            if path.is_dir():
                raise RuntimeError("Directory symlink unsupported")
        if path.is_file():
            archive.write(path, path.relative_to(source))
`;

export async function pack(output = join(root, "release")) {
  const platform = platforms[`${process.platform}-${process.arch}`];
  if (!platform) throw new Error("Unsupported build platform");
  const version = cliVersion();
  const stage = mkdtempSync(join(tmpdir(), "siada-browser-pack-"));
  output = resolve(output);
  mkdirSync(output, {recursive: true});
  try {
    const nodeOS = process.platform === "win32" ? "win" : process.platform;
    const archiveName = `node-v${NODE_VERSION}-${nodeOS}-${process.arch}.${process.platform === "win32" ? "zip" : "tar.gz"}`;
    const base = `https://nodejs.org/dist/v${NODE_VERSION}`;
    const sums = (await download(`${base}/SHASUMS256.txt`)).toString();
    const expected = sums.split("\n").map(line => line.trim().split(/\s+/))
      .find(([, name]) => name === archiveName)?.[0];
    if (!expected) throw new Error("Node archive is missing from official checksums");
    const data = await download(`${base}/${archiveName}`);
    if (createHash("sha256").update(data).digest("hex") !== expected) throw new Error("Node checksum mismatch");
    const archive = join(stage, archiveName);
    writeFileSync(archive, data);
    const unpack = join(stage, "unpack");
    mkdirSync(unpack);
    if (process.platform === "win32") {
      python(["-c", "import zipfile,sys; zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])", archive, unpack]);
    } else {
      run("tar", ["-xzf", archive, "-C", unpack]);
    }
    const bundle = join(stage, "bundle");
    mkdirSync(bundle);
    cpSync(join(unpack, archiveName.replace(/\.(zip|tar\.gz)$/, "")), join(bundle, "runtime"), {recursive: true, dereference: true});
    const proxy = join(bundle, "proxy");
    mkdirSync(proxy);
    for (const name of ["dist", "public", "package.json", "package-lock.json", "LICENSE", "THIRD_PARTY_NOTICES.md"]) {
      cpSync(join(root, "packages/proxy-server", name), join(proxy, name), {recursive: true});
    }
    const extension = join(bundle, "extension");
    mkdirSync(extension);
    for (const name of ["manifest.json", "icons", "rules", "dist", "LICENSE", "THIRD_PARTY_NOTICES.md"]) {
      cpSync(join(root, "packages/chrome-extension", name), join(extension, name), {recursive: true});
    }
    for (const component of [proxy, extension]) {
      for (const name of ["LICENSE", "THIRD_PARTY_NOTICES.md"]) {
        if (!readFileSync(join(root, name)).equals(readFileSync(join(component, name)))) {
          throw new Error(`Stale ${name}; rebuild browser components`);
        }
      }
    }
    const runtime = join(bundle, "runtime");
    const node = join(runtime, process.platform === "win32" ? "node.exe" : "bin/node");
    const npm = join(runtime, process.platform === "win32" ? "node_modules/npm/bin/npm-cli.js" : "lib/node_modules/npm/bin/npm-cli.js");
    run(node, [npm, "ci", "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund"], proxy);
    run(node, [join(proxy, "dist/cli/bin.js"), "--help"], proxy);
    const filename = `siada-browser-${version}-${platform}.zip`;
    const temporaryZip = join(stage, filename);
    python(["-c", zipScript, bundle, temporaryZip]);
    cpSync(temporaryZip, join(output, filename));
    const sha256 = createHash("sha256").update(readFileSync(join(output, filename))).digest("hex");
    const manifest = {schema_version: 1, version, node_version: NODE_VERSION, platforms: {[platform]: {filename, sha256}}};
    writeFileSync(join(output, `browser-manifest-${platform}.json`), JSON.stringify(manifest, null, 2) + "\n");
    writeFileSync(join(output, "browser-manifest.json"), JSON.stringify(manifest, null, 2) + "\n");
    console.log(`Packed ${filename} (${sha256})`);
    return manifest;
  } finally {
    rmSync(stage, {recursive: true, force: true});
  }
}

export function mergeManifest(inputs, output) {
  const result = {schema_version: 1, version: cliVersion(), node_version: NODE_VERSION, platforms: {}};
  for (const filename of inputs) {
    const part = JSON.parse(readFileSync(filename, "utf8"));
    if (part.schema_version !== 1 || part.version !== result.version || part.node_version !== NODE_VERSION) {
      throw new Error("Manifest versions do not match");
    }
    for (const [platform, entry] of Object.entries(part.platforms)) {
      if (!Object.values(platforms).includes(platform) || result.platforms[platform] ||
          entry.filename !== `siada-browser-${result.version}-${platform}.zip` ||
          !/^[a-f0-9]{64}$/.test(entry.sha256)) throw new Error("Invalid or duplicate platform");
      const artifact = join(dirname(filename), entry.filename);
      if (!existsSync(artifact) || createHash("sha256").update(readFileSync(artifact)).digest("hex") !== entry.sha256) {
        throw new Error("Artifact checksum mismatch");
      }
      result.platforms[platform] = entry;
    }
  }
  if (!Object.keys(result.platforms).length) throw new Error("No platform manifests provided");
  writeFileSync(output, JSON.stringify(result, null, 2) + "\n");
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [command, ...args] = process.argv.slice(2);
  if (command === "pack") await pack(args[0]);
  else if (command === "manifest" && args.length >= 2) mergeManifest(args.slice(1), args[0]);
  else throw new Error("Usage: package-browser.mjs pack [output] | manifest output input...");
}