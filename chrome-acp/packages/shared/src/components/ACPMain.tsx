import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { FolderOpen, MessageSquare, History, Activity, Play, Square } from "lucide-react";
import { cn } from "../lib/utils";
import type { ACPClient } from "../acp/client";
import type { AgentSessionInfo, LiveViewMode } from "../acp/types";
import { createTraceStore } from "./trace/trace-store";
import type { TraceRun } from "../trace/types";
import { ChatInterface } from "./ChatInterface";
import { FileExplorer } from "./FileExplorer";
import { ThreadHistory } from "./ThreadHistory";
import { TraceView } from "./trace/TraceView";
import { Button } from "./ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";

interface ACPMainProps {
  client: ACPClient;
  /** Passed through to ChatInterface: restore this session on mount
   * (sidepanel close/reopen survival). The optional cwd restores the
   * session's working directory (e.g. for share links). */
  initialSession?: { sessionId: string; cwd?: string } | null;
  /** Passed through to ChatInterface: notified on every active session. */
  onSessionActive?: (sessionId: string) => void;
}

const TAB_ORDER = ["chat", "trace", "history", "files"] as const;
type TabValue = (typeof TAB_ORDER)[number];

/** Match the active-tab lookup used when ChatInterface binds a session. */
async function currentTabId(): Promise<number | undefined> {
  try {
    const api = (globalThis as {
      chrome?: { tabs?: { query?: (query: object) => Promise<{ id?: number }[]> } };
    }).chrome;
    const tabs = await api?.tabs?.query?.({ active: true, currentWindow: true });
    return tabs?.[0]?.id;
  } catch {
    return undefined;
  }
}

/**
 * Main container component that provides tabs for Chat, Trace, History, and
 * File explorer. The Trace tab is the browser-activity viewer: per-step
 * timings come from the ACP stream, pictures from a pluggable frame source.
 * Reference: Zed's AgentPanel with ThreadHistory integration
 * This component should be rendered after successful connection.
 */
export function ACPMain({ client, initialSession, onSessionActive }: ACPMainProps) {
  const [activeTab, setActiveTab] = useState<TabValue>("chat");
  const touchStartX = useRef<number | null>(null);
  const touchStartY = useRef<number | null>(null);
  const tabLookup = useRef(0);

  // Each request owns its trace, with terminal events supplied by ACP.
  const trace = useMemo(
    () => createTraceStore({ model: () => client.modelState?.currentModelId ?? undefined }),
    [client],
  );
  const [run, setRun] = useState<TraceRun>(() => trace.collector.snapshot());

  useEffect(() => trace.collector.subscribe(setRun), [trace]);

  useEffect(() => {
    trace.attach(client);
    return () => {
      tabLookup.current++;
      trace.detach();
    };
  }, [client, trace]);

  // Live view: off until asked for, because streaming attaches a debugger to
  // the user's tab and that should be a deliberate choice.
  const [liveState, setLiveState] = useState<{
    active: boolean;
    error?: string;
    mode?: LiveViewMode;
  }>({ active: false });
  useEffect(() => client.onScreencastState(setLiveState), [client]);
  useEffect(() => () => {
    try { client.setScreencast(false); } catch { /* The connection is already gone. */ }
  }, [client]);

  const toggleLiveView = useCallback(() => {
    try {
      client.setScreencast(!liveState.active);
    } catch (error) {
      setLiveState({
        active: false,
        error: error instanceof Error ? error.message : "live view is unavailable",
      });
    }
  }, [client, liveState.active]);

  // A new session means a new run: otherwise steps from the previous session
  // would keep accumulating into one timeline.
  const handleSessionActiveInternal = useCallback(
    (sessionId: string) => {
      trace.setSession(sessionId);
      const lookup = ++tabLookup.current;
      void currentTabId().then(id => {
        if (lookup === tabLookup.current) trace.setTab(id, sessionId);
      });
      onSessionActive?.(sessionId);
    },
    [trace, onSessionActive],
  );

  // Handle session selection from history
  // Reference: Zed's connection_view.rs line 616-631
  // Zed prioritizes load_session (with history), falls back to resume_session (without history)
  const handleSelectSession = useCallback(async (session: AgentSessionInfo) => {
    try {
      if (client.supportsLoadSession) {
        // load_session replays full history
        await client.loadSession({ sessionId: session.sessionId, cwd: session.cwd });
      } else if (client.supportsResumeSession) {
        // resume_session starts without replaying history
        await client.resumeSession({ sessionId: session.sessionId, cwd: session.cwd });
      } else {
        throw new Error("Loading or resuming sessions is not supported by this agent.");
      }
      // Switch to chat tab after loading
      setActiveTab("chat");
    } catch (error) {
      console.error("Failed to load/resume session:", error);
    }
  }, [client]);

  // Check if an element or its ancestors can scroll horizontally
  const isInHorizontalScrollableArea = useCallback((element: HTMLElement | null): boolean => {
    while (element) {
      if (element.scrollWidth > element.clientWidth) {
        const style = window.getComputedStyle(element);
        const overflowX = style.overflowX;
        if (overflowX === "auto" || overflowX === "scroll") {
          return true;
        }
      }
      element = element.parentElement;
    }
    return false;
  }, []);

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    // Don't track swipe if starting in a horizontally scrollable area
    if (isInHorizontalScrollableArea(e.target as HTMLElement)) {
      touchStartX.current = null;
      touchStartY.current = null;
      return;
    }
    touchStartX.current = e.touches[0].clientX;
    touchStartY.current = e.touches[0].clientY;
  }, [isInHorizontalScrollableArea]);

  const handleTouchEnd = useCallback((e: React.TouchEvent) => {
    if (touchStartX.current === null || touchStartY.current === null) return;

    const deltaX = e.changedTouches[0].clientX - touchStartX.current;
    const deltaY = e.changedTouches[0].clientY - touchStartY.current;

    // Only trigger if horizontal swipe is dominant and significant
    if (Math.abs(deltaX) > 50 && Math.abs(deltaX) > Math.abs(deltaY) * 1.5) {
      const currentIndex = TAB_ORDER.indexOf(activeTab);
      if (deltaX < 0 && currentIndex < TAB_ORDER.length - 1) {
        // Swipe left → next tab
        setActiveTab(TAB_ORDER[currentIndex + 1]);
      } else if (deltaX > 0 && currentIndex > 0) {
        // Swipe right → previous tab
        setActiveTab(TAB_ORDER[currentIndex - 1]);
      }
    }

    touchStartX.current = null;
    touchStartY.current = null;
  }, [activeTab]);

  return (
    <Tabs
      value={activeTab}
      onValueChange={(v) => setActiveTab(v as TabValue)}
      className="flex flex-col h-full w-full"
    >
      <TabsList className="mx-2 mt-2 self-center">
        <TabsTrigger value="chat" className="gap-1.5">
          <MessageSquare className="h-4 w-4" />
          <span>Chat</span>
        </TabsTrigger>
        <TabsTrigger value="trace" className="gap-1.5">
          <Activity className="h-4 w-4" />
          <span>Trace</span>
        </TabsTrigger>
        <TabsTrigger value="history" className="gap-1.5">
          <History className="h-4 w-4" />
          <span>History</span>
        </TabsTrigger>
        <TabsTrigger value="files" className="gap-1.5">
          <FolderOpen className="h-4 w-4" />
          <span>Files</span>
        </TabsTrigger>
      </TabsList>

      <div
        className="flex-1 flex flex-col min-h-0 overflow-hidden"
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
      >
        <TabsContent value="chat" forceMount className="w-full h-full m-0 max-w-2xl mx-auto">
          <ChatInterface client={client} initialSession={initialSession} onSessionActive={handleSessionActiveInternal} />
        </TabsContent>

        <TabsContent value="trace" forceMount className="w-full h-full m-0 flex flex-col overflow-hidden">
          <div className="flex items-center gap-2 border-b px-3 py-1.5">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Browser activity
            </span>
            <span
              className={cn(
                "ml-auto truncate text-[11px]",
                liveState.error ? "text-amber-600" : "text-muted-foreground",
              )}
            >
              {liveState.error
                ? liveState.error
                : liveState.active
                  ? liveState.mode === "screenshots"
                    ? "live · polling"
                    : "live"
                  : "snapshots only"}
            </span>
            <Button
              type="button"
              size="sm"
              variant={liveState.active ? "secondary" : "outline"}
              className="h-6 gap-1 px-2 text-[11px]"
              onClick={toggleLiveView}
            >
              {liveState.active ? (
                <Square className="size-3" />
              ) : (
                <Play className="size-3" />
              )}
              {liveState.active ? "Stop live" : "Go live"}
            </Button>
          </div>
          <TraceView
            run={run}
            frameSource={trace.frames}
            onPageChange={trace.reportPageChange}
            className="min-h-0 flex-1"
            placeholder="Frames appear here as the agent acts. Timings come from the trace, not from the picture."
          />
        </TabsContent>

        <TabsContent value="history" forceMount className="flex flex-col h-full m-0 max-w-2xl mx-auto w-full">
          <ThreadHistory client={client} onSelectSession={handleSelectSession} />
        </TabsContent>

        <TabsContent value="files" forceMount className="flex flex-col h-full m-0">
          <FileExplorer client={client} />
        </TabsContent>
      </div>
    </Tabs>
  );
}
