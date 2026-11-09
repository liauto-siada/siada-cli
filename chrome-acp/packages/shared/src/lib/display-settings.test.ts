import { afterEach, expect, test } from "bun:test";
import { DEFAULT_DISPLAY_SETTINGS, DISPLAY_SETTINGS_KEY, browserDisplaySettingsStore, normalizeDisplaySettings } from "./display-settings";

const originalChrome = (globalThis as any).chrome;
const originalStorage = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
afterEach(() => {
  (globalThis as any).chrome = originalChrome;
  if (originalStorage) Object.defineProperty(globalThis, "localStorage", originalStorage);
  else delete (globalThis as any).localStorage;
});

test("display preferences reject corrupt values and clamp unsafe sizes", () => {
  expect(normalizeDisplaySettings(null)).toEqual(DEFAULT_DISPLAY_SETTINGS);
  expect(normalizeDisplaySettings({ scale: NaN, inputLines: "huge" })).toEqual(DEFAULT_DISPLAY_SETTINGS);
  expect(normalizeDisplaySettings({ scale: 1000, inputLines: -8 })).toEqual({ scale: 120, inputLines: 1 });
  expect(normalizeDisplaySettings({ scale: 83, inputLines: 4.3 })).toEqual({ scale: 85, inputLines: 4 });
});

test("extension storage persists preferences separately from connection credentials", async () => {
  const values: Record<string, unknown> = { acp_settings: { proxyUrl: "ws://example.test/ws" } };
  (globalThis as any).chrome = { storage: { local: {
    get: async (key: string) => ({ [key]: values[key] }),
    set: async (patch: Record<string, unknown>) => Object.assign(values, patch),
  } } };
  await browserDisplaySettingsStore().save({ scale: 80, inputLines: 2 });
  expect(await browserDisplaySettingsStore().load()).toEqual({ scale: 80, inputLines: 2 });
  expect(values.acp_settings).toEqual({ proxyUrl: "ws://example.test/ws" });
  expect(Object.keys(values)).toEqual(["acp_settings", DISPLAY_SETTINGS_KEY]);
});

test("web storage restores values in a newly created settings store", async () => {
  (globalThis as any).chrome = undefined;
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  } });
  await browserDisplaySettingsStore().save({ scale: 85, inputLines: 1 });
  expect(await browserDisplaySettingsStore().load()).toEqual({ scale: 85, inputLines: 1 });
});

test("storage failure is surfaced to the settings UI instead of claiming success", async () => {
  (globalThis as any).chrome = { storage: { local: {
    get: async () => ({}),
    set: async () => { throw new Error("storage unavailable"); },
  } } };
  await expect(browserDisplaySettingsStore().save({ scale: 90, inputLines: 1 })).rejects.toThrow("storage unavailable");
});