import { afterEach, expect, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { InstallGuide, INSTALL_COMMANDS } from "./components/InstallGuide";
import { ACPClient } from "@chrome-acp/shared/acp";
import { ThemeProvider } from "../../shared/src/lib/theme";
// Browser tools register a runtime listener at import time.
(globalThis as any).chrome = { runtime: { onMessage: { addListener: () => {} } }, tabs: { onRemoved: { addListener: () => {} } } };
const { ACPConnect } = await import("./components/ACPConnect");

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
let root: Root | undefined;
const originalFetch = globalThis.fetch;
const originalSocket = globalThis.WebSocket;
afterEach(() => {
  act(() => root?.unmount());
  root = undefined;
  document.body.innerHTML = "";
  globalThis.fetch = originalFetch;
  globalThis.WebSocket = originalSocket;
});

function chromeFixture() {
  globalThis.WebSocket = class {
    static OPEN = 1;
    readyState = 1;
    close() {}
    send() {}
  } as unknown as typeof WebSocket;
  (globalThis as any).chrome = {
    runtime: { id: "a".repeat(32), getURL: (path: string) => `chrome-extension://${"a".repeat(32)}/${path}` },
    storage: { local: {
      get: async () => ({}), set: async () => {},
    } },
  };
}

async function mount(element: React.ReactNode) {
  const container = document.createElement("div");
  document.body.append(container);
  await act(async () => { root = createRoot(container); root.render(<ThemeProvider>{element}</ThemeProvider>); });
  return container;
}

test("install guide displays icon, exact commands and remote access explanation", async () => {
  chromeFixture();
  const container = await mount(<InstallGuide onConnect={() => {}} />);
  expect(container.querySelector("img")?.alt).toBe("Chrome ACP");
  expect(container.textContent).toContain(INSTALL_COMMANDS.unix);
  expect(container.textContent).toContain(INSTALL_COMMANDS.windows);
  expect(container.textContent).toContain("对外开放");
  let opened = false;
  await act(async () => root?.render(<InstallGuide onConnect={() => { opened = true; }} />));
  await act(async () => (Array.from(container.querySelectorAll("button")).find(button => button.textContent?.includes("其它设备")) as HTMLButtonElement).click());
  expect(opened).toBe(true);
});

test("unreachable local service shows install guide without connection fields", async () => {
  chromeFixture();
  globalThis.fetch = (async () => { throw new Error("offline"); }) as unknown as typeof fetch;
  const states: string[] = [];
  const container = await mount(<ACPConnect expanded onExpandedChange={() => {}} onStartupStateChange={state => states.push(state)} />);
  expect(container.textContent).toContain("安装 Siada CLI");
  expect(container.textContent).toContain("已安装 / 其它设备存在 Siada CLI");
  expect(container.querySelector("input")).toBeNull();
  expect(states.at(-1)).toBe("install");
});

test("local login displays Chrome wizard without opening a terminal", async () => {
  chromeFixture();
  const methods: string[] = [];
  globalThis.fetch = (async (_url: string, init?: RequestInit) => {
    methods.push(init?.method ?? "");
    return Response.json({ schemaVersion: 1, authStatus: "login_required", terminalOpened: true });
  }) as typeof fetch;
  const container = await mount(<ACPConnect expanded onExpandedChange={() => {}} />);
  expect(methods).toEqual(["GET"]);
  expect(container.textContent).toContain("登录 Siada CLI");
  expect(container.textContent).not.toContain("安装 Siada CLI");
});

test("installed-device entry opens actual connection fields", async () => {
  chromeFixture();
  globalThis.fetch = (async () => { throw new Error("offline"); }) as unknown as typeof fetch;
  const connect = ACPClient.prototype.connect;
  ACPClient.prototype.connect = async () => {};
  try {
    const container = await mount(<ACPConnect expanded onExpandedChange={() => {}} />);
    await act(async () => (Array.from(container.querySelectorAll("button")).find(button => button.textContent?.includes("其它设备")) as HTMLButtonElement).click());
    expect(container.querySelector("input")).not.toBeNull();
    expect(container.textContent).not.toContain("安装 Siada CLI");
  } finally { ACPClient.prototype.connect = connect; }
});

test("login polling transitions to connection after credentials are saved", async () => {
  chromeFixture();
  const originalTimer = globalThis.setTimeout;
  const connect = ACPClient.prototype.connect;
  let poll: (() => void) | undefined;
  let ready = false;
  globalThis.setTimeout = ((callback: () => void, delay?: number) => {
    if (delay === 5000) { poll = callback; return 0; }
    return originalTimer(callback, delay);
  }) as typeof setTimeout;
  ACPClient.prototype.connect = async () => {};
  globalThis.fetch = (async () => Response.json(ready
    ? { schemaVersion: 1, proxyUrl: "ws://127.0.0.1:9315/ws", token: "synthetic" }
    : { schemaVersion: 1, authStatus: "login_required", terminalOpened: true })) as unknown as typeof fetch;
  try {
    const container = await mount(<ACPConnect expanded onExpandedChange={() => {}} />);
    expect(container.textContent).toContain("登录 Siada CLI");
    ready = true;
    await act(async () => { poll?.(); });
    expect(container.textContent).not.toContain("登录 Siada CLI");
    expect(container.querySelector("input")).not.toBeNull();
  } finally {
    globalThis.setTimeout = originalTimer;
    ACPClient.prototype.connect = connect;
  }
});