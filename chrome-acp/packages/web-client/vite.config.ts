import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "path";

const __dirname = new URL(".", import.meta.url).pathname;

const buildInputAudit: Plugin = {
  name: "chrome-acp-build-inputs",
  generateBundle(_options, bundle) {
    const chunks = Object.fromEntries(
      Object.entries(bundle)
        .filter(([, output]) => output.type === "chunk")
        .map(([name, output]) => [name, Object.keys(output.modules)]),
    );
    const auditDir = resolve(__dirname, "../../.build-audit");
    mkdirSync(auditDir, { recursive: true });
    writeFileSync(resolve(auditDir, "web-inputs.json"), JSON.stringify(chunks, null, 2));
  },
};

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    ...(process.env.CHROME_ACP_BUILD_AUDIT === "1" ? [buildInputAudit] : []),
  ],
  root: "src",
  base: "/app/", // Serve from /app/ path on the proxy server
  publicDir: false, // We'll handle public assets manually
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  build: {
    outDir: resolve(__dirname, "../proxy-server/public"),
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      input: {
        main: resolve(__dirname, "src/index.html"),
      },
      output: {
        // Enable code splitting with proper chunking (Rolldown advancedChunks)
        advancedChunks: {
          groups: [
            { name: "react", test: /[\\/]react(?:-dom)?[\\/]/ },
            { name: "radix", test: /@radix-ui[\\/]/ },
            { name: "shiki", test: /[\\/]shiki[\\/]/ },
          ],
        },
        assetFileNames: "assets/[name]-[hash][extname]",
        chunkFileNames: "assets/[name]-[hash].js",
        entryFileNames: "assets/[name]-[hash].js",
      },
    },
  },
});

