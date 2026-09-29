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
  return trajectoryWsUrlFor(settings.proxyUrl);
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
      let msg: { type?: string; callId?: string; params?: unknown };
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
      if (msg.type !== "browser_tool_call" || msg.callId === undefined) return;

      let result: unknown;
      try {
        result = await executeBrowserTool(msg.params as Parameters<typeof executeBrowserTool>[0]);
      } catch (error) {
        result = { error: (error as Error).message };
      }
      socket.send(JSON.stringify({ type: "browser_tool_result", callId: msg.callId, result }));
    })();
  };

  socket.onclose = () => {
    if (toolWs === socket) toolWs = null;
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

