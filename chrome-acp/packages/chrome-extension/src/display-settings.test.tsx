import { afterEach, expect, test } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { DisplaySettingsButton, DisplaySettingsProvider } from "../../shared/src/components/DisplaySettings";
import type { DisplaySettingsStore } from "../../shared/src/lib/display-settings";

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
let root: Root;
afterEach(() => {
  act(() => root?.unmount());
  document.body.innerHTML = "";
  document.documentElement.style.cssText = "";
});
async function mount(store: DisplaySettingsStore) {
  const host = document.createElement("div");
  document.body.append(host);
  await act(async () => {
    root = createRoot(host);
    root.render(<DisplaySettingsProvider store={store}><DisplaySettingsButton /></DisplaySettingsProvider>);
  });
  await act(async () => host.querySelector<HTMLButtonElement>("button")!.click());
}
function resetButton() {
  return Array.from(document.querySelectorAll<HTMLButtonElement>("button")).find(button => button.textContent === "恢复默认")!;
}

test("a late saved-settings read cannot undo a user's reset", async () => {
  let finish!: (value: unknown) => void;
  const saved: unknown[] = [];
  await mount({
    load: () => new Promise(resolve => { finish = resolve; }),
    save: async value => { saved.push(value); },
  });
  await act(async () => resetButton().click());
  await act(async () => finish({ scale: 120, inputLines: 6 }));
  expect(document.documentElement.style.fontSize).toBe("14.4px");
  expect(document.documentElement.style.getPropertyValue("--siada-input-lines")).toBe("1");
  expect(saved).toEqual([{ scale: 90, inputLines: 1 }]);
});

test("unmount releases the document styles owned by the provider", async () => {
  document.documentElement.style.fontSize = "19px";
  document.documentElement.style.setProperty("--siada-input-lines", "4");
  await mount({ load: async () => ({ scale: 100, inputLines: 3 }), save: async () => {} });
  expect(document.documentElement.style.fontSize).toBe("16px");
  act(() => root.unmount());
  expect(document.documentElement.style.fontSize).toBe("19px");
  expect(document.documentElement.style.getPropertyValue("--siada-input-lines")).toBe("4");
});

test("failed saving shows a retry message and a successful retry clears it", async () => {
  let failing = true;
  await mount({
    load: async () => ({ scale: 100, inputLines: 2 }),
    save: async () => { if (failing) throw new Error("storage full"); },
  });
  await act(async () => resetButton().click());
  expect(document.querySelector('[role="alert"]')?.textContent).toContain("保存失败");
  failing = false;
  await act(async () => resetButton().click());
  expect(document.querySelector('[role="alert"]')).toBeNull();
});