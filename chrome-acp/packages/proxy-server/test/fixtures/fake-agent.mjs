// Minimal ACP agent used by agent-connection tests: answers the initialize
// handshake over newline-delimited JSON-RPC on stdio and stays alive until
// killed. Emulates just enough of the protocol for the connect path.
import * as readline from "node:readline";
const rl = readline.createInterface({ input: process.stdin });

const GENERIC_DETAILS = "BadGatewayError: Error code: 502 LiteLLM Retried: 3 times";
const steeringEnabled = process.argv.includes("--steering");
let heldPrompt = null;

function reply(id, payload) {
  process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, ...payload }) + "\n");
}

rl.on("line", (line) => {
  let message;
  try {
    message = JSON.parse(line);
  } catch {
    return;
  }
  if (message.method === "initialize") {
    reply(message.id, {
      result: {
        protocolVersion: message.params?.protocolVersion ?? "1",
        agentCapabilities: steeringEnabled ? { _meta: { siada: { steering: true } } } : {},
        agentInfo: { name: "fake-agent", version: "1.0.0" },
      },
    });
    return;
  }
  if (message.method === "session/new") {
    reply(message.id, { result: { sessionId: "fake-session" } });
    return;
  }
  if (message.method === "_trajectory_event") {
    // Echo trajectory notifications back as an agent session update. Real
    // agents queue these for skill matching; here the echo gives tests a
    // visible signal that the proxy actually delivered the batch to the agent.
    process.stdout.write(
      JSON.stringify({
        jsonrpc: "2.0",
        method: "session/update",
        params: {
          sessionId: "fake-session",
          update: {
            sessionUpdate: "agent_message_chunk",
            content: { type: "text", text: JSON.stringify(message.params) },
          },
        },
      }) + "\n",
    );
    return;
  }
  if (message.method === "session/prompt") {
    // Error scenarios containing "generic-shape" answer the way
    // the SDK reports a bare exception (-32603 with the cause buried in
    // `data.details`); anything else answers with the cause as the message.
    const text = (message.params?.prompt ?? [])
      .map((block) => block.text ?? "")
      .join("");
    if (steeringEnabled && text === "steering-hold") {
      heldPrompt = message.id;
      return;
    }
    if (text === "logging-stream") {
      for (let i = 0; i < 1000; i++) {
        process.stdout.write(JSON.stringify({
          jsonrpc: "2.0", method: "session/update",
          params: { sessionId: "fake-session", update: {
            sessionUpdate: "agent_message_chunk", content: { type: "text", text: "x" },
            _meta: { siadaLog: {
              requestId: message.params?._meta?.siadaLog?.requestId,
              agent: "synthetic-agent", agentRunId: "synthetic-run",
            } },
          } },
        }) + "\n");
      }
      reply(message.id, { result: { stopReason: "end_turn" } });
      return;
    }
    const error = text.includes("generic-shape")
      ? { code: -32603, message: "Internal error", data: { details: GENERIC_DETAILS } }
      : { code: -32603, message: GENERIC_DETAILS };
    reply(message.id, { error });
  }
  if (message.method === "_session/steer" && steeringEnabled) {
    if (heldPrompt === null || message.params?.prompt?.some(block => block.type !== "text")) {
      reply(message.id, { error: { code: -32000, message: "Steering rejected" } });
      return;
    }
    reply(message.id, { result: { accepted: true } });
    reply(heldPrompt, { result: { stopReason: "end_turn" } });
    heldPrompt = null;
  }
});
