import { afterEach, expect, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { BrowserLogin } from "../../shared/src/components/BrowserLogin";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
const original = globalThis.WebSocket;
let root: Root;
class FakeSocket {
  static OPEN = 1;
  static current: FakeSocket;
  readyState = 1;
  onmessage?: (event: { data: string }) => void;
  onerror?: () => void;
  onclose?: () => void;
  sent: string[] = [];
  closed = false;
  constructor(public url: string) { FakeSocket.current = this; }
  send(data: string) { this.sent.push(data); }
  close() { this.closed = true; }
  event(method: string, params: object) { this.onmessage?.({ data: JSON.stringify({ method, params }) }); }
}
afterEach(() => {
  act(() => root?.unmount()); globalThis.WebSocket = original; document.body.innerHTML = "";
});
async function mount(params: object) {
  globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
  const host = document.createElement("div"); document.body.append(host);
  await act(async () => {
    root = createRoot(host);
    root.render(<BrowserLogin endpoint="http://127.0.0.1:9315/local-bootstrap" extensionId={"a".repeat(32)} icon="/icon.png" />);
  });
  await act(async () => FakeSocket.current.event("ui/showLoginSelector", params));
  return host;
}
test("public selector never offers hosted login and cleans up its socket", async () => {
  const host = await mount({ providers: [] });
  expect(host.querySelectorAll("button").length).toBe(1);
  expect(host.textContent).not.toContain("LiId");
  await act(async () => FakeSocket.current.event("ui/loginDeviceUrl", { url: "https://example.com/device", openBrowser: false }));
  expect(host.querySelector("a")?.href).toBe("https://example.com/device");
  act(() => root.unmount());
  expect(FakeSocket.current.closed).toBe(true);
});
test("free trial renders two options and submits the CLI model ID", async () => {
  const host = await mount({ liidDisabled: true, freeTrialModels: [{ id: "synthetic:free", name: "Free model" }] });
  expect(host.querySelectorAll("button").length).toBe(2);
  expect(host.textContent).not.toContain("LiId");
  await act(async () => (Array.from(host.querySelectorAll("button")).find(b => b.textContent?.includes("Free Trial"))!).click());
  await act(async () => host.querySelector("form")!.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true })));
  expect(JSON.parse(FakeSocket.current.sent[0]!)).toEqual({ choice: "4", payload: { model: "synthetic:free" } });
  await act(async () => FakeSocket.current.event("ui/loginError", { error: "Save failed" }));
  expect(host.textContent).toContain("Save failed");
  await act(async () => (Array.from(host.querySelectorAll("button")).find(b => b.textContent === "重试登录")!).click());
  expect(FakeSocket.current.sent).toHaveLength(0);
});
test("reconfigure passes mode and cancel closes its owned socket", async () => {
  globalThis.WebSocket = FakeSocket as unknown as typeof WebSocket;
  const host = document.createElement("div"); document.body.append(host);
  let cancelled = false;
  await act(async () => {
    root = createRoot(host);
    root.render(<BrowserLogin endpoint="http://127.0.0.1:9315/local-bootstrap" extensionId={"a".repeat(32)} icon="/icon.png"
      reconfigure onCancel={() => { cancelled = true; root.unmount(); }} />);
  });
  expect(new URL(FakeSocket.current.url).searchParams.get("reconfigure")).toBe("1");
  await act(async () => host.querySelector("button")!.click());
  expect(cancelled).toBe(true);
  expect(FakeSocket.current.closed).toBe(true);
});
test("API key form masks secrets and success clears the form", async () => {
  const host = await mount({ liidDisabled: true });
  await act(async () => host.querySelector("button")!.click());
  expect(host.querySelector('input[type="password"]')).not.toBeNull();
  expect(host.querySelector('input[type="password"]')?.getAttribute("autocomplete")).toBe("off");
  await act(async () => FakeSocket.current.event("ui/loginSuccess", {}));
  expect(host.querySelector('input[type="password"]')).toBeNull();
  expect(host.textContent).toContain("登录成功");
});