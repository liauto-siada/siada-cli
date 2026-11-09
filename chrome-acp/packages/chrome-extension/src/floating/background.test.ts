import { describe, expect, mock, test } from "bun:test";
import { registerFloatingLauncher } from "./background";
import { OPEN_SIDEPANEL_MESSAGE } from "./launcher";

type MessageListener = (
  message: unknown,
  sender: chrome.runtime.MessageSender,
  sendResponse: (response: unknown) => void,
) => boolean | void;

function setup(open = mock(() => Promise.resolve())) {
  let listener!: MessageListener;
  registerFloatingLauncher({
    runtime: {
      id: "test-extension",
      onMessage: { addListener: (callback: typeof listener) => { listener = callback; } },
    },
    sidePanel: { open },
  } as unknown as Pick<typeof chrome, "runtime" | "sidePanel">);
  return { listener, open };
}

const sender = { id: "test-extension", frameId: 0, tab: { id: 17 } } as chrome.runtime.MessageSender;

describe("floating launcher sidepanel bridge", () => {
  test("opens the sender's tab synchronously before returning to preserve the gesture", async () => {
    const { listener, open } = setup();
    const response = mock();
    expect(listener({ type: OPEN_SIDEPANEL_MESSAGE }, sender, response)).toBe(true);
    expect(open).toHaveBeenCalledWith({ tabId: 17 });
    await Promise.resolve();
    expect(response).toHaveBeenCalledWith({ ok: true });
  });

  test("ignores unrelated messages and rejects foreign or non-top-level senders", () => {
    const { listener, open } = setup();
    const response = mock();
    listener({ type: "other" }, sender, response);
    expect(response).not.toHaveBeenCalled();
    for (const invalid of [
      { ...sender, id: "foreign" },
      { ...sender, frameId: 1 },
      { ...sender, tab: undefined },
    ]) {
      listener({ type: OPEN_SIDEPANEL_MESSAGE }, invalid, response);
    }
    expect(open).not.toHaveBeenCalled();
    expect(response).toHaveBeenCalledTimes(3);
  });

  test("returns open failures so the launcher can expose an error and retry", async () => {
    const open = mock(() => Promise.reject(new Error("gesture rejected")));
    const { listener } = setup(open);
    const response = mock();
    listener({ type: OPEN_SIDEPANEL_MESSAGE }, sender, response);
    await Promise.resolve();
    expect(response).toHaveBeenCalledWith({ ok: false, error: "gesture rejected" });
  });
});