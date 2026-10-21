// Re-export from shared with browser tool handler configured
import { useEffect, useState } from "react";
import { ACPConnect as SharedACPConnect } from "@chrome-acp/shared/components";
import { executeBrowserTool } from "@/tools/browser";
import type { ACPClient, ACPSettings } from "@chrome-acp/shared/acp";
import { loadStoredSettings, persistSettings, resolveProxySettings, ACP_SETTINGS_KEY, loadExplainEnabled, persistExplainEnabled, loadPdfHandlerEnabled, persistPdfHandlerEnabled } from "@/settings";
import { discoverLocalSettings, localBootstrapUrl } from "../local-bootstrap";
import { InstallGuide } from "./InstallGuide";
import { BrowserLogin } from "../../../shared/src/components/BrowserLogin";

export type StartupState = "checking" | "install" | "login" | "connection";

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
    <div className="flex items-start justify-between gap-3">
      <label htmlFor="explain-toggle" className="text-sm font-medium leading-none">
        划词解释
        <span className="mt-1.5 block text-xs leading-5 text-muted-foreground font-normal">选中文字后显示「✨ 解释」按钮</span>
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
    <div className="flex items-start justify-between gap-3">
      <label htmlFor="pdf-handler-toggle" className="text-sm font-medium leading-none">
        默认用 Siada 打开 PDF
        <span className="mt-1.5 block text-xs leading-5 text-muted-foreground font-normal">在内置阅读器打开 PDF。本地文件需在扩展设置中允许访问文件网址。</span>
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
  onStartupStateChange?: (state: StartupState) => void;
  onClientReady?: (client: ACPClient | null) => void;
  onConnectingChange?: (connecting: boolean) => void;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
  onConnectInitiated?: (source: "auto" | "manual") => void;
}

export function ACPConnect({ onClientReady, onConnectingChange, expanded, onExpandedChange, onConnectInitiated, onStartupStateChange }: ACPConnectProps) {
  // Load persisted settings before first render so the shared component
  // initializes with them (and the background worker reads the same values).
  const [initialSettings, setInitialSettings] = useState<Partial<ACPSettings> | null>(null);
  const [connectionKey, setConnectionKey] = useState(0);
  const [localUnavailable, setLocalUnavailable] = useState(false);
  const [loginRequired, setLoginRequired] = useState(false);
  const [loginEndpoint, setLoginEndpoint] = useState("");
  const [manualConnection, setManualConnection] = useState(false);
  const [discoveryComplete, setDiscoveryComplete] = useState(false);
  const [reconfigure, setReconfigure] = useState(false);
  const [discoveryKey, setDiscoveryKey] = useState(0);

  const startupState: StartupState = reconfigure ? "login" : manualConnection ? "connection"
    : loginRequired ? "login" : !discoveryComplete ? "checking"
    : localUnavailable ? "install" : "connection";
  useEffect(() => { onStartupStateChange?.(startupState); }, [startupState, onStartupStateChange]);

  useEffect(() => {
    let active = true;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const discover = async (first: boolean) => {
      const settings = resolveProxySettings(await loadStoredSettings());
      let result = await discoverLocalSettings(settings, chrome.runtime.id);
      if (!active) return;
      if (result && "loginRequired" in result) {
        if (result && "loginRequired" in result) {
          setLoginEndpoint(localBootstrapUrl(settings.proxyUrl)!);
          setLoginRequired(true);
          setDiscoveryComplete(true);
          setLocalUnavailable(false);
          retry = setTimeout(() => void discover(first), 5000);
          return;
        }
      }
      // Do not overwrite edits made while the request was in flight.
      const latest = resolveProxySettings(await loadStoredSettings());
      if (!active) return;
      if (latest.proxyUrl !== settings.proxyUrl || latest.token !== settings.token) {
        retry = setTimeout(() => void discover(first), 1000);
        return;
      }
      if (result) {
        if ("loginRequired" in result) return;
        await chrome.storage.local.set({ [ACP_SETTINGS_KEY]: result });
        if (!active) return;
        setInitialSettings(result);
        if (!first) setConnectionKey((value) => value + 1);
        setLocalUnavailable(false);
        setLoginRequired(false);
      } else {
        setLoginRequired(false);
        if (first) setInitialSettings(settings);
        const local = localBootstrapUrl(settings.proxyUrl) !== null;
        setLocalUnavailable(local);
        if (local) retry = setTimeout(() => void discover(false), 5000);
      }
      setDiscoveryComplete(true);
    };
    void discover(true);
    return () => { active = false; clearTimeout(retry); };
  }, [discoveryKey]);

  return (
    <>
    {startupState === "login" && <BrowserLogin endpoint={loginEndpoint} extensionId={chrome.runtime.id} icon={chrome.runtime.getURL("icons/icon128.png")} reconfigure={reconfigure}
      onComplete={() => { setReconfigure(false); setLoginRequired(false); setManualConnection(false); setConnectionKey(n => n + 1); setDiscoveryKey(n => n + 1); }}
      onCancel={() => { if (reconfigure) { setReconfigure(false); setConnectionKey(n => n + 1); } else { setManualConnection(true); onExpandedChange(true); } }} />}
    {startupState === "checking" && <div role="status" className="flex flex-1 items-center justify-center text-muted-foreground">正在检测本机 Siada…</div>}
    {startupState === "install" && <InstallGuide onConnect={() => { setManualConnection(true); onExpandedChange(true); }} />}
    {startupState === "connection" && initialSettings !== null && <SharedACPConnect
      key={connectionKey}
      onClientReady={onClientReady}
      onConnectingChange={onConnectingChange}
      expanded={expanded}
      onExpandedChange={onExpandedChange}
      onConnectInitiated={onConnectInitiated}
      browserToolHandler={executeBrowserTool}
      showTokenInput
      autoConnect
      initialSettings={initialSettings}
      onSettingsChange={persistSettings}
      extraSettings={<div className="space-y-4 border-t pt-4">
        {localBootstrapUrl(initialSettings.proxyUrl ?? "") && <button type="button" className="w-full rounded-lg border px-3 py-2.5 text-sm font-medium hover:bg-muted"
          onClick={() => { setLoginEndpoint(localBootstrapUrl(initialSettings.proxyUrl!)!); setReconfigure(true); onClientReady?.(null); }}>
          重新登录 / 切换模型服务
        </button>}
        <ExplainToggle /><PdfHandlerToggle />
      </div>}
    />}
    </>
  );
}
