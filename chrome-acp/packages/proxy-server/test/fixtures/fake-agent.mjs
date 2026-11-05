// Minimal ACP agent used by agent-connection tests: answers the initialize
// handshake over newline-delimited JSON-RPC on stdio and stays alive until
// killed. Emulates just enough of the protocol for the connect path.
import * as readline from "node:readline";
import { appendFileSync } from "node:fs";

const rl = readline.createInterface({ input: process.stdin });

const GENERIC_DETAILS = "BadGatewayError: Error code: 502 LiteLLM Retried: 3 times";
const steeringEnabled = process.argv.includes("--steering");
const retentionEnabled = process.argv.includes("--retention");
const initializationDelay = process.argv.includes("--slow-init") ? 400 : 0;
if (retentionEnabled && process.env.SIADA_RETENTION_TEST_LAUNCH_LOG) {
  appendFileSync(process.env.SIADA_RETENTION_TEST_LAUNCH_LOG, `${process.pid}\n`);
}
let heldPrompt = null;
let ignoreCancellation = false;

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
  if (retentionEnabled && message.id === "retention-permission" && heldPrompt !== null) {
    const promptId = heldPrompt;
    heldPrompt = null;
    reply(promptId, { result: {
      stopReason: message.result?.outcome?.outcome === "selected" ? "end_turn" : "cancelled",
    } });
    return;
  }
  if (message.method === "initialize") {
    const initialize = () => reply(message.id, {
      result: {
        protocolVersion: message.params?.protocolVersion ?? "1",
        agentCapabilities: retentionEnabled ? { loadSession: true } : steeringEnabled ? { _meta: { siada: { steering: true } } } : {},
        agentInfo: { name: retentionEnabled ? `fake-agent-${process.pid}` : "fake-agent", version: "1.0.0" },
      },
    });
    if (initializationDelay) setTimeout(initialize, initializationDelay);
    else initialize();
    return;
  }
  if (message.method === "session/new") {
    reply(message.id, { result: { sessionId: retentionEnabled ? `session-${process.pid}` : "fake-session" } });
    return;
  }
  if (retentionEnabled && message.method === "session/load") {
    process.stdout.write(JSON.stringify({
      jsonrpc: "2.0", method: "session/update",
      params: { sessionId: message.params.sessionId, update: {
        sessionUpdate: "agent_message_chunk",
        content: { type: "text", text: `retained history ${process.pid}` },
      } },
    }) + "\n");
    reply(message.id, { result: {} });
    return;
  }
  if (retentionEnabled && message.method === "session/cancel" && heldPrompt !== null) {
    if (ignoreCancellation) return;
    const promptId = heldPrompt;
    heldPrompt = null;
    setTimeout(() => reply(promptId, { result: { stopReason: "cancelled" } }), 25);
    return;
  }
  if (message.method === "session/prompt") {
    // Error scenarios containing "generic-shape" answer the way
    // the SDK reports a bare exception (-32603 with the cause buried in
    // `data.details`); anything else answers with the cause as the message.
    const text = (message.params?.prompt ?? [])
      .map((block) => block.text ?? "")
      .join("");
    if (retentionEnabled) {
      process.stdout.write(JSON.stringify({
        jsonrpc: "2.0", method: "session/update",
        params: { sessionId: message.params.sessionId, update: {
          sessionUpdate: "agent_message_chunk", content: { type: "text", text: "retention test update" },
        } },
      }) + "\n");
      if (text === "retention-permission") {
        heldPrompt = message.id;
        process.stdout.write(JSON.stringify({
          jsonrpc: "2.0", id: "retention-permission", method: "session/request_permission",
          params: {
            sessionId: message.params.sessionId,
            toolCall: { toolCallId: "synthetic-read", title: "Synthetic read", kind: "read", status: "pending" },
            options: [{ optionId: "allow", name: "Allow", kind: "allow_once" }],
          },
        }) + "\n");
      } else if (text === "retention-hold" || text === "retention-ignore-cancel") {
        heldPrompt = message.id;
        ignoreCancellation = text === "retention-ignore-cancel";
      }
      else reply(message.id, { result: { stopReason: "end_turn" } });
      return;
    }
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

