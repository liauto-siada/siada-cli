/**
 * @license
 * Copyright 2026 Siada Team
 * SPDX-License-Identifier: Apache-2.0
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { copyFileSync, readFileSync } from 'node:fs';

let esbuild;
try {
  esbuild = (await import('esbuild')).default;
} catch (_error) {
  console.error('esbuild is required to build the UI bundle; run npm ci first.');
  process.exit(1);
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const project = readFileSync(path.resolve(__dirname, '../pyproject.toml'), 'utf8');
const releaseVersion = project.match(/^version\s*=\s*"([^"]+)"/m)?.[1];
if (!releaseVersion) {
  throw new Error('No release version found in pyproject.toml');
}

// Base configuration.
const baseConfig = {
  bundle: true,
  platform: 'node',
  format: 'esm',
  external: [
    // Native dependencies cannot be bundled.
    'fsevents',
  ],
  loader: { '.node': 'file' },
  write: true,
  minify: true,
  sourcemap: false,
  // Preserve significant spaces inside strings as escapes in generated code.
  supported: { 'template-literal': false },
};

// CLI entry point.
const cliConfig = {
  ...baseConfig,
  banner: {
    js: `import { createRequire } from 'module';
const require = createRequire(import.meta.url);
globalThis.__filename = require('url').fileURLToPath(import.meta.url);
globalThis.__dirname = require('path').dirname(globalThis.__filename);`,
  },
  entryPoints: ['src/cli.ts'],
  outfile: 'bundle/siada-ui.js',
  define: {
    'process.env.CLI_VERSION': JSON.stringify(releaseVersion),
    'process.env.DEV': JSON.stringify('false'),  // Disable Ink devtools in production
  },
  metafile: true,
  plugins: [{
    name: 'ignore-optional-deps',
    setup(build) {
      // Ignore react-devtools-core (optional Ink dev dependency)
      // Reference: https://github.com/tapjs/tapjs/issues/1010
      build.onResolve({ filter: /^react-devtools-core$/ }, () => ({
        path: 'react-devtools-core',
        external: true,
        sideEffects: false
      }))
      
      // Also ignore the devtools.js file that imports it
      build.onResolve({ filter: /\/devtools\.js$/ }, () => ({
        path: 'devtools-stub',
        namespace: 'devtools-stub',
        sideEffects: false
      }))
      
      // Provide empty module for devtools-stub
      build.onLoad({ filter: /.*/, namespace: 'devtools-stub' }, () => ({
        contents: 'export default {}',
        loader: 'js'
      }))
    }
  }],
};

// Build the release bundle.
async function build() {
  try {
    console.log('Building siada-cli-ui with esbuild...');
    const result = await esbuild.build(cliConfig);
    copyFileSync(
      path.resolve(__dirname, 'THIRD_PARTY_NOTICES.md'),
      path.resolve(__dirname, 'bundle/siada-ui.LEGAL.txt'),
    );
    
    if (result.metafile && process.env.DEV === 'true') {
      const { writeFileSync } = await import('node:fs');
      writeFileSync('./bundle/esbuild-meta.json', JSON.stringify(result.metafile, null, 2));
      console.log('✓ Metafile written to bundle/esbuild-meta.json');
    }
    
    console.log('✓ Build completed successfully!');
  } catch (error) {
    console.error('Build failed:', error);
    process.exit(1);
  }
}

build();
