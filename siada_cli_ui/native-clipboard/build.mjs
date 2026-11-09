import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { x } from 'tar';

/** All prebuilt targets are included so a wheel built on macOS also runs on Linux. */
export async function buildNativeClipboard(uiDirectory) {
  const destination = path.join(uiDirectory, 'bundle/native-clipboard');
  await mkdir(destination, { recursive: true });
  for (const file of ['helper.cjs', 'png.cjs', 'NOTICE']) {
    await cp(path.join(uiDirectory, 'native-clipboard', file), path.join(destination, file));
  }
  await buildBinding(uiDirectory, '@napi-rs/clipboard', 'runtime');
  await buildBinding(uiDirectory, '@mariozechner/clipboard', 'image-runtime');
}

async function buildBinding(uiDirectory, packageName, runtimeDirectory) {
  const require = createRequire(path.join(uiDirectory, 'package.json'));
  const packageFile = require.resolve(`${packageName}/package.json`);
  const packageDirectory = path.dirname(packageFile);
  const metadata = JSON.parse(await readFile(packageFile, 'utf8'));
  const lock = JSON.parse(await readFile(path.join(uiDirectory, 'package-lock.json'), 'utf8'));
  const destination = path.join(uiDirectory, 'bundle/native-clipboard');
  const runtime = path.join(destination, runtimeDirectory);
  const cache = path.join(uiDirectory, 'node_modules/.cache/native-clipboard');
  // Do not let a target absent from a new version load a previous binary.
  await rm(runtime, { recursive: true, force: true });
  await mkdir(runtime, { recursive: true });
  await mkdir(cache, { recursive: true });
  await cp(path.join(packageDirectory, 'index.js'), path.join(runtime, 'index.js'));
  await cp(packageFile, path.join(runtime, 'package.json'));
  for (const [name, version] of Object.entries(metadata.optionalDependencies)) {
    const locked = lock.packages[`node_modules/${name}`];
    if (locked?.version !== version || !locked.integrity?.startsWith('sha512-')) {
      throw new Error(`Missing locked native clipboard artifact: ${name}`);
    }
    if (!name.startsWith(`${packageName}-`)) throw new Error('Unexpected native clipboard target');
    const binary = `clipboard.${name.slice(packageName.length + 1)}.node`;
    const cacheName = name.replace('@napi-rs/', '').replace('@mariozechner/', 'image-');
    const archive = path.join(cache, `${cacheName}-${version}.tgz`);
    let bytes;
    try { bytes = await readFile(archive); } catch {
      const response = await fetch(locked.resolved, { signal: AbortSignal.timeout(60000) });
      if (!response.ok) throw new Error(`Native clipboard download failed: ${name}`);
      bytes = Buffer.from(await response.arrayBuffer());
    }
    const integrity = `sha512-${createHash('sha512').update(bytes).digest('base64')}`;
    if (integrity !== locked.integrity) {
      await rm(archive, { force: true });
      throw new Error(`Native clipboard integrity mismatch: ${name}`);
    }
    await writeFile(archive, bytes);
    const temporary = await mkdtemp(path.join(tmpdir(), 'siada-clipboard-build-'));
    try {
      await x({ file: archive, cwd: temporary, filter: entry => entry === `package/${binary}` });
      await cp(path.join(temporary, 'package', binary), path.join(runtime, binary));
    } finally {
      await rm(temporary, { recursive: true, force: true });
    }
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await buildNativeClipboard(path.resolve(fileURLToPath(new URL('..', import.meta.url))));
}