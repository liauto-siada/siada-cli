// Immersive explain content script (ISOLATED world, document_idle).
// When the user selects text on a page, a small floating "解释" button
// appears next to the selection. Clicking it streams an AI-generated
// explanation into a floating card beside the selection. All UI is rendered
// inside shadow roots so page styles never leak in, and agent output is
// rendered with textContent only (never innerHTML).
//
// The feature is OFF by default and gated by the `explain_enabled` key in
// chrome.storage.local (toggled from the sidepanel settings): the floating
// button overlaps page text and swallows clicks in its area, so it only
// activates on explicit opt-in.

import { EXPLAIN_ENABLED_KEY } from "../settings";

// NOTE: IIFE on purpose — same-extension content scripts share one isolated
// world, and our top-level names must not collide with the recorder's bundle
// (or vice versa).
(() => {
const MIN_SELECTION_LENGTH = 2;
const SELECTION_DEBOUNCE_MS = 200;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30_000;
const MAX_CARD_TEXT = 50_000; // cap rendered explanation length

let port: chrome.runtime.Port | null = null;
let reconnectDelay = RECONNECT_BASE_MS;
let requestCounter = 0;
let activeRequestId: string | null = null;
let explainEnabled = false;

let selectionDebounce: ReturnType<typeof setTimeout> | null = null;
let buttonHost: HTMLDivElement | null = null;
let cardHost: HTMLDivElement | null = null;
let cardBody: HTMLDivElement | null = null;
let cardStatus: HTMLSpanElement | null = null;
let suppressButtonUntil = 0; // timestamp; hides button right after a click

// ---------------------------------------------------------------------------
// Port to the background worker
// ---------------------------------------------------------------------------

type ExplainPortMessage =
  | { kind: "chunk"; requestId: string; text: string }
  | { kind: "done"; requestId: string; stopReason: string }
  | { kind: "error"; requestId: string; message: string };

function connect() {
  if (!explainEnabled) return;
  try {
    port = chrome.runtime.connect({ name: "explain" });
  } catch {
    port = null;
  }
  if (!port) {
    scheduleReconnect();
    return;
  }
  reconnectDelay = RECONNECT_BASE_MS;
  port.onMessage.addListener(onPortMessage);
  port.onDisconnect.addListener(() => {
    port = null;
    // If an explanation was in flight, surface the disconnect in the card
    if (activeRequestId && cardStatus) {
      cardStatus.textContent = "连接已断开，请重试";
    }
    if (explainEnabled) scheduleReconnect();
  });
}

function disconnect() {
  try {
    port?.disconnect();
  } catch {
    // Port already gone
  }
  port = null;
}

function scheduleReconnect() {
  setTimeout(connect, reconnectDelay);
  reconnectDelay = Math.min(reconnectDelay * 2, RECONNECT_MAX_MS);
}

function onPortMessage(message: ExplainPortMessage) {
  if (!message || message.requestId !== activeRequestId) return;
  if (message.kind === "chunk") {
    appendChunk(message.text);
  } else if (message.kind === "done") {
    if (cardStatus) cardStatus.textContent = "";
  } else if (message.kind === "error") {
    if (cardStatus) cardStatus.textContent = `出错：${message.message}`;
  }
}

// ---------------------------------------------------------------------------
// Floating button
// ---------------------------------------------------------------------------

function ensureButton(): HTMLDivElement {
  if (buttonHost) return buttonHost;

  buttonHost = document.createElement("div");
  buttonHost.style.cssText =
    "position:absolute;z-index:2147483647;display:none;";
  const shadow = buttonHost.attachShadow({ mode: "closed" });

  const style = document.createElement("style");
  style.textContent = `
    button {
      all: initial;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 4px 10px;
      border-radius: 9999px;
      background: #1f2937;
      color: #f9fafb;
      font: 12px/1.4 -apple-system, "PingFang SC", "Segoe UI", sans-serif;
      cursor: pointer;
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.35);
      transition: background 0.15s;
    }
    button:hover { background: #374151; }
  `;
  const button = document.createElement("button");
  button.textContent = "✨ 解释";
  button.addEventListener("mousedown", (e) => {
    // Keep the page selection alive while clicking
    e.preventDefault();
    e.stopPropagation();
  });
  button.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    const text = window.getSelection()?.toString().trim() ?? "";
    if (text.length < MIN_SELECTION_LENGTH) return;
    const rect = window.getSelection()!.getRangeAt(0).getBoundingClientRect();
    suppressButtonUntil = Date.now() + 500;
    hideButton();
    startExplanation(text, rect);
  });

  shadow.append(style, button);
  document.documentElement.appendChild(buttonHost);
  return buttonHost;
}

function showButton(rect: DOMRect) {
  const host = ensureButton();
  const top = rect.bottom + window.scrollY + 6;
  const left = Math.max(4, rect.left + window.scrollX);
  host.style.top = `${top}px`;
  host.style.left = `${left}px`;
  host.style.display = "block";
}

function hideButton() {
  if (buttonHost) buttonHost.style.display = "none";
}

// ---------------------------------------------------------------------------
// Explanation card
// ---------------------------------------------------------------------------

function removeCard() {
  if (cardHost) {
    cardHost.remove();
    cardHost = null;
    cardBody = null;
    cardStatus = null;
  }
}

function ensureCard(rect: DOMRect) {
  removeCard();

  cardHost = document.createElement("div");
  const top = rect.bottom + window.scrollY + 8;
  const left = Math.min(
    Math.max(4, rect.left + window.scrollX),
    window.scrollX + window.innerWidth - 380,
  );
  cardHost.style.cssText = `position:absolute;z-index:2147483647;top:${top}px;left:${Math.max(4, left)}px;`;

  const shadow = cardHost.attachShadow({ mode: "closed" });
  const style = document.createElement("style");
  style.textContent = `
    .card {
      width: 360px;
      max-height: 45vh;
      display: flex;
      flex-direction: column;
      background: #111827;
      color: #e5e7eb;
      border: 1px solid #374151;
      border-radius: 10px;
      box-shadow: 0 8px 30px rgba(0, 0, 0, 0.45);
      font: 13px/1.6 -apple-system, "PingFang SC", "Segoe UI", sans-serif;
      overflow: hidden;
    }
    .header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6px 10px;
      border-bottom: 1px solid #1f2937;
      color: #9ca3af;
      font-size: 12px;
      flex-shrink: 0;
    }
    .close {
      all: initial;
      cursor: pointer;
      color: #9ca3af;
      font-size: 14px;
      padding: 0 4px;
      font-family: inherit;
    }
    .close:hover { color: #f9fafb; }
    .body {
      padding: 10px 12px;
      overflow-y: auto;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .status { color: #6b7280; font-size: 12px; }
  `;

  const card = document.createElement("div");
  card.className = "card";

  const header = document.createElement("div");
  header.className = "header";
  const title = document.createElement("span");
  title.textContent = "✨ 沉浸式解释";
  const closeBtn = document.createElement("button");
  closeBtn.className = "close";
  closeBtn.textContent = "✕";
  closeBtn.addEventListener("click", () => {
    cancelActive();
    removeCard();
  });
  header.append(title, closeBtn);

  cardBody = document.createElement("div");
  cardBody.className = "body";
  cardStatus = document.createElement("span");
  cardStatus.className = "status";
  cardStatus.textContent = "正在解释…";
  cardBody.appendChild(cardStatus);

  card.append(header, cardBody);
  shadow.append(style, card);
  document.documentElement.appendChild(cardHost);
}

function appendChunk(text: string) {
  if (!cardBody) return;
  if (cardStatus?.textContent === "正在解释…") cardStatus.textContent = "";
  const current = cardBody.textContent ?? "";
  if (current.length < MAX_CARD_TEXT) {
    cardBody.appendChild(document.createTextNode(text));
    cardBody.scrollTop = cardBody.scrollHeight;
  }
}

function cancelActive() {
  if (activeRequestId && port) {
    try {
      port.postMessage({ kind: "cancel", requestId: activeRequestId });
    } catch {
      // Port gone
    }
  }
  activeRequestId = null;
}

// ---------------------------------------------------------------------------
// Explanation flow
// ---------------------------------------------------------------------------

function startExplanation(text: string, rect: DOMRect) {
  if (!port) connect();
  ensureCard(rect);

  activeRequestId = `explain-${Date.now()}-${++requestCounter}`;
  const message = {
    kind: "explain",
    requestId: activeRequestId,
    text: text.slice(0, 8000),
    url: location.href,
    title: document.title,
  };
  try {
    port?.postMessage(message);
  } catch {
    activeRequestId = null;
    if (cardStatus) cardStatus.textContent = "无法连接后台，请重试";
    connect();
  }
}

// ---------------------------------------------------------------------------
// Selection tracking
// ---------------------------------------------------------------------------

function currentSelection(): { text: string; rect: DOMRect } | null {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
    return null;
  }
  const text = selection.toString().trim();
  if (text.length < MIN_SELECTION_LENGTH) return null;
  const rect = selection.getRangeAt(0).getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  return { text, rect };
}

function scheduleSelectionCheck() {
  if (selectionDebounce) clearTimeout(selectionDebounce);
  selectionDebounce = setTimeout(() => {
    selectionDebounce = null;
    if (!explainEnabled) return;
    if (Date.now() < suppressButtonUntil) return;
    const sel = currentSelection();
    if (sel) showButton(sel.rect);
    else hideButton();
  }, SELECTION_DEBOUNCE_MS);
}

// ---------------------------------------------------------------------------
// Feature toggle (chrome.storage.local, switched from sidepanel settings)
// ---------------------------------------------------------------------------

function setExplainEnabled(enabled: boolean) {
  if (explainEnabled === enabled) return;
  explainEnabled = enabled;
  if (!enabled) {
    // Tear down any visible UI and the background port immediately
    cancelActive();
    hideButton();
    removeCard();
    disconnect();
  }
}

// ---------------------------------------------------------------------------
// Bootstrap
// ---------------------------------------------------------------------------

try {
  chrome.storage.local
    .get(EXPLAIN_ENABLED_KEY)
    .then((stored) => {
      setExplainEnabled(stored[EXPLAIN_ENABLED_KEY] === true);
      if (explainEnabled) connect();
    })
    .catch(() => {});
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local" || !(EXPLAIN_ENABLED_KEY in changes)) return;
    setExplainEnabled(changes[EXPLAIN_ENABLED_KEY]?.newValue === true);
  });
  document.addEventListener("mouseup", scheduleSelectionCheck, true);
  document.addEventListener("keyup", (e) => {
    if (e.shiftKey || e.key === "Shift") scheduleSelectionCheck();
  }, true);
  document.addEventListener("mousedown", (e) => {
    // Clicking the button/card keeps them; clicking elsewhere hides the button
    const path = e.composedPath();
    if (buttonHost && path.includes(buttonHost)) return;
    hideButton();
  }, true);
  document.addEventListener("scroll", hideButton, true);
  window.addEventListener("resize", hideButton);
  document.addEventListener("selectionchange", () => {
    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) hideButton();
  });
} catch (error) {
  console.warn("[explain] content script failed to start:", error);
}
})();
