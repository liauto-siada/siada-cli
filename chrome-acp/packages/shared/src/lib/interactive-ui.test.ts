import { expect, test } from "bun:test";
import { interactiveToolReferences, interactiveToolText, splitInteractiveMessage, uiActionPrompt, validUiState } from "./interactive-ui";
import { ACPClient } from "../acp/client";

const page = { id: "de06908b-41b8-4c39-83bc-2b3f1cb42a9b", title: "Budget" };
const fence = `\`\`\`siada-ui\n${JSON.stringify(page)}\n\`\`\``;

test("only a complete valid fence renders UI; streaming and invalid references stay text", () => {
  expect(splitInteractiveMessage(`Before\n${fence}\nAfter`).map(part => part.type)).toEqual(["text", "ui", "text"]);
  expect(splitInteractiveMessage(fence.slice(0, -1)).every(part => part.type === "text")).toBe(true);
  expect(splitInteractiveMessage(fence.replace(page.id, "../etc/passwd")).every(part => part.type === "text")).toBe(true);
  expect(splitInteractiveMessage("```siada-ui\n{broken}\n```")[0]?.type).toBe("text");
});
test("extracts UI from both ACP text and serialized MCP content without rendering raw inputs", () => {
  expect(interactiveToolText(JSON.stringify({ content: [{ type: "text", text: fence }] }))).toBe(fence);
  expect(interactiveToolText({ rawInput: { html: fence } })).toBe("");
});
test("the installed Python SDK text dictionary repr renders without an assistant quote", () => {
  const repr = `{'type': 'text', 'text': '${fence.replace(/\\/g, "\\\\").replace(/'/g, "\\'").replace(/\n/g, "\\n")}'}`;
  expect(interactiveToolText(repr)).toBe(fence);
  expect(interactiveToolReferences([{ type: "content", content: { type: "text", text: repr } }])).toEqual([page]);
  expect(interactiveToolText("{'type': 'text', 'text': '\\u4e2d\\U0001f680'}")).toBe("中🚀");
  expect(interactiveToolText("{'type': 'text', 'text': __import__('os').system('bad')}")).not.toBe(fence);
});
test("progress and multiple ACP result blocks do not hide the UI reference", () => {
  const wrapped = JSON.stringify({ result: { content: [{ type: "text", text: JSON.stringify({ content: [{ type: "text", text: fence }] }) }] } });
  const content = [
    { type: "content", content: { type: "text", text: "Preparing the UI…" } },
    { type: "content", content: { type: "text", text: wrapped } },
    { type: "content", content: { type: "text", text: '{"note":"Complete"}' } },
  ];
  expect(interactiveToolReferences(content)).toEqual([page]);
  expect(interactiveToolReferences([{ type: "content", content: { type: "text", text: "Complete" } }], { content: [{ type: "text", text: fence }] })).toEqual([page]);
  expect(interactiveToolReferences({ rawInput: { html: fence } })).toEqual([]);
  const cycle: Record<string, unknown> = {};
  cycle.content = cycle;
  expect(interactiveToolText(cycle)).toBe("");
});
test("actions include exact page identity and current state, not a bare button label", () => {
  const prompt = uiActionPrompt(page, " Save this ", { range: 7, amount: 42 });
  expect(prompt).toStartWith("Save this\n\n");
  expect(prompt).toContain('"range":7');
  expect(prompt).toContain(page.id);
  expect(validUiState([])).toBe(false);
  expect(validUiState({ x: "x".repeat(65536) })).toBe(false);
  expect(validUiState({ range: 7 })).toBe(true);
  const cyclic: Record<string, unknown> = {};
  cyclic.self = cyclic;
  expect(validUiState(cyclic)).toBe(false);
});
test("frame and export URLs use the proxy origin and never contain its credentials", () => {
  const client = new ACPClient({ proxyUrl: "wss://localhost:9320/ws?token=secret", token: "secret" });
  expect(client.interactiveUiUrl(page.id, "frame")).toBe(`https://localhost:9320/ui/${page.id}/frame`);
  expect(client.interactiveUiUrl(page.id)).not.toContain("secret");
});

test("Share authenticates publication without putting credentials into the LAN URL", async () => {
  const original = globalThis.fetch;
  let request: { url: string; init?: RequestInit } | undefined;
  globalThis.fetch = (async (url: RequestInfo | URL, init?: RequestInit) => {
    request = { url: String(url), init };
    return Response.json({ url: `http://192.168.1.20:9316/share/${page.id}` }, { status: 201 });
  }) as unknown as typeof fetch;
  try {
    const client = new ACPClient({ proxyUrl: "ws://localhost:9315/ws?token=secret" });
    const result = await client.shareInteractiveUi(page.id, { amount: 42 });
    expect(request?.url).toBe(`http://localhost:9315/ui/${page.id}/share`);
    expect((request?.init?.headers as Record<string, string>).Authorization).toBe("Bearer secret");
    expect(JSON.parse(request!.init!.body as string).state).toEqual({ amount: 42 });
    expect(result.url).not.toContain("secret");
  } finally { globalThis.fetch = original; }
});

test("Share rejects unsafe or loopback links rather than presenting a false LAN URL", async () => {
  const original = globalThis.fetch;
  try {
    const client = new ACPClient({ proxyUrl: "ws://localhost:9315/ws" });
    for (const url of ["javascript:alert(1)", `http://localhost:9316/share/${page.id}`, `http://192.168.1.20:9316/share/${page.id}?token=secret`]) {
      globalThis.fetch = (async () => Response.json({ url }, { status: 201 })) as unknown as typeof fetch;
      await expect(client.shareInteractiveUi(page.id, {})).rejects.toThrow("Invalid share URL");
    }
  } finally { globalThis.fetch = original; }
});