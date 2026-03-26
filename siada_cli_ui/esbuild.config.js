/**
 * @license
 * Copyright 2026 Siada Team
 * SPDX-License-Identifier: Apache-2.0
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

let esbuild;
try {
  esbuild = (await import('esbuild')).default;
} catch (_error) {
  console.warn('esbuild not available, skipping bundle step');
  process.exit(0);
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const require = createRequire(import.meta.url);
const pkg = require(path.resolve(__dirname, 'package.json'));

// 基础配置
const baseConfig = {
  bundle: true,
  platform: 'node',
  format: 'esm',
  external: [
    // 只保留原生模块为 external（无法打包）
    'fsevents',
  ],
  loader: { '.node': 'file' },
  write: true,
  minify: false, // 保持可读性，便于调试
  sourcemap: true,
};

// CLI 入口配置
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
    'process.env.CLI_VERSION': JSON.stringify(pkg.version),
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

// 构建
async function build() {
  try {
    console.log('Building siada-cli-ui with esbuild...');
    const result = await esbuild.build(cliConfig);
    
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
