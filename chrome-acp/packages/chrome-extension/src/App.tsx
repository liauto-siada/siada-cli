import { useCallback, useEffect, useState } from "react";
import { ACPConnect } from "@/components/ACPConnect";
import { ACPMain } from "@chrome-acp/shared/components";
import { ThemeProvider } from "@chrome-acp/shared/lib";
import type { ACPClient } from "@chrome-acp/shared/acp";
import "./index.css";

// Persisted "last session" so the sidepanel survives close/reopen: the proxy
// kills the agent process when the panel's WS closes, and without this the
// reopened panel would silently start a brand-new session.
const LAST_SESSION_KEY = "sidepanel_last_session";

export function App() {
  const [client, setClient] = useState<ACPClient | null>(null);
  const [expanded, setExpanded] = useState(true);
  // undefined = not yet read from storage; null = no previous session
  const [lastSession, setLastSession] = useState<{ sessionId: string } | null | undefined>(undefined);
  // Auto-connect restores the last session; a MANUAL Connect click means the
  // user explicitly wants a connection — start a fresh session instead.
  const [restoreLastSession, setRestoreLastSession] = useState(true);

  useEffect(() => {
    chrome.storage.local
      .get(LAST_SESSION_KEY)
      .then((stored) => setLastSession(stored[LAST_SESSION_KEY] ?? null))
      .catch(() => setLastSession(null));
  }, []);

  const handleSessionActive = useCallback((sessionId: string) => {
    chrome.storage.local.set({ [LAST_SESSION_KEY]: { sessionId } }).catch(() => {});
  }, []);

  const handleConnectInitiated = useCallback((source: "auto" | "manual") => {
    if (source === "manual") setRestoreLastSession(false);
  }, []);

  const initialSession = restoreLastSession ? lastSession : null;

  return (
    <ThemeProvider>
      <div className="flex flex-col h-dvh w-full">
        {/* Unified Connection Bar */}
        <ACPConnect
          onClientReady={setClient}
          expanded={expanded}
          onExpandedChange={setExpanded}
          onConnectInitiated={handleConnectInitiated}
        />

        {/* Main Content — wait for the storage read before mounting ACPMain,
            or ChatInterface would create a new session before we can restore. */}
        <main className="flex-1 overflow-hidden">
          {client && initialSession !== undefined ? (
            <ACPMain
              client={client}
              initialSession={initialSession}
              onSessionActive={handleSessionActive}
            />
          ) : client ? null : (
            <div className="flex items-center justify-center h-full text-muted-foreground p-4">
              <div className="text-center">
                <p className="text-lg mb-2">No agent connected</p>
                <p className="text-sm">Click the status bar above to configure connection</p>
              </div>
            </div>
          )}
        </main>
      </div>
    </ThemeProvider>
  );
}

export default App;
