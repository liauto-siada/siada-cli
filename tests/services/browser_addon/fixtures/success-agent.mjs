// Offline ACP peer for manual release-chain acceptance.
import {createInterface} from "node:readline";
const input = createInterface({input: process.stdin});
const send = message => process.stdout.write(JSON.stringify({jsonrpc: "2.0", ...message}) + "\n");
input.on("line", line => {
  const message = JSON.parse(line);
  if (message.method === "initialize") {
    send({id: message.id, result: {protocolVersion: message.params.protocolVersion, agentCapabilities: {}, agentInfo: {name: "offline-release-peer", version: "1.0.0"}}});
  } else if (message.method === "session/new") {
    send({id: message.id, result: {sessionId: "offline-session"}});
  } else if (message.method === "session/prompt") {
    send({method: "session/update", params: {sessionId: "offline-session", update: {sessionUpdate: "agent_message_chunk", content: {type: "text", text: "OFFLINE_RELEASE_CHAIN_OK"}}}});
    send({id: message.id, result: {stopReason: "end_turn"}});
  } else if (message.id !== undefined) {
    send({id: message.id, result: {}});
  }
});