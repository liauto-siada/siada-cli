// Minimal ACP agent used by agent-connection tests: answers the initialize
// handshake over newline-delimited JSON-RPC on stdio and stays alive until
// killed. Emulates just enough of the protocol for the connect path.
import * as readline from "node:readline";

const rl = readline.createInterface({ input: process.stdin });

rl.on("line", (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    return;
  }
  if (message.method === "initialize") {
    process.stdout.write(
      JSON.stringify({
        jsonrpc: "2.0",
        id: message.id,
        result: {
          protocolVersion: message.params?.protocolVersion ?? "1",
          agentCapabilities: {},
          agentInfo: { name: "fake-agent", version: "1.0.0" },
        },
      }) + "\n",
    );
  }
});
