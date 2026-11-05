// Build the real input harness with the same optional-devtools exclusion as
// the production bundle. Run from siada_cli_ui.
import esbuild from 'esbuild';

await esbuild.build({
  entryPoints: ['tests/native-clipboard-tui.tsx'],
  bundle: true, platform: 'node', format: 'esm',
  outfile: 'bundle/native-harness.js',
  define: { 'process.env.DEV': '"false"' },
  banner: {
    js: "import {createRequire} from 'node:module'; const require=createRequire(import.meta.url); globalThis.__filename=require('node:url').fileURLToPath(import.meta.url); globalThis.__dirname=require('node:path').dirname(globalThis.__filename);",
  },
  plugins: [{
    name: 'production-devtools-exclusion',
    setup(build) {
      build.onResolve({ filter: /[/\\]devtools\.js$/ }, () => ({
        path: 'devtools-stub', namespace: 'devtools-stub',
      }));
      build.onLoad({ filter: /.*/, namespace: 'devtools-stub' }, () => ({
        contents: 'export default {}', loader: 'js',
      }));
    },
  }],
});