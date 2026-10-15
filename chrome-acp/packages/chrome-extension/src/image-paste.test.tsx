import { afterAll, afterEach, expect, spyOn, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { ACPClient } from "@chrome-acp/shared/acp";
import { ChatInterface } from "../../shared/src/components/ChatInterface";
import { TooltipProvider } from "../../shared/src/components/ui/tooltip";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | undefined;
const objectURL = spyOn(URL, "createObjectURL").mockImplementation(() => "blob:synthetic-paste");
const revokeURL = spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
afterAll(() => {
  objectURL.mockRestore();
  revokeURL.mockRestore();
});

afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  document.body.innerHTML = "";
  objectURL.mockClear();
  revokeURL.mockClear();
});

async function renderChat(supportsImages: boolean) {
  const client = new ACPClient({ proxyUrl: "ws://localhost:9315/ws" });
  Object.defineProperty(client, "supportsImages", { value: supportsImages });
  let sessionCreated = (_sessionId: string) => {};
  client.setSessionCreatedHandler = (handler) => { sessionCreated = handler; };
  client.createSession = async () => { sessionCreated("paste-session"); };
  const container = document.createElement("div");
  document.body.append(container);
  await act(async () => {
    root = createRoot(container);
    root.render(<TooltipProvider><ChatInterface client={client} /></TooltipProvider>);
  });
  return container;
}

for (const supportsImages of [false, true]) {
  test(`pasted images remain visible and removable with supportsImages=${supportsImages}`, async () => {
    const container = await renderChat(supportsImages);
    const textarea = container.querySelector("textarea")!;
    expect(textarea.disabled).toBe(false);
    const file = new File(["synthetic image"], "clipboard.png", { type: "image/png" });
    const paste = new Event("paste", { bubbles: true, cancelable: true });
    Object.defineProperty(paste, "clipboardData", {
      value: { items: [{ kind: "file", getAsFile: () => file }] },
    });
    await act(async () => { textarea.dispatchEvent(paste); });
    expect(paste.defaultPrevented).toBe(true);
    const preview = container.querySelector('form img[alt="clipboard.png"]');
    expect(preview?.getAttribute("src")).toBe("blob:synthetic-paste");
    expect(container.querySelector("form")?.textContent).toContain("clipboard.png");
    const remove = container.querySelector<HTMLButtonElement>('button[aria-label="Remove attachment"]');
    expect(remove).not.toBeNull();
    await act(async () => { remove!.click(); });
    expect(container.querySelector("form img")).toBeNull();
    expect(revokeURL).toHaveBeenCalledWith("blob:synthetic-paste");
  });
}