import { startServer } from "../../dist/server.js";
import { fileURLToPath } from "node:url";

await startServer({
  host: "127.0.0.1", port: Number(process.env.SIADA_UI_TEST_PORT || 9334),
  command: process.execPath, args: [fileURLToPath(new URL("./interactive-ui-agent.mjs", import.meta.url))],
  cwd: fileURLToPath(new URL(".", import.meta.url)),
  token: "interactive-ui-e2e-token",
});