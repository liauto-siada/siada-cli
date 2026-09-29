import { beforeEach, describe, expect, test } from "bun:test";

// pdf-handler.ts self-wires at import: reads persisted state, applies DNR
// rules, subscribes to storage changes. Stub the chrome APIs first.

interface UpdateCall {
  addRules?: chrome.declarativeNetRequest.Rule[];
  removeRuleIds?: number[];
}

let updateCalls: UpdateCall[] = [];
let storageData: Record<string, unknown> = {};
let storageListeners: ((changes: Record<string, { newValue?: unknown }>, area: string) => void)[] = [];

const chromeStub = {
  runtime: {
    id: "test-extension-id",
    getURL: (p: string) => `chrome-extension://test-extension-id/${p}`,
  },
  declarativeNetRequest: {
    updateDynamicRules: async (options: UpdateCall) => {
      updateCalls.push(options);
    },
  },
  storage: {
    local: {
      get: async (key: string) => ({ [key]: storageData[key] }),
      set: async (items: Record<string, unknown>) => Object.assign(storageData, items),
    },
    onChanged: {
      addListener: (fn: (changes: Record<string, { newValue?: unknown }>, area: string) => void) =>
        storageListeners.push(fn),
    },
  },
};

(globalThis as { chrome?: unknown }).chrome = chromeStub;

const { applyPdfHandlerRules } = await import("./pdf-handler");

beforeEach(() => {
  updateCalls = [];
});

describe("applyPdfHandlerRules", () => {
  test("enable registers redirect rules pointing at the vendored viewer", async () => {
    await applyPdfHandlerRules(true);
    expect(updateCalls).toHaveLength(1);
    const call = updateCalls[0]!;
    expect(call.addRules!.length).toBeGreaterThanOrEqual(5);

    const ids = call.addRules!.map((r) => r.id);
    expect(new Set(ids).size).toBe(ids.length); // unique ids

    const redirectRules = call.addRules!.filter((r) => r.action.type === "redirect");
    expect(redirectRules.length).toBeGreaterThanOrEqual(4);
    for (const rule of redirectRules) {
      const sub = (rule.action as { redirect: { regexSubstitution: string } }).redirect.regexSubstitution;
      expect(sub).toStartWith("chrome-extension://test-extension-id/dist/pdf/web/viewer.html?DNR:");
    }

    // The plain application/pdf content-type rule must exist.
    const ctRule = call.addRules!.find(
      (r) =>
        r.action.type === "redirect" &&
        r.condition.responseHeaders?.some(
          (h) => h.header === "content-type" && h.values?.includes("application/pdf"),
        ),
    );
    expect(ctRule).toBeDefined();
    // POST must be excluded: the viewer re-fetches via GET.
    expect(ctRule!.condition.excludedRequestMethods).toContain("post");

    // file:// PDFs are redirected (fires only when the user granted file access).
    const fileRule = call.addRules!.find((r) => r.condition.regexFilter?.startsWith("^file://"));
    expect(fileRule).toBeDefined();
    expect(fileRule!.action.type).toBe("redirect");
  });

  test("disable removes exactly the rule ids we registered", async () => {
    await applyPdfHandlerRules(true);
    updateCalls = [];
    await applyPdfHandlerRules(false);
    expect(updateCalls).toHaveLength(1);
    expect(updateCalls[0]!.addRules).toBeUndefined();
    expect(updateCalls[0]!.removeRuleIds!.length).toBeGreaterThanOrEqual(5);
  });

  test("storage change to enabled registers rules; to false removes them", async () => {
    expect(storageListeners.length).toBeGreaterThan(0);
    const listener = storageListeners[0]!;

    listener({ pdf_handler_enabled: { newValue: true } }, "local");
    await new Promise((r) => setTimeout(r, 10));
    expect(updateCalls.some((c) => c.addRules)).toBe(true);

    updateCalls = [];
    listener({ pdf_handler_enabled: { newValue: false } }, "local");
    await new Promise((r) => setTimeout(r, 10));
    expect(updateCalls).toHaveLength(1);
    expect(updateCalls[0]!.removeRuleIds).toBeDefined();
  });

  test("unrelated storage changes are ignored", async () => {
    const listener = storageListeners[0]!;
    listener({ explain_enabled: { newValue: true } }, "local");
    await new Promise((r) => setTimeout(r, 10));
    expect(updateCalls).toHaveLength(0);
  });
});
