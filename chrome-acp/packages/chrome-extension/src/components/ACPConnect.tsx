// Re-export from shared with browser tool handler configured
import { useEffect, useState } from "react";
import { ACPConnect as SharedACPConnect } from "@chrome-acp/shared/components";
import { executeBrowserTool } from "@/tools/browser";
import type { ACPClient, ACPSettings } from "@chrome-acp/shared/acp";
import { loadStoredSettings, persistSettings, loadExplainEnabled, persistExplainEnabled, loadPdfHandlerEnabled, persistPdfHandlerEnabled } from "@/settings";

// Toggle for the immersive explain feature ("✨ 解释" floating button injected
// into every page). Default OFF; persisted to chrome.storage.local where the
// content script watches it.
function ExplainToggle() {
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    void loadExplainEnabled().then(setEnabled);
  }, []);

  if (enabled === null) return null;

  return (
    <div className="flex items-center justify-between">
      <label htmlFor="explain-toggle" className="text-sm font-medium leading-none">
        划词解释
        <span className="text-muted-foreground font-normal ml-1.5">在网页选中文本时显示「✨ 解释」按钮</span>
      </label>
      <input
        id="explain-toggle"
        type="checkbox"
        className="h-4 w-4 shrink-0 cursor-pointer accent-primary"
        checked={enabled}
        onChange={(e) => {
          setEnabled(e.target.checked);
          persistExplainEnabled(e.target.checked);
        }}
      />
    </div>
  );
}

// Toggle for the default PDF handler: when ON, DNR rules redirect PDF
// navigations to the extension's built-in pdf.js viewer (see
// src/pdf/pdf-handler.ts), so the agent can observe/control PDF reading
// (pagesloaded events, browser_screenshot). Default OFF.
function PdfHandlerToggle() {
  const [enabled, setEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    void loadPdfHandlerEnabled().then(setEnabled);
  }, []);

  if (enabled === null) return null;

  return (
    <div className="flex items-center justify-between">
      <label htmlFor="pdf-handler-toggle" className="text-sm font-medium leading-none">
        默认用 Siada 打开 PDF
        <span className="text-muted-foreground font-normal ml-1.5">PDF 链接在内置 pdf.js 查看器中打开（本地文件需在扩展详情页允许访问文件网址）</span>
      </label>
      <input
        id="pdf-handler-toggle"
        type="checkbox"
        className="h-4 w-4 shrink-0 cursor-pointer accent-primary"
        checked={enabled}
        onChange={(e) => {
          setEnabled(e.target.checked);
          persistPdfHandlerEnabled(e.target.checked);
        }}
      />
    </div>
  );
}

interface ACPConnectProps {
  onClientReady?: (client: ACPClient | null) => void;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
}

export function ACPConnect({ onClientReady, expanded, onExpandedChange }: ACPConnectProps) {
  // Load persisted settings before first render so the shared component
  // initializes with them (and the background worker reads the same values).
  const [initialSettings, setInitialSettings] = useState<Partial<ACPSettings> | null>(null);

  useEffect(() => {
    void loadStoredSettings().then((stored) => setInitialSettings(stored ?? {}));
  }, []);

  if (initialSettings === null) return null;

  return (
    <SharedACPConnect
      onClientReady={onClientReady}
      expanded={expanded}
      onExpandedChange={onExpandedChange}
      browserToolHandler={executeBrowserTool}
      showTokenInput
      autoConnect
      initialSettings={initialSettings}
      onSettingsChange={persistSettings}
      extraSettings={<><ExplainToggle /><PdfHandlerToggle /></>}
    />
  );
}
