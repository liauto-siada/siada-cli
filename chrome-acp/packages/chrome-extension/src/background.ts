// Open side panel when the extension icon is clicked
chrome.action.onClicked.addListener((tab) => {
  if (tab.id) {
    chrome.sidePanel.open({ tabId: tab.id });
  }
});

// ============================================================================
// Trajectory forwarding
// ============================================================================
// Receives recorded events from content scripts (one port per tab), tags them
// with the tab id, and forwards them to the proxy-server over a dedicated
// WebSocket (/ws/trajectory). While the proxy is unreachable, events are
// buffered in chrome.storage.local and flushed on reconnect.

import { ACPClient, DEFAULT_SETTINGS, type ACPSettings, type SessionUpdate, type TrajectoryEvent } from "@chrome-acp/shared/acp";
import {
  ACP_SETTINGS_KEY,
  flipLoopbackWsScheme,
  loadStoredSettings,
  resolveProxySettings,
  trajectoryWsUrlFor,
} from "./settings";
import { executeBrowserTool } from "./tools/browser";
import {
  createScreencast,
  createScreenshotPolling,
  type LiveViewState,
  type ScreencastSession,
  type ScreencastTarget,
} from "./screencast/screencast";
// Self-wiring module: applies the persisted default-PDF-handler toggle
// (DNR redirect rules) at startup and follows storage changes.
import "./pdf/pdf-handler";

const TRAJECTORY_BUFFER_KEY = "trajectory_buffer";
const STORAGE_BUFFER_CAP = 5000; // drop oldest beyond this
const WS_RECONNECT_BASE_MS = 2000;
const WS_RECONNECT_MAX_MS = 60_000;

let ws: WebSocket | null = null;
let wsReconnectDelay = WS_RECONNECT_BASE_MS;
// URL that last reached onopen, remembered for the worker's lifetime: when
// a loopback scheme flip was needed (Chrome rejects the self-signed cert
// for wss://localhost), later reconnects reuse the working scheme instead
// of re-failing first.
let wsWorkingUrl: string | null = null;
// Serialize read-modify-write cycles on the storage buffer
let bufferChain: Promise<void> = Promise.resolve();

// Resolve the trajectory endpoint from the same persisted settings as the
// tool channel (not the hardcoded default) so remote deployments where the
// user overrides proxyUrl keep receiving trajectory events.
async function trajectoryWsUrl(): Promise<string> {
  const stored = await loadStoredSettings();
  const settings = resolveProxySettings(stored);
  // The trajectory endpoint sits behind the same token gate as /ws; carry the
  // token the user configured for the tool channel or the proxy refuses us.
  return trajectoryWsUrlFor(settings.proxyUrl, settings.token);
}

async function connectWs(urlOverride?: string) {
  let socket: WebSocket;
  try {
    socket = new WebSocket(urlOverride ?? wsWorkingUrl ?? (await trajectoryWsUrl()));
  } catch {
    ws = null;
    scheduleWsReconnect();
    return;
  }
  ws = socket;
  let opened = false;

  socket.onopen = () => {
    opened = true;
    wsWorkingUrl = socket.url;
    wsReconnectDelay = WS_RECONNECT_BASE_MS;
    void flushBuffer();
  };
  socket.onclose = () => {
    if (ws === socket) ws = null;
    // A loopback socket that never opened is a scheme mismatch (the proxy's
    // dual-protocol listener serves plaintext ws to loopback peers even in
    // --https mode). Retry once with the flipped scheme before the backoff
    // reconnect — mirrors ACPClient.connect().
    if (!opened && !urlOverride) {
      const flipped = flipLoopbackWsScheme(socket.url);
      if (flipped) {
        void connectWs(flipped);
        return;
      }
      // The remembered URL stopped working; recompute from settings.
      wsWorkingUrl = null;
    }
    scheduleWsReconnect();
  };
  socket.onerror = () => {
    socket.close();
  };
  // Receiving messages resets the service worker's idle timer; without a
  // listener the proxy's app-level heartbeat cannot keep this worker alive.
  socket.onmessage = () => {};
}

function scheduleWsReconnect() {
  setTimeout(() => void connectWs(), wsReconnectDelay);
  wsReconnectDelay = Math.min(wsReconnectDelay * 2, WS_RECONNECT_MAX_MS);
}

function persistBuffer(events: TrajectoryEvent[]): Promise<void> {
  bufferChain = bufferChain.then(async () => {
    const stored = await chrome.storage.local.get(TRAJECTORY_BUFFER_KEY);
    const existing =
      (stored[TRAJECTORY_BUFFER_KEY] as TrajectoryEvent[] | undefined) ?? [];
    const merged = [...existing, ...events].slice(-STORAGE_BUFFER_CAP);
    await chrome.storage.local.set({ [TRAJECTORY_BUFFER_KEY]: merged });
  });
  return bufferChain;
}

async function flushBuffer(): Promise<void> {
  const stored = await chrome.storage.local.get(TRAJECTORY_BUFFER_KEY);
  const buffered =
    (stored[TRAJECTORY_BUFFER_KEY] as TrajectoryEvent[] | undefined) ?? [];
  if (buffered.length === 0) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  ws.send(JSON.stringify({ type: "trajectory_events", payload: buffered }));
  await chrome.storage.local.remove(TRAJECTORY_BUFFER_KEY);
}

function forwardEvents(events: TrajectoryEvent[]) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    console.log(
      `[STEP 5] background -> proxy WebSocket: ${events.length} event(s)`,
    );
    ws.send(JSON.stringify({ type: "trajectory_events", payload: events }));
  } else {
    console.log(
      `[STEP 5] proxy WS not open; buffering ${events.length} event(s) locally`,
    );
    void persistBuffer(events);
  }
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name === "explain") {
    handleExplainPort(port);
    return;
  }
  if (port.name !== "trajectory") return;
  const tabId = port.sender?.tab?.id;

  port.onMessage.addListener((message: { events?: TrajectoryEvent[]; type?: string }) => {
    // Health-check handshake: the recorder probes the port because an MV3 port
    // created during SW cold-start can silently drop messages.
    if (message?.type === "ping") {
      try {
        port.postMessage({ type: "pong" });
      } catch {
        // port is going away; the content script will reconnect
      }
      return;
    }
    if (!Array.isArray(message.events)) return;
    const events = message.events;
    if (tabId !== undefined) {
      for (const event of events) event.tabId = tabId;
    }
    console.log(
      `[STEP 4] background received ${events.length} event(s) from tab ${tabId}`,
    );
    forwardEvents(events);
  });
});

void connectWs();

// ============================================================================
// Browser tool execution channel
// ============================================================================
// A dedicated tool-only WebSocket (announced via `register_executor`) so
// browser tools keep working while no sidepanel is open. Unlike the
// sidepanel's ACPClient, this connection never sends "connect" — the proxy
// must not spawn an agent for it. Reuses the trajectory channel's
// reconnect/backoff pattern; the proxy's 30s heartbeat keeps the service
// worker alive while connected.

let toolWs: WebSocket | null = null;
let toolWsReconnectDelay = WS_RECONNECT_BASE_MS;
// Same remembered-working-URL scheme fallback as the trajectory channel.
let toolWsWorkingUrl: string | null = null;

// Browser actions that change the page, and therefore deserve a picture in the
// activity viewer. `read`/`tabs`/`paragraphs` leave the page alone.
const MUTATING_ACTIONS = new Set(["execute", "replay"]);

/**
 * Capture the controlled page's content area.
 *
 * `captureVisibleTab` only sees the active tab of a window, so a mutation that
 * happened on a background tab returns null rather than a mislabelled picture.
 * Lifting that restriction is what a CDP screencast frame source is for.
 */
async function captureFrame(
  tabId: number,
  phase: "before" | "after",
): Promise<{
  dataUrl: string;
  width: number;
  height: number;
  tsMs: number;
  phase: "before" | "after";
  url?: string;
  title?: string;
} | null> {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!tab.active) return null;
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
      format: "jpeg",
      quality: 60,
    });
    return {
      dataUrl,
      width: tab.width ?? 0,
      height: tab.height ?? 0,
      tsMs: Date.now(),
      phase,
      url: tab.url,
      title: tab.title,
    };
  } catch (error) {
    // Never let a failed capture affect tool execution.
    console.log("[frame] capture skipped:", (error as Error).message);
    return null;
  }
}

// ============================================================================
// Live view (CDP screencast via chrome.debugger)
// ============================================================================
// Started on demand by the proxy when a viewer asks for it, stopped when that
// viewer goes away or the tab detaches. Only one stream exists at a time: a
// second viewer reuses the running one rather than attaching twice (Chrome
// refuses two debuggers on one tab).

let liveView: {
  session: ScreencastSession;
  tabId: number;
  socket: WebSocket;
} | null = null;
// Tabs this worker attached, so teardown never detaches someone else's
// debugger session (another extension or DevTools).
const attachedTabs = new Set<number>();

// Starting and stopping a stream are each a pair of async Chrome API calls, so
// two overlapping requests can interleave (stop during attach, two starts) and
// leave a stream running that nothing references any more. Requests are run one
// after another instead; the sessions themselves also abort a start that is
// stopped mid-flight, for the paths that do not go through this queue.
let liveViewQueue: Promise<unknown> = Promise.resolve();
function queueLiveViewRequest(task: () => Promise<void>): void {
  liveViewQueue = liveViewQueue
    .then(task, task)
    .catch((error) => console.warn("[live-view] request failed:", error));
}

function debuggerTarget(tabId: number): ScreencastTarget {
  const target = { tabId };
  let unsubscribe: (() => void) | null = null;
  return {
    attach: async () => {
      await chrome.debugger.attach(target, "1.3");
      attachedTabs.add(tabId);
    },
    detach: async () => {
      attachedTabs.delete(tabId);
      await chrome.debugger.detach(target);
    },
    isAttached: () => attachedTabs.has(tabId),
    sendCommand: (method, params) =>
      chrome.debugger.sendCommand(target, method, params),
    onEvent: (listener) => {
      const handler = (
        source: chrome.debugger.Debuggee,
        method: string,
        params?: object,
      ) => {
        if (source.tabId !== tabId) return;
        listener(method, (params ?? {}) as Record<string, unknown>);
      };
      chrome.debugger.onEvent.addListener(handler);
      unsubscribe = () => chrome.debugger.onEvent.removeListener(handler);
      return () => {
        unsubscribe?.();
        unsubscribe = null;
      };
    },
  };
}

/**
 * Send a tab-scoped message over the tool channel. The proxy routes pictures
 * and live-view state by the tab they belong to and drops untagged ones, so
 * every frame/state send must name its tab here.
 */
function sendTabMessage(socket: WebSocket, tabId: number, message: object): void {
  if (socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ ...message, tabId }));
}

function sendScreencastState(socket: WebSocket, tabId: number, state: LiveViewState): void {
  sendTabMessage(socket, tabId, { type: "screencast_state", payload: state });
}

/** Stop the running stream, if any. `session.stop()` reports the state change. */
async function stopLiveView(): Promise<void> {
  const current = liveView;
  if (!current) return;
  liveView = null;
  await current.session.stop();
}

async function handleScreencastRequest(
  socket: WebSocket,
  payload: { enabled?: boolean; tabId?: number },
): Promise<void> {
  const requestedTabId = typeof payload.tabId === "number" ? payload.tabId : undefined;

  if (!payload.enabled) {
    // A stop names the tab it stops: a viewer disconnecting from another tab
    // must not kill the user's running stream. The proxy always sends the tab
    // it had bound; a legacy stop without one falls back to the single stream.
    if (liveView && requestedTabId !== undefined && liveView.tabId !== requestedTabId) {
      sendScreencastState(socket, requestedTabId, { active: false });
      return;
    }
    if (!liveView) {
      if (requestedTabId !== undefined) {
        sendScreencastState(socket, requestedTabId, { active: false });
      }
      return;
    }
    await stopLiveView();
    return;
  }

  const tabId = requestedTabId;
  if (tabId === undefined) {
    // The proxy answers a start without a bound tab itself and never forwards
    // one, and a state message without a tab could not be routed back anyway.
    console.warn("[live-view] start request without a tab was ignored");
    return;
  }

  if (liveView?.tabId === tabId && liveView.session.isActive()) {
    sendScreencastState(socket, tabId, { active: true });
    return;
  }

  await stopLiveView();

  // Pick the mode by how Chrome will treat the tab. A visible tab streams
  // (screencast); a tab the user is not looking at is not composited, so
  // `Page.startScreencast` would emit one frame and stop — poll screenshots
  // instead, which has no such restriction.
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  const options = {
    // Keep the payload small: the viewer is a monitor, not a video player.
    quality: 60,
    maxWidth: 1280,
    onFrame: (frame: { dataUrl: string; width: number; height: number; tsMs: number }) => {
      sendTabMessage(socket, tabId, { type: "frame", payload: frame });
    },
    onState: (state: LiveViewState) => sendScreencastState(socket, tabId, state),
  };
  const session = tab?.active
    ? createScreencast(debuggerTarget(tabId), options)
    : createScreenshotPolling(debuggerTarget(tabId), options);

  liveView = { session, tabId, socket };
  await session.start();

  // start() already reported the failure and detached; just drop the handle —
  // unless a later request replaced it in the meantime, in which case dropping
  // it would leave that running stream with nobody able to stop it.
  if (!session.isActive() && liveView?.session === session) liveView = null;
}

// Chrome detaches on its own when a tab closes or navigates in some cases;
// mirror that into the live view so the UI stops believing it is streaming.
chrome.debugger.onDetach.addListener((source) => {
  if (source.tabId === undefined) return;
  attachedTabs.delete(source.tabId);
  if (liveView?.tabId === source.tabId) void stopLiveView();
});

function scheduleToolWsReconnect() {
  setTimeout(() => void connectToolWs(), toolWsReconnectDelay);
  toolWsReconnectDelay = Math.min(toolWsReconnectDelay * 2, WS_RECONNECT_MAX_MS);
}

async function connectToolWs(urlOverride?: string): Promise<void> {
  let url = urlOverride ?? toolWsWorkingUrl;
  if (!url) {
    const stored = await loadStoredSettings();
    const settings = resolveProxySettings(stored);
    const parsed = new URL(settings.proxyUrl);
    if (settings.token) parsed.searchParams.set("token", settings.token);
    url = parsed.toString();
  }

  let socket: WebSocket;
  try {
    socket = new WebSocket(url);
  } catch {
    toolWs = null;
    scheduleToolWsReconnect();
    return;
  }
  toolWs = socket;
  let opened = false;

  socket.onopen = () => {
    opened = true;
    toolWsWorkingUrl = socket.url;
    toolWsReconnectDelay = WS_RECONNECT_BASE_MS;
    socket.send(JSON.stringify({ type: "register_executor" }));
  };

  socket.onmessage = (event: MessageEvent) => {
    void (async () => {
      let msg: {
        type?: string;
        callId?: string;
        params?: unknown;
        payload?: { enabled?: boolean; tabId?: number };
      };
      try {
        msg = JSON.parse(String(event.data));
      } catch {
        return;
      }
      // Reply to the proxy's app-level heartbeat: every message delivered
      // here resets this service worker's 30s idle timer, keeping the tool
      // channel (and the trajectory channel below) permanently connected.
      if (msg.type === "ping") {
        socket.send(JSON.stringify({ type: "pong" }));
        return;
      }
      if (msg.type === "screencast") {
        queueLiveViewRequest(() => handleScreencastRequest(socket, msg.payload ?? {}));
        return;
      }
      if (msg.type !== "browser_tool_call" || msg.callId === undefined) return;

      const params = msg.params as Parameters<typeof executeBrowserTool>[0];
      const watchPage = params.tabId !== undefined && MUTATING_ACTIONS.has(params.action);
      // Take the "before" picture up front: the change overlay is produced by
      // diffing it against the picture taken once the action has run.
      const beforeFrame = watchPage ? await captureFrame(params.tabId!, "before") : null;

      let result: unknown;
      try {
        result = await executeBrowserTool(params);
      } catch (error) {
        result = { error: (error as Error).message };
      }
      socket.send(JSON.stringify({ type: "browser_tool_result", callId: msg.callId, result }));

      // Frames go to the UI, the tool result goes to the agent; they are sent
      // separately for that reason. Each frame is tagged with the tab the tool
      // ran in, so the proxy hands it to that tab's client only.
      if (beforeFrame) {
        sendTabMessage(socket, params.tabId!, {
          type: "frame",
          callId: msg.callId,
          payload: beforeFrame,
        });
      }
      if (watchPage) {
        const afterFrame = await captureFrame(params.tabId!, "after");
        if (afterFrame) {
          sendTabMessage(socket, params.tabId!, {
            type: "frame",
            callId: msg.callId,
            payload: afterFrame,
          });
        }
      }
    })();
  };

  socket.onclose = () => {
    if (toolWs === socket) toolWs = null;
    // The proxy can only tell us to stop while its socket is alive; if this
    // channel drops first, clean up here so the user's tab is not left with a
    // debugger attached and nothing watching.
    if (liveView?.socket === socket) void stopLiveView();
    if (!opened && !urlOverride) {
      const flipped = flipLoopbackWsScheme(socket.url);
      if (flipped) {
        void connectToolWs(flipped);
        return;
      }
      toolWsWorkingUrl = null;
    }
    scheduleToolWsReconnect();
  };
  socket.onerror = () => {
    socket.close();
  };
}

void connectToolWs();

// Belt-and-suspenders keepalive: if the proxy was down (or restarted) while
// this worker slept, the app-level heartbeat obviously couldn't reach us.
// The alarm wakes the worker at most 30s later, top-level code re-runs, and
// both channels reconnect with their base backoff.
chrome.alarms.create("browser-addon-keepalive", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== "browser-addon-keepalive") return;
  if (!toolWs || toolWs.readyState !== WebSocket.OPEN) {
    toolWsReconnectDelay = WS_RECONNECT_BASE_MS;
    void connectToolWs();
  }
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    wsReconnectDelay = WS_RECONNECT_BASE_MS;
    void connectWs();
  }
});

// Reconnect both channels when the sidepanel persists new proxy settings:
// closing the sockets triggers onclose, which schedules a reconnect with the
// base backoff, so the freshly persisted settings take effect immediately.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local" || !(ACP_SETTINGS_KEY in changes)) return;
  toolWsReconnectDelay = WS_RECONNECT_BASE_MS;
  toolWsWorkingUrl = null;
  try {
    toolWs?.close();
  } catch {
    // already closed
  }
  wsReconnectDelay = WS_RECONNECT_BASE_MS;
  wsWorkingUrl = null;
  try {
    ws?.close();
  } catch {
    // already closed
  }
});

// ============================================================================
// Immersive explain
// ============================================================================
// Content scripts connect over a long-lived port named "explain" and send
// the user's text selection to be explained. The background worker keeps its
// own ACP connection (independent from the sidepanel's) with a dedicated
// session, and streams the agent's reply chunks back into the page.
// The sidepanel persists the effective proxy settings to chrome.storage.local
// so this connection reaches the same proxy even while the panel is closed.

interface ExplainRequestMessage {
  kind: "explain";
  requestId: string;
  text: string;
  url: string;
  title: string;
}

interface ExplainCancelMessage {
  kind: "cancel";
  requestId: string;
}

type ExplainPortMessage =
  | { kind: "chunk"; requestId: string; text: string }
  | { kind: "done"; requestId: string; stopReason: string }
  | { kind: "error"; requestId: string; message: string };

let explainClient: ACPClient | null = null;
let explainSessionPromise: Promise<void> | null = null;
let sessionCreatedResolve: (() => void) | null = null;
let explainActivePort: chrome.runtime.Port | null = null;
let explainActiveRequestId: string | null = null;

function postExplain(message: ExplainPortMessage) {
  try {
    explainActivePort?.postMessage(message);
  } catch {
    // Port already gone
  }
}

async function getExplainClient(): Promise<ACPClient> {
  const stored = await loadStoredSettings();
  const settings: ACPSettings = { ...DEFAULT_SETTINGS, ...stored };

  if (!explainClient) {
    explainClient = new ACPClient(settings);

    explainClient.setSessionUpdateHandler((_sessionId: string, update: SessionUpdate) => {
      if (update.sessionUpdate !== "agent_message_chunk") return;
      const text =
        update.content.type === "text" && update.content.text ? update.content.text : "";
      if (text && explainActiveRequestId) {
        postExplain({ kind: "chunk", requestId: explainActiveRequestId, text });
      }
    });

    explainClient.setPromptCompleteHandler((stopReason) => {
      if (explainActiveRequestId) {
        postExplain({ kind: "done", requestId: explainActiveRequestId, stopReason });
      }
    });

    // Explanation prompts are self-contained; never let this session run
    // tools - auto-cancel any permission request.
    explainClient.setPermissionRequestHandler((request) => {
      explainClient?.respondToPermission(request.requestId, null);
    });

    // Surface agent-side failures (e.g. model errors) in the explain card
    explainClient.setErrorHandler((message) => {
      if (explainActiveRequestId) {
        postExplain({ kind: "error", requestId: explainActiveRequestId, message });
      }
    });

    explainClient.setSessionCreatedHandler(() => {
      sessionCreatedResolve?.();
      sessionCreatedResolve = null;
    });

    // Reset session state if the connection drops so the next request
    // reconnects and creates a fresh session.
    explainClient.setConnectionStateHandler((state) => {
      if (state === "disconnected" || state === "error") {
        explainSessionPromise = null;
      }
    });
  } else {
    explainClient.updateSettings(settings);
  }

  if (explainClient.getState() !== "connected") {
    await explainClient.connect();
  }
  return explainClient;
}

function ensureExplainSession(client: ACPClient): Promise<void> {
  if (!explainSessionPromise) {
    explainSessionPromise = new Promise<void>((resolve, reject) => {
      sessionCreatedResolve = resolve;
      setTimeout(() => {
        if (sessionCreatedResolve === resolve) {
          sessionCreatedResolve = null;
          explainSessionPromise = null;
          reject(new Error("Timed out creating explain session"));
        }
      }, 30_000);
      try {
        client.createSession();
      } catch (error) {
        sessionCreatedResolve = null;
        explainSessionPromise = null;
        reject(error);
      }
    });
  }
  return explainSessionPromise;
}

async function handleExplainRequest(
  port: chrome.runtime.Port,
  request: ExplainRequestMessage,
) {
  // A new request supersedes any in-flight explanation
  if (explainClient && explainActiveRequestId) {
    try {
      explainClient.cancel();
    } catch {
      // Not connected
    }
  }
  explainActivePort = port;
  explainActiveRequestId = request.requestId;

  try {
    const client = await getExplainClient();
    await ensureExplainSession(client);

    const prompt = [
      "以下是从网页中选中的一段内容，请用简洁明了的语言解释它。",
      "如果选中文本主要是中文，请用中文回答；否则用该文本的主要语言回答。",
      "直接给出解释，不要调用任何工具。",
      "",
      `页面：${request.title} (${request.url})`,
      "",
      "选中内容：",
      request.text,
    ].join("\n");

    await client.sendPrompt(prompt);
  } catch (error) {
    if (explainActiveRequestId === request.requestId) {
      postExplain({
        kind: "error",
        requestId: request.requestId,
        message: (error as Error).message,
      });
    }
  }
}

function handleExplainPort(port: chrome.runtime.Port) {
  port.onMessage.addListener(
    (message: ExplainRequestMessage | ExplainCancelMessage) => {
      if (message.kind === "explain") {
        void handleExplainRequest(port, message);
      } else if (message.kind === "cancel") {
        if (explainActiveRequestId === message.requestId && explainClient) {
          try {
            explainClient.cancel();
          } catch {
            // Not connected
          }
          explainActiveRequestId = null;
        }
      }
    },
  );
  port.onDisconnect.addListener(() => {
    if (explainActivePort === port) {
      explainActivePort = null;
      explainActiveRequestId = null;
    }
  });
}

