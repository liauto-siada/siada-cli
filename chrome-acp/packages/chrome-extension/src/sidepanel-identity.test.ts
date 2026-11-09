import { afterEach, expect, test } from "bun:test";
import { loadSidepanelIdentity } from "./sidepanel-identity";

const originalChrome = globalThis.chrome;
afterEach(() => { globalThis.chrome = originalChrome; });

test("reopens with the same identity and keeps window histories separate", async () => {
  let windowId = 1;
  const local: Record<string, unknown> = { sidepanel_last_session: { sessionId: "legacy-session" } };
  const session: Record<string, unknown> = {};
  const storage = (values: Record<string, unknown>) => ({
    get: async (keys: string[]) => Object.fromEntries(keys.filter(key => key in values).map(key => [key, values[key]])),
    set: async (items: Record<string, unknown>) => { Object.assign(values, items); },
  });
  globalThis.chrome = {
    windows: { getCurrent: async () => ({ id: windowId }) },
    storage: { local: storage(local), session: storage(session) },
  } as unknown as typeof chrome;
  const first = await loadSidepanelIdentity();
  expect(first.lastSession).toEqual({ sessionId: "legacy-session" });
  local[first.lastSessionKey] = { sessionId: "first-window" };
  const reopened = await loadSidepanelIdentity();
  expect(reopened.retentionId).toBe(first.retentionId);
  expect(reopened.lastSession).toEqual({ sessionId: "first-window" });
  windowId = 2;
  const second = await loadSidepanelIdentity();
  expect(second.retentionId).not.toBe(first.retentionId);
  expect(second.lastSessionKey).not.toBe(first.lastSessionKey);
  expect(second.lastSession).toBeNull();
});