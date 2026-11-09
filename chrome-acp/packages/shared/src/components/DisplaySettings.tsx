import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { SlidersHorizontal } from "lucide-react";
import {
  DEFAULT_DISPLAY_SETTINGS,
  browserDisplaySettingsStore,
  normalizeDisplaySettings,
  type DisplaySettings,
  type DisplaySettingsStore,
} from "../lib/display-settings";
import { Button } from "./ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "./ui/popover";
import "./display-settings.css";

interface DisplayContext {
  settings: DisplaySettings;
  update: (patch: Partial<DisplaySettings>) => void;
  error: string | null;
}

const DisplaySettingsContext = createContext<DisplayContext | null>(null);

export function useDisplaySettings(): DisplaySettings {
  return useContext(DisplaySettingsContext)?.settings ?? DEFAULT_DISPLAY_SETTINGS;
}

export function DisplaySettingsProvider({ children, store: providedStore }: {
  children: ReactNode;
  store?: DisplaySettingsStore;
}) {
  const store = useMemo(() => providedStore ?? browserDisplaySettingsStore(), [providedStore]);
  const [settings, setSettings] = useState<DisplaySettings>(() => ({ ...DEFAULT_DISPLAY_SETTINGS }));
  const current = useRef(settings);
  const revision = useRef(0);
  const writes = useRef<Promise<void>>(Promise.resolve());
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const initialRevision = revision.current;
    void store.load().then(value => {
      // A slow storage read must not overwrite a user's edits.
      if (!active || revision.current !== initialRevision) return;
      const loaded = normalizeDisplaySettings(value);
      current.current = loaded;
      setSettings(loaded);
    }).catch(() => {
      if (active && revision.current === initialRevision) setError("无法读取显示设置，可以重新调整后保存");
    });
    return () => { active = false; };
  }, [store]);

  useLayoutEffect(() => {
    const root = document.documentElement;
    const oldFont = root.style.fontSize;
    const oldLines = root.style.getPropertyValue("--siada-input-lines");
    root.style.fontSize = `${16 * settings.scale / 100}px`;
    root.style.setProperty("--siada-input-lines", String(settings.inputLines));
    return () => {
      root.style.fontSize = oldFont;
      if (oldLines) root.style.setProperty("--siada-input-lines", oldLines);
      else root.style.removeProperty("--siada-input-lines");
    };
  }, [settings]);

  const update = useCallback((patch: Partial<DisplaySettings>) => {
    revision.current++;
    const next = normalizeDisplaySettings({ ...current.current, ...patch });
    current.current = next;
    setSettings(next);
    setError(null);
    // Serial saves keep the latest drag/keyboard adjustment durable.
    const work = writes.current.catch(() => {}).then(() => store.save(next));
    writes.current = work;
    void work.then(
      () => { if (current.current === next) setError(null); },
      () => { if (current.current === next) setError("显示设置保存失败，请再次调整或点击恢复默认重试"); },
    );
  }, [store]);

  return (
    <DisplaySettingsContext.Provider value={{ settings, update, error }}>
      {children}
    </DisplaySettingsContext.Provider>
  );
}

export function DisplaySettingsButton() {
  const context = useContext(DisplaySettingsContext);
  if (!context) return null;
  const { settings, update, error } = context;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button type="button" variant="ghost" size="sm" className="h-8 gap-1 px-2"
          aria-label="显示设置" title="调节字号、间距和输入框">
          <SlidersHorizontal className="size-4" />
          <span className="text-xs">显示</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 max-w-[calc(100vw-1rem)] space-y-4 p-3">
        <div className="text-sm font-medium">显示设置</div>
        <div className="space-y-2">
          <label htmlFor="siada-display-scale" className="flex justify-between text-sm">
            <span>界面缩放</span><output>{settings.scale}%</output>
          </label>
          <input id="siada-display-scale" aria-label="界面缩放" className="w-full accent-primary"
            type="range" min={80} max={120} step={5} value={settings.scale}
            onChange={event => update({ scale: Number(event.target.value) })} />
          <p className="text-xs text-muted-foreground">同时调节字号、间距和交互界面大小</p>
        </div>
        <div className="space-y-2">
          <label htmlFor="siada-input-lines" className="flex justify-between text-sm">
            <span>输入框行数</span><output>{settings.inputLines} 行</output>
          </label>
          <input id="siada-input-lines" aria-label="输入框行数" className="w-full accent-primary"
            type="range" min={1} max={6} step={1} value={settings.inputLines}
            onChange={event => update({ inputLines: Number(event.target.value) })} />
          <p className="text-xs text-muted-foreground">长消息会在输入框内滚动</p>
        </div>
        <Button type="button" variant="outline" size="sm"
          onClick={() => update(DEFAULT_DISPLAY_SETTINGS)}>恢复默认</Button>
        {error && <p role="alert" className="text-xs text-destructive">{error}</p>}
      </PopoverContent>
    </Popover>
  );
}