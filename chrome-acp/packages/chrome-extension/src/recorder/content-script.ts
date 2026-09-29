// Trajectory recorder content script (ISOLATED world, document_idle).
// Records semantic user actions plus a summary of the DOM changes they
// trigger, then forwards events to the background service worker over a
// long-lived port. Recording must never affect the page: every handler is
// passive and wrapped in try/catch.

import { setupActionListeners } from "./actions";
import { summarizeMutations } from "./mutation-summary";
import type {
  TrajectoryActionEvent,
  TrajectoryEvent,
  TrajectoryNavigationEvent,
} from "@chrome-acp/shared/acp";

// NOTE: the whole recorder lives inside an IIFE. Content scripts of the same
// extension share one isolated world, and the explain content script runs in
// the same scope — top-level var/function names here would collide with its
// bundle (they did: its `var m = "explain_enabled"` replaced our event queue,
// which silently killed all post-boot recording).
(() => {
const RESPONSE_WINDOW_MS = 500; // debounce window collecting post-action DOM changes
const MUTATION_BUFFER_CAP = 500;
const QUEUE_CAP = 200; // events buffered while the port is down
const NAV_POLL_MS = 1000; // SPA navigation detection
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30_000;
// Port health: an MV3 port created while the service worker is cold-starting
// can silently become a black hole ~1-2s after boot (postMessage neither
// throws nor fires onDisconnect, messages just vanish). Empirically a port
// that carries traffic from birth stays healthy, so we ping early and often:
// exponential pings right after connect, then a steady cadence. A missed pong
// rebuilds the port; connect() flushes anything queued meanwhile.
const PONG_TIMEOUT_MS = 800;
const EARLY_PING_DELAYS_MS = [500, 1000, 2000, 4000]; // after connect
const STEADY_PING_INTERVAL_MS = 10_000;

let port: chrome.runtime.Port | null = null;
let reconnectDelay = RECONNECT_BASE_MS;
const queue: TrajectoryEvent[] = [];
const mutationBuffer: MutationRecord[] = [];
let pendingActions: TrajectoryActionEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let pongDeadline = 0; // 0 = no ping in flight
let pingTimer: ReturnType<typeof setTimeout> | null = null;
let pingIndex = 0;

function send(events: TrajectoryEvent[]) {
  if (events.length === 0) return;
  if (port) {
    try {
      port.postMessage({ events });
      return;
    } catch {
      port = null; // fall through to buffering
    }
  }
  queue.push(...events);
  if (queue.length > QUEUE_CAP) queue.splice(0, queue.length - QUEUE_CAP);
}

function connect() {
  try {
    port = chrome.runtime.connect({ name: "trajectory" });
  } catch {
    port = null;
  }
  if (!port) {
    scheduleReconnect();
    return;
  }
  reconnectDelay = RECONNECT_BASE_MS;
  port.onDisconnect.addListener(() => {
    port = null;
    clearPingLoop();
    scheduleReconnect();
  });
  port.onMessage.addListener((msg: { type?: string }) => {
    if (msg?.type === "pong") {
      pongDeadline = 0;
    }
  });
  // Flush events buffered while disconnected
  if (queue.length > 0) {
    const buffered = queue.splice(0, queue.length);
    send(buffered);
  }
  // Start the ping chain: covers the boot-time black-hole window and then
  // keeps a steady heartbeat so the pipe never goes idle.
  pingIndex = 0;
  pongDeadline = Date.now() + PONG_TIMEOUT_MS;
  try {
    port.postMessage({ type: "ping" });
  } catch {
    /* the ping chain rebuilds the port on timeout */
  }
  schedulePing(EARLY_PING_DELAYS_MS[0]);
}

function clearPingLoop() {
  if (pingTimer) clearTimeout(pingTimer);
  pingTimer = null;
}

// Replace a port whose ping went unanswered; scheduleReconnect() retries with
// backoff and connect() flushes anything queued while the port was down.
function rebuildPort() {
  clearPingLoop();
  try {
    port?.disconnect();
  } catch {
    /* already gone */
  }
  port = null;
  scheduleReconnect();
}

function schedulePing(delayMs: number) {
  clearPingLoop();
  pingTimer = setTimeout(() => {
    if (!port) return;
    if (pongDeadline !== 0 && Date.now() >= pongDeadline) {
      rebuildPort();
      return;
    }
    pongDeadline = Date.now() + PONG_TIMEOUT_MS;
    try {
      port.postMessage({ type: "ping" });
    } catch {
      rebuildPort();
      return;
    }
    const delay =
      pingIndex < EARLY_PING_DELAYS_MS.length
        ? EARLY_PING_DELAYS_MS[pingIndex]
        : STEADY_PING_INTERVAL_MS;
    pingIndex++;
    schedulePing(delay);
  }, delayMs);
}

function scheduleReconnect() {
  setTimeout(connect, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
}

// ---- Action -> delayed flush (to attach the DOM-change summary) ----

function flush() {
  flushTimer = null;
  const summary = summarizeMutations(mutationBuffer);
  mutationBuffer.length = 0;
  const actions = pendingActions;
  pendingActions = [];
  if (summary && actions.length > 0) {
    actions[actions.length - 1]!.response = summary;
  }
  if (actions.length > 0) {
    console.log(
      `[STEP 3] content-script flushing ${actions.length} action(s) to background (port=${port ? "up" : "down"})`,
    );
  }
  send(actions);
}

function onAction(event: TrajectoryActionEvent) {
  pendingActions.push(event);
  if (flushTimer) clearTimeout(flushTimer);
  flushTimer = setTimeout(flush, RESPONSE_WINDOW_MS);
}

// A click that triggers a navigation would otherwise be lost: the page
// unloads inside the 500ms debounce window and the flush timer dies with it.
// Flush immediately on page hide / tab hide so every recorded action survives.
function flushNow() {
  if (flushTimer) {
    clearTimeout(flushTimer);
    flush();
  }
}
window.addEventListener("pagehide", flushNow);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flushNow();
});


// ---- Mutation collection (only while an action response window is open) ----

const observer = new MutationObserver((records) => {
  if (pendingActions.length === 0) return; // not attributable to a user action
  if (mutationBuffer.length < MUTATION_BUFFER_CAP) {
    mutationBuffer.push(...records);
  }
});

// ---- Navigation (initial load + SPA polling) ----

let lastUrl = location.href;

function navigationEvent(): TrajectoryNavigationEvent {
  return {
    ts: Date.now(),
    type: "navigation",
    url: location.href,
    title: document.title,
  };
}

function checkNavigation() {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    send([navigationEvent()]);
  }
}

// ---- Bootstrap ----

try {
  console.log(`[STEP 1] recorder bootstrap: url=${location.href}`);
  connect();
  setupActionListeners((event) => {
    onAction(event);
  });
  if (window.top === window) {
    // Top frame only: actions are captured in every frame, but navigation
    // is owned by the top document (iframe frames would duplicate it).
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      characterData: true,
    });
    send([navigationEvent()]);
    setInterval(checkNavigation, NAV_POLL_MS);
  }
} catch (error) {
  console.warn("[trajectory] recorder failed to start:", error);
}
})();
