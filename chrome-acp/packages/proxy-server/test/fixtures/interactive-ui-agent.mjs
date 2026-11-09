// Deterministic ACP agent; all generation and actions are synthetic and offline.
import { createInterface } from "node:readline";
import { readFile } from "node:fs/promises";

let mcpUrl;
let pageId;
const sessionId = "interactive-ui-test-session";
function send(value) { process.stdout.write(JSON.stringify({ jsonrpc: "2.0", ...value }) + "\n"); }
function update(value) { send({ method: "session/update", params: { sessionId, update: value } }); }
function emitTool(name, id, result) {
  // Mirror the installed Python ACP adapter: SDK text dicts become a Python
  // repr, and completion appends its content to the earlier progress block.
  const text = result.content.filter(item => item.type === "text").map(item => item.text).join("\n");
  const output = "{'type': 'text', 'text': " + JSON.stringify(text) + "}";
  update({ sessionUpdate: "tool_call", toolCallId: id, title: name, kind: "other", status: "in_progress", content: [{ type: "content", content: { type: "text", text: "Preparing the interface…" } }] });
  update({ sessionUpdate: "tool_call_update", toolCallId: id, status: "completed", rawOutput: output, content: [{ type: "content", content: { type: "text", text: output } }] });
}
createInterface({ input: process.stdin }).on("line", async line => {
  const message = JSON.parse(line);
  if (message.method === "initialize") send({ id: message.id, result: { protocolVersion: message.params.protocolVersion, agentCapabilities: { loadSession: true, sessionCapabilities: { list: {} } }, agentInfo: { name: "Interactive UI test agent", version: "1" } } });
  if (message.method === "session/new" || message.method === "session/load") {
    mcpUrl = message.params.mcpServers.find(server => server.name === "browser").url;
    send({ id: message.id, result: message.method === "session/new" ? { sessionId } : {} });
  }
  if (message.method === "session/list") {
    send({ id: message.id, result: { sessions: [{ sessionId, cwd: "/tmp", title: "Interactive UI verification" }] } });
  }
  if (message.method === "session/prompt") {
    try {
      const text = message.params.prompt.map(block => block.text || "").join("");
      if (text.includes("<siada-ui-action>")) {
        const action = JSON.parse(text.split("<siada-ui-action>\n")[1].split("\n</siada-ui-action>")[0]);
        update({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: `已收到界面操作：range=${action.state.range}，budget=${action.state.budget}，cylinder=${action.state.cylinder}，angle=${action.state.angle}，id=${action.id}` } });
      } else if (text.includes("integration-3d")) {
        const call = async (name, args) => {
          const response = await fetch(mcpUrl, {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }),
          });
          const { result } = await response.json();
          if (result.isError) throw new Error(result.content[0].text);
          return result;
        };
        const created = JSON.parse((await call("browser_ui_project", { title: "3D source integration", template: "teardown-v8" })).content[0].text);
        if (created.toolkitSource !== "bundled") throw new Error("The 3D test requires the bundled toolkit");
        const main = await readFile(`${created.sourceDirectory}/main.js`, "utf8");
        for (let revision = 0; revision < 2; revision++) {
          const result = await call("browser_ui_build", { id: created.id, ...(revision ? { files: { "main.js": main.replace("V8 发动机 · 交互拆解", "V8 发动机 · 更新后") } } : {}) });
          const reference = JSON.parse(result.content[0].text.split("```siada-ui\n")[1].split("\n```")[0]);
          pageId = reference.id;
          emitTool("browser_ui_build", `build-${revision}-${pageId}`, result);
        }
        update({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: "3D integration ready" } });
      } else {
        const response = await fetch(mcpUrl, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "browser_present_ui", arguments: {
            title: "可探索的经营看板", html: await readFile(new URL("./interactive-dashboard.html", import.meta.url), "utf8"), state: { range: 30, budget: 500 },
          } } }),
        });
        const { result } = await response.json();
        if (result.isError) throw new Error(result.content[0].text);
        pageId = JSON.parse(result.content[0].text.split("```siada-ui\n")[1].split("\n```")[0]).id;
        emitTool("browser_present_ui", `ui-${pageId}`, result);
        update({ sessionUpdate: "agent_message_chunk", content: { type: "text", text: "调整时间范围和预算，再点击界面里的按钮继续分析。也可以保存为网页。" } });
      }
      send({ id: message.id, result: { stopReason: "end_turn" } });
    } catch (error) { send({ id: message.id, error: { code: -32603, message: error.message } }); }
  }
});