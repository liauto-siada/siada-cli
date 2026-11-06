import { useCallback, useEffect, useState } from "react";
import { ACPConnect, type StartupState } from "@/components/ACPConnect";
import { ACPMain, DisplaySettingsProvider } from "@chrome-acp/shared/components";
import { ThemeProvider } from "@chrome-acp/shared/lib";
import type { ACPClient } from "@chrome-acp/shared/acp";
import "./index.css";
import { loadSidepanelIdentity } from "./sidepanel-identity";

// Window-scoped identity reattaches to a retained agent; persisted session
// history also survives the retention timeout or a proxy restart.
export function App() {
  const [client, setClient] = useState<ACPClient | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [connecting, setConnecting] = useState(true);
  const [startupState, setStartupState] = useState<StartupState>("checking");
  // undefined = not yet read from storage; null = no previous session
  const [lastSession, setLastSession] = useState<{ sessionId: string } | null | undefined>(undefined);
  // Auto-connect restores the last session; a MANUAL Connect click means the
  // user explicitly wants a connection — start a fresh session instead.
  const [restoreLastSession, setRestoreLastSession] = useState(true);
  const [identity, setIdentity] = useState<Awaited<ReturnType<typeof loadSidepanelIdentity>> | null>(null);
  const [identityAttempt, setIdentityAttempt] = useState(0);
  const [identityError, setIdentityError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setIdentityError(null);
    void loadSidepanelIdentity().then((value) => {
      if (!active) return;
      setIdentity(value);
      setLastSession(value.lastSession);
    }).catch((error: unknown) => {
      if (active) setIdentityError(error instanceof Error ? error.message : String(error));
    });
    return () => { active = false; };
  }, [identityAttempt]);

  const handleSessionActive = useCallback((sessionId: string) => {
    if (identity) chrome.storage.local.set({ [identity.lastSessionKey]: { sessionId } }).catch(() => {});
  }, [identity]);

  const handleConnectInitiated = useCallback((source: "auto" | "manual") => {
    if (source === "manual") setRestoreLastSession(false);
  }, []);

  const initialSession = restoreLastSession ? lastSession : null;

  return (
    <ThemeProvider>
      <DisplaySettingsProvider>
      <div className="flex flex-col h-dvh w-full">
        {/* Unified Connection Bar */}
        {identity ? <ACPConnect
          retentionId={identity.retentionId}
          onStartupStateChange={setStartupState}
          onClientReady={setClient}
          onConnectingChange={setConnecting}
          expanded={expanded}
          onExpandedChange={setExpanded}
          onConnectInitiated={handleConnectInitiated}
        /> : <div role="status" className="flex flex-1 items-center justify-center text-muted-foreground">
          {identityError ? <div>无法准备 Siada：{identityError}<button className="ml-2 underline" onClick={() => setIdentityAttempt(n => n + 1)}>重试</button></div> : "正在准备 Siada…"}
        </div>}

        {/* Main Content — wait for the storage read before mounting ACPMain,
            or ChatInterface would create a new session before we can restore. */}
        {startupState === "connection" && <main className="flex-1 overflow-hidden">
          {client && initialSession !== undefined ? (
            <ACPMain
              client={client}
              initialSession={initialSession}
              onSessionActive={handleSessionActive}
            />
          ) : client ? null : (
            <div className="flex items-center justify-center h-full text-muted-foreground p-4">
              <div className="text-center">
                <p className="text-lg mb-2">{connecting ? "正在连接 Siada…" : "尚未连接 Siada"}</p>
                <p className="text-sm">{connecting ? "正在启动本机助手，请稍候。" : "请在上方查看连接状态。"}</p>
              </div>
            </div>
          )}
        </main>}
      </div>
      </DisplaySettingsProvider>
    </ThemeProvider>
  );
}

export default App;
