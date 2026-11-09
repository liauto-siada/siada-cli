export interface DisplaySettings {
  scale: number;
  inputLines: number;
}

export const DISPLAY_SETTINGS_KEY = "display_settings";
export const DEFAULT_DISPLAY_SETTINGS: Readonly<DisplaySettings> = Object.freeze({
  scale: 90,
  inputLines: 1,
});

export function normalizeDisplaySettings(value: unknown): DisplaySettings {
  const settings = value && typeof value === "object" ? value as Partial<DisplaySettings> : {};
  return {
    scale: typeof settings.scale === "number" && Number.isFinite(settings.scale)
      ? Math.max(80, Math.min(120, Math.round(settings.scale / 5) * 5))
      : DEFAULT_DISPLAY_SETTINGS.scale,
    inputLines: typeof settings.inputLines === "number" && Number.isFinite(settings.inputLines)
      ? Math.max(1, Math.min(6, Math.round(settings.inputLines)))
      : DEFAULT_DISPLAY_SETTINGS.inputLines,
  };
}

export interface DisplaySettingsStore {
  load(): Promise<unknown>;
  save(settings: DisplaySettings): Promise<void>;
}

/** Extension settings survive panel close; the web client uses its own origin. */
export function browserDisplaySettingsStore(): DisplaySettingsStore {
  const storage = (globalThis as {
    chrome?: { storage?: { local?: {
      get(key: string): Promise<Record<string, unknown>>;
      set(values: Record<string, unknown>): Promise<void>;
    } } };
  }).chrome?.storage?.local;
  if (storage) {
    return {
      load: async () => (await storage.get(DISPLAY_SETTINGS_KEY))[DISPLAY_SETTINGS_KEY],
      save: settings => storage.set({ [DISPLAY_SETTINGS_KEY]: settings }),
    };
  }
  return {
    load: async () => {
      const stored = localStorage.getItem(DISPLAY_SETTINGS_KEY);
      return stored ? JSON.parse(stored) : undefined;
    },
    save: async settings => localStorage.setItem(DISPLAY_SETTINGS_KEY, JSON.stringify(settings)),
  };
}