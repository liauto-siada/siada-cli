import type {
  ACPSettings,
  AgentCapabilities,
  AgentSessionInfo,
  BrowserToolParams,
  BrowserToolResult,
  ConnectionState,
  ContentBlock,
  ListSessionsRequest,
  ListSessionsResponse,
  LoadSessionRequest,
  PermissionRequestPayload,
  PromptCapabilities,
  ProxyMessage,
  ProxyResponse,
  ResumeSessionRequest,
  SessionUpdate,
  SessionModelState,
  SessionConfigOption,
  ModelInfo,
  FileItem,
  FileContent,
  FileChange,
  FramePayload,
  LiveViewMode,
} from "./types";

/**
 * Error thrown when disconnect() is called while a connection is in progress.
 * Callers can use `instanceof` to distinguish this from real connection errors.
 */
export class DisconnectRequestedError extends Error {
  constructor() {
    super("Disconnect requested");
    this.name = "DisconnectRequestedError";
  }
}

// Transport-level failure (handshake never completed, e.g. plain ws://
// against a TLS-only port). Distinct from server-side rejections (auth,
// proxy error messages) so connect() can tell "wrong scheme" apart from
// "server reachable but refused".
class WebSocketTransportError extends Error {}

export type ConnectionStateHandler = (
  state: ConnectionState,
  error?: string,
) => void;
export type SessionUpdateHandler = (sessionId: string, update: SessionUpdate) => void;
export type SessionCreatedHandler = (sessionId: string) => void;
export type PromptCompleteHandler = (stopReason: string) => void;
export type PermissionRequestHandler = (request: PermissionRequestPayload) => void;
// Runtime error notifications from the proxy (e.g. prompt failures). Without
// this, agent-side errors only land in the console and the UI stays silent.
export type ErrorHandler = (message: string) => void;
export type BrowserToolCallHandler = (
  params: BrowserToolParams,
) => Promise<BrowserToolResult>;
export type ModelChangedHandler = (modelId: string) => void;
export type ModelStateChangedHandler = (state: SessionModelState | null) => void;

/**
 * Derive model selection state from a session's configOptions.
 * Newer agents (e.g. siada-agenthub) don't implement the legacy `models`
 * field; they expose model selection as a category="model" select option.
 * Reference: Zed's config_state() reads response.config_options.
 */
function modelStateFromConfigOptions(
  configOptions: SessionConfigOption[] | null | undefined,
): { state: SessionModelState; configId: string } | null {
  const option = configOptions?.find(
    (o) => o.type === "select" && o.category === "model",
  );
  if (!option) return null;

  // Options can be a flat list or grouped; flatten for the picker
  const availableModels: ModelInfo[] = [];
  for (const entry of option.options) {
    if ("value" in entry) {
      availableModels.push({
        modelId: entry.value,
        name: entry.name,
        description: entry.description ?? null,
      });
    } else {
      for (const sub of entry.options) {
        availableModels.push({
          modelId: sub.value,
          name: sub.name,
          description: sub.description ?? null,
        });
      }
    }
  }
  if (availableModels.length === 0) return null;

  return {
    state: { availableModels, currentModelId: option.currentValue },
    configId: option.id,
  };
}

export type FileChangesHandler = (changes: FileChange[]) => void;
// Handler for server-pushed directory listings (e.g., after session cwd change)
export type DirListingPushHandler = (path: string, items: FileItem[]) => void;
// Handler for pictures of the controlled page pushed by the extension. Kept
// trace-agnostic: the caller decides how a frame maps onto a trace step.
//
// The relay routes each picture to the viewer of the tab it came from and tags
// it with that tab and the run it belongs to, so a consumer can reject a
// picture that reach it late (after a session switch, say) instead of blending
// it into the current timeline. Producers that do not tag their pictures leave
// these undefined.
export interface FrameEnvelope {
  callId?: string;
  tabId?: number;
  sessionId?: string;
  payload: FramePayload;
}
export type FrameHandler = (frame: FrameEnvelope) => void;
// Handler for live view state changes (the extension reports whether the
// screencast actually started, and why not when it failed).
export type ScreencastStateHandler = (state: {
  active: boolean;
  error?: string;
  mode?: LiveViewMode;
}) => void;
// What a second consumer (the trace collector) needs to know about a turn:
// when a prompt starts and when/why it stops. A turn is what the protocol
// actually ends with — `prompt_complete` carries the stop reason (including
// "cancelled"), a proxy "error" message is a failed turn, and a dropped
// connection ends the stream without either. Emitted *in addition to* the
// single-handler prompt_complete/error setters, which ChatInterface already
// owns.
export type TurnLifecycleEvent =
  | { kind: "started" }
  | { kind: "completed"; stopReason: string }
  | { kind: "failed"; message: string }
  | { kind: "cancel-requested" }
  | { kind: "disconnected"; error?: string };
export type TurnLifecycleHandler = (event: TurnLifecycleEvent) => void;
// Handler for session loaded/resumed events
export type SessionLoadedHandler = (sessionId: string) => void;
// Handler fired before switching the active session.
// This matches Zed's model more closely: the UI changes active thread first,
// then receives updates for that thread while load/resume is in flight.
export type SessionSwitchingHandler = (sessionId: string) => void;

interface PendingFileRequest<T> {
  path: string;
  resolve: (value: T) => void;
  reject: (err: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

function settleFileRequest<T>(
  requests: Map<number, PendingFileRequest<T>>,
  payload: { path: string; requestId?: number },
  result: T | Error,
): boolean {
  let matched = false;
  for (const [id, pending] of requests) {
    // Older proxies return only the path. Settle all callers for that path.
    if (payload.requestId !== undefined ? id !== payload.requestId : pending.path !== payload.path) continue;
    if (pending.path !== payload.path) continue;
    matched = true;
    clearTimeout(pending.timer);
    requests.delete(id);
    if (result instanceof Error) pending.reject(result);
    else pending.resolve(result);
  }
  return matched;
}

export class ACPClient {
  private ws: WebSocket | null = null;
  private settings: ACPSettings;
  private connectionState: ConnectionState = "disconnected";
  private sessionId: string | null = null;
  private pendingSessionTarget: string | null = null;
  // Reference: Zed stores full agentCapabilities from initialize response
  // Used to check supports_load_session, supports_resume_session, etc.
  private _agentCapabilities: AgentCapabilities | null = null;
  // Reference: Zed's prompt_capabilities in MessageEditor
  // Stores capabilities from agent's initialize response
  private _promptCapabilities: PromptCapabilities | null = null;
  // Reference: Zed stores model state from NewSessionResponse
  private _modelState: SessionModelState | null = null;
  // Config option id when model selection came from configOptions (new-style
  // agents); setSessionModel() then routes to set_config_option instead of
  // the legacy session/set_model.
  private _modelConfigId: string | null = null;
  private onModelChanged: ModelChangedHandler | null = null;
  private onModelStateChanged: ModelStateChangedHandler | null = null;
  private onSessionLoaded: SessionLoadedHandler | null = null;
  private onSessionSwitching: SessionSwitchingHandler | null = null;

  private onConnectionStateChange: ConnectionStateHandler | null = null;
  private onSessionUpdate: SessionUpdateHandler | null = null;
  // Additional consumers of the session-update stream (e.g. the trace
  // collector). Kept separate from onSessionUpdate so the single-handler
  // setters used by ChatInterface keep working unchanged.
  private sessionUpdateListeners: Set<SessionUpdateHandler> = new Set();
  private onSessionCreated: SessionCreatedHandler | null = null;
  private onPromptComplete: PromptCompleteHandler | null = null;
  // Additional consumers of the turn lifecycle (e.g. the trace collector).
  private turnLifecycleHandlers: Set<TurnLifecycleHandler> = new Set();
  private onPermissionRequest: PermissionRequestHandler | null = null;
  private onError: ErrorHandler | null = null;
  private onBrowserToolCall: BrowserToolCallHandler | null = null;
  private fileChangesHandlers: Set<FileChangesHandler> = new Set();
  private frameHandlers: Set<FrameHandler> = new Set();
  private screencastStateHandlers: Set<ScreencastStateHandler> = new Set();
  private onDirListingPush: DirListingPushHandler | null = null;

  // Pending file operations - keyed by unique requestId to handle concurrent requests
  private requestIdCounter = 0;
  private pendingDirListing = new Map<number, PendingFileRequest<FileItem[]>>();
  private pendingFileRead = new Map<number, PendingFileRequest<FileContent>>();
  // Pending session operations
  private pendingSessionList: { resolve: (response: ListSessionsResponse) => void; reject: (err: Error) => void } | null = null;
  private pendingSessionLoad: { resolve: (sessionId: string) => void; reject: (err: Error) => void } | null = null;
  private pendingSessionResume: { resolve: (sessionId: string) => void; reject: (err: Error) => void } | null = null;

  private connectResolve: ((value: void) => void) | null = null;
  private connectReject: ((error: Error) => void) | null = null;

  // Heartbeat state
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private heartbeatTimeout: ReturnType<typeof setTimeout> | null = null;
  private missedPongs = 0;
  private static readonly HEARTBEAT_INTERVAL_MS = 30_000;
  private static readonly PONG_TIMEOUT_MS = 10_000;
  private static readonly MAX_MISSED_PONGS = 2;

  constructor(settings: ACPSettings) {
    this.settings = settings;
  }

  updateSettings(settings: ACPSettings): void {
    this.settings = settings;
  }

  setConnectionStateHandler(handler: ConnectionStateHandler): void {
    this.onConnectionStateChange = handler;
  }

  setSessionUpdateHandler(handler: SessionUpdateHandler): void {
    this.onSessionUpdate = handler;
  }

  /**
   * Observe session updates without replacing the primary handler. Returns an
   * unsubscribe function. Used by the trace collector, which runs alongside
   * ChatInterface rather than instead of it.
   */
  addSessionUpdateListener(handler: SessionUpdateHandler): () => void {
    this.sessionUpdateListeners.add(handler);
    return () => {
      this.sessionUpdateListeners.delete(handler);
    };
  }

  setSessionCreatedHandler(handler: SessionCreatedHandler): void {
    this.onSessionCreated = handler;
  }

  setPromptCompleteHandler(handler: PromptCompleteHandler): void {
    this.onPromptComplete = handler;
  }

  /**
   * Observe the turn lifecycle (started / completed / failed / cancel
   * requested / disconnected) without replacing the primary
   * prompt_complete and error callbacks.
   *
   * @returns Unsubscribe function
   */
  addTurnLifecycleListener(handler: TurnLifecycleHandler): () => void {
    this.turnLifecycleHandlers.add(handler);
    return () => {
      this.turnLifecycleHandlers.delete(handler);
    };
  }

  private emitTurn(event: TurnLifecycleEvent): void {
    for (const handler of this.turnLifecycleHandlers) {
      try {
        handler(event);
      } catch (error) {
        // A listener must never break the connection's own message handling.
        console.error("[ACPClient] turn lifecycle listener failed:", error);
      }
    }
  }

  setModelChangedHandler(handler: ModelChangedHandler): void {
    this.onModelChanged = handler;
  }

  /**
   * Set handler for model state changes (called when session is created/destroyed).
   * This replaces polling - the handler is called immediately with current state,
   * and again whenever session is created or disconnected.
   */
  setModelStateChangedHandler(handler: ModelStateChangedHandler): void {
    this.onModelStateChanged = handler;
    // Immediately notify with current state
    handler(this._modelState);
  }

  setPermissionRequestHandler(handler: PermissionRequestHandler): void {
    this.onPermissionRequest = handler;
  }

  setErrorHandler(handler: ErrorHandler): void {
    this.onError = handler;
  }

  setBrowserToolCallHandler(handler: BrowserToolCallHandler): void {
    this.onBrowserToolCall = handler;
  }

  setSessionSwitchingHandler(handler: SessionSwitchingHandler | null): void {
    this.onSessionSwitching = handler;
  }

  /**
   * Set handler for server-pushed directory listings.
   * Called when server sends a dir_listing without a corresponding request
   * (e.g., after session cwd change).
   * Pass null to clear the handler.
   */
  setDirListingPushHandler(handler: DirListingPushHandler | null): void {
    this.onDirListingPush = handler;
  }

  private setState(state: ConnectionState, error?: string): void {
    const wasConnected = this.connectionState === "connected";
    this.connectionState = state;
    if (wasConnected && (state === "disconnected" || state === "error")) {
      // The stream the run was following is gone; nothing else will report the
      // turn as finished, so tell lifecycle listeners (e.g. the trace viewer)
      // instead of leaving it "running" forever.
      this.emitTurn({ kind: "disconnected", error });
    }
    this.onConnectionStateChange?.(state, error);
  }

  getState(): ConnectionState {
    return this.connectionState;
  }

  getSessionId(): string | null {
    return this.sessionId;
  }

  // Reference: Zed's supports_images() in MessageEditor
  // Returns true if the agent supports image content in prompts
  get supportsImages(): boolean {
    return this._promptCapabilities?.image === true;
  }

  // Reference: Zed's prompt_capabilities in MessageEditor
  getPromptCapabilities(): PromptCapabilities | null {
    return this._promptCapabilities;
  }

  /**
   * Get the current model state (available models and current model ID).
   * Reference: Zed's AgentModelSelector reads from state.available_models
   */
  get modelState(): SessionModelState | null {
    return this._modelState;
  }

  /**
   * Check if the agent supports model selection.
   * Reference: Zed's model_selector() returns Option<Rc<dyn AgentModelSelector>>
   */
  get supportsModelSelection(): boolean {
    return this._modelState !== null && this._modelState.availableModels.length > 0;
  }

  /**
   * Resolve model state from a session response: prefer the new-style
   * configOptions (category="model" select), fall back to the legacy
   * `models` field. Also records the config option id used to switch models.
   */
  private applySessionModelState(
    models: SessionModelState | null | undefined,
    configOptions: SessionConfigOption[] | null | undefined,
  ): void {
    const fromConfig = modelStateFromConfigOptions(configOptions);
    if (fromConfig) {
      this._modelState = fromConfig.state;
      this._modelConfigId = fromConfig.configId;
    } else {
      this._modelState = models ?? null;
      this._modelConfigId = null;
    }
  }

  // ============================================================================
  // Session Capability Getters
  // Reference: Zed's AgentConnection supports_* methods
  // ============================================================================

  /**
   * Get the full agent capabilities.
   * Reference: Zed's AcpConnection.agent_capabilities
   */
  get agentCapabilities(): AgentCapabilities | null {
    return this._agentCapabilities;
  }

  /**
   * Check if the agent supports loading existing sessions.
   * Reference: Zed's AcpConnection.supports_load_session()
   */
  get supportsLoadSession(): boolean {
    return this._agentCapabilities?.loadSession === true;
  }

  /**
   * Check if the agent supports resuming existing sessions.
   * Reference: Zed's AcpConnection.supports_resume_session()
   */
  get supportsResumeSession(): boolean {
    return this._agentCapabilities?.sessionCapabilities?.resume !== undefined
      && this._agentCapabilities?.sessionCapabilities?.resume !== null;
  }

  /**
   * Check if the agent supports listing sessions.
   * Reference: Zed checks agent_capabilities.session_capabilities.list
   */
  get supportsSessionList(): boolean {
    return this._agentCapabilities?.sessionCapabilities?.list !== undefined
      && this._agentCapabilities?.sessionCapabilities?.list !== null;
  }

  /**
   * Check if the agent supports session history (load or resume).
   * Reference: Zed's AgentConnection.supports_session_history()
   */
  get supportsSessionHistory(): boolean {
    return this.supportsLoadSession || this.supportsResumeSession;
  }

  async connect(): Promise<void> {
    const initialUrl = this.settings.proxyUrl;
    try {
      await this.openConnection();
    } catch (error) {
      // Loopback scheme mismatch: the proxy serves TLS to remote peers but
      // keeps plaintext ws for loopback clients on the same port, while
      // older TLS-only proxies only accepted wss. A mismatch surfaces as a
      // transport-level failure (the handshake never completed); auth
      // rejections or proxy error messages mean the server was reached, so
      // the scheme was fine. Retry once with the other scheme.
      if (error instanceof WebSocketTransportError && this.flipLoopbackScheme()) {
        try {
          await this.openConnection();
          return;
        } catch (retryError) {
          // Neither scheme works — restore the stored URL so later
          // reconnects start from the user's original value.
          this.settings = { ...this.settings, proxyUrl: initialUrl };
          throw retryError;
        }
      }
      throw error;
    }
  }

  // Flip settings.proxyUrl between ws:// and wss:// when it targets a
  // loopback host. Returns true when the flip happened (i.e. a retry is
  // worthwhile).
  private flipLoopbackScheme(): boolean {
    try {
      const url = new URL(this.settings.proxyUrl);
      const host = url.hostname.replace(/^\[|\]$/g, "");
      const isLoopback = host === "localhost" || host === "127.0.0.1" || host === "::1";
      if (!isLoopback || (url.protocol !== "ws:" && url.protocol !== "wss:")) {
        return false;
      }
      const from = url.protocol;
      url.protocol = url.protocol === "ws:" ? "wss:" : "ws:";
      this.settings = { ...this.settings, proxyUrl: url.toString() };
      console.warn(`[ACPClient] ${from} failed; retrying loopback connection over ${url.protocol} (${this.settings.proxyUrl})`);
      return true;
    } catch {
      return false;
    }
  }

  private async openConnection(): Promise<void> {
    if (this.ws) {
      this.disconnect();
    }

    this.setState("connecting");

    return new Promise((resolve, reject) => {
      this.connectResolve = resolve;
      this.connectReject = reject;

      try {
        // Build WebSocket URL with token if provided
        let wsUrl = this.settings.proxyUrl;
        if (this.settings.token) {
          const url = new URL(wsUrl);
          url.searchParams.set("token", this.settings.token);
          wsUrl = url.toString();
        }
        const ws = new WebSocket(wsUrl);
        this.ws = ws;

        ws.onopen = () => {
          // Guard against race condition: check if this WebSocket is still current
          if (this.ws !== ws) {
            console.log("[ACPClient] WebSocket opened but already disconnected/replaced, closing stale socket");
            ws.close();
            return;
          }
          console.log("[ACPClient] WebSocket connected, sending connect command");
          this.send({ type: "connect" });
        };

        ws.onmessage = (event) => {
          // Ignore messages from stale sockets
          if (this.ws !== ws) return;
          try {
            const response: ProxyResponse = JSON.parse(event.data);
            this.handleResponse(response);
          } catch (error) {
            console.error("[ACPClient] Failed to parse message:", error);
          }
        };

        ws.onerror = () => {
          // Ignore errors from stale sockets
          if (this.ws !== ws) return;
          console.error("[ACPClient] WebSocket error");
          const errorMessage = `WebSocket connection error (${this.settings.proxyUrl})`;
          this.setState("error", errorMessage);
          this.connectReject?.(new WebSocketTransportError(errorMessage));
          this.connectResolve = null;
          this.connectReject = null;
        };

        ws.onclose = (event) => {
          // Ignore close events from stale sockets (replaced by a new connection)
          if (this.ws !== ws) return;
          console.log("[ACPClient] WebSocket closed", event.code, event.reason);

          // Check if closed due to auth failure (code 4001) or other error during connect
          if (this.connectReject) {
            const errorMessage = event.reason || `Connection closed (code: ${event.code})`;
            this.setState("error", errorMessage);
            // No reason = transport gave up (some platforms skip onerror);
            // a reason means the server deliberately rejected (e.g. auth).
            const closeError = event.reason
              ? new Error(errorMessage)
              : new WebSocketTransportError(errorMessage);
            this.connectReject(closeError);
            this.connectResolve = null;
            this.connectReject = null;
          } else if (this.connectionState === "error") {
            // Close following a connect-phase error (e.g. onerror or a proxy
            // "error" message already rejected the connect): keep the error
            // state and message visible instead of downgrading to
            // "disconnected", which would wipe the reason from the UI.
          } else {
            this.setState("disconnected");
          }

          this.ws = null;
          this.sessionId = null;
        };
      } catch (error) {
        this.setState("error", (error as Error).message);
        reject(error);
      }
    });
  }

  private handleResponse(response: ProxyResponse): void {
    console.log("[ACPClient] Received:", response.type);

    switch (response.type) {
      case "status":
        if (response.payload.connected) {
          // Reference: Zed stores full agentCapabilities from status message
          this._agentCapabilities = response.payload.capabilities ?? null;
          this.setState("connected");
          this.startHeartbeat();
          this.connectResolve?.();
        } else {
          this.stopHeartbeat();
          if (this.connectReject) {
            // Connect still in flight and the agent didn't come up (e.g. the
            // process exited during initialization on an older proxy, or the
            // agent connection dropped). Settle the pending connect() so the
            // UI leaves "Connecting..." and shows the failure instead of
            // hanging forever.
            const errorMessage = "Agent connection failed (agent did not start)";
            this.setState("error", errorMessage);
            this.connectReject(new Error(errorMessage));
          } else if (this.connectionState !== "error") {
            // Normal transition after being connected, or an explicit
            // disconnect — but never overwrite a connect-phase error.
            this.setState("disconnected");
          }
        }
        this.connectResolve = null;
        this.connectReject = null;
        break;

      case "error":
        // File explorer failures belong to their request, not to the chat or
        // an unrelated session operation. Recognize older proxy list errors too.
        if (response.payload.operation || response.payload.message.startsWith("list_dir failed: ")) {
          const operation = response.payload.operation ?? "list_dir";
          const legacyPath = response.payload.message.slice("list_dir failed: ".length);
          const path = response.payload.path ?? (legacyPath === "(root)" ? "" : legacyPath);
          const target = { path, requestId: response.payload.requestId };
          const error = new Error(response.payload.message);
          if (operation === "list_dir") settleFileRequest(this.pendingDirListing, target, error);
          else settleFileRequest(this.pendingFileRead, target, error);
          break;
        }
        console.error("[ACPClient] Error:", response.payload.message);
        this.pendingSessionTarget = null;
        // Surface runtime errors (e.g. prompt failures) to the UI
        this.onError?.(response.payload.message);
        this.emitTurn({ kind: "failed", message: response.payload.message });
        // Reject pending session operations if any
        this.pendingSessionList?.reject(new Error(response.payload.message));
        this.pendingSessionList = null;
        this.pendingSessionLoad?.reject(new Error(response.payload.message));
        this.pendingSessionLoad = null;
        this.pendingSessionResume?.reject(new Error(response.payload.message));
        this.pendingSessionResume = null;
        if (this.connectReject) {
          // Connect-phase failure (e.g. agent failed to start on the proxy):
          // reflect it in the connection state so the reason stays visible;
          // the status/close follow-up must not wipe it.
          this.setState("error", response.payload.message);
          this.connectReject(new Error(response.payload.message));
        }
        this.connectResolve = null;
        this.connectReject = null;
        break;

      case "session_created":
        this.sessionId = response.payload.sessionId;
        this.pendingSessionTarget = null;
        // Reference: Zed stores promptCapabilities from session/initialize response
        this._promptCapabilities = response.payload.promptCapabilities ?? null;
        // Reference: Zed's config_state() - prefer configOptions (new-style
        // agents like siada), fall back to legacy `models` field
        this.applySessionModelState(response.payload.models, response.payload.configOptions);
        console.log("[ACPClient] Session created, promptCapabilities:", this._promptCapabilities, "models:", this._modelState);
        this.onSessionCreated?.(response.payload.sessionId);
        // Notify model state subscribers (replaces polling in useModels)
        this.onModelStateChanged?.(this._modelState);
        break;

      // Session history responses - Reference: Zed's AgentSessionList
      case "session_list":
        console.log("[ACPClient] Session list received:", response.payload.sessions.length, "sessions");
        this.pendingSessionList?.resolve(response.payload);
        this.pendingSessionList = null;
        break;

      case "session_loaded":
        this.sessionId = response.payload.sessionId;
        this.pendingSessionTarget = null;
        this._promptCapabilities = response.payload.promptCapabilities ?? null;
        this.applySessionModelState(response.payload.models, response.payload.configOptions);
        console.log("[ACPClient] Session loaded:", response.payload.sessionId);
        this.pendingSessionLoad?.resolve(response.payload.sessionId);
        this.pendingSessionLoad = null;
        this.onSessionLoaded?.(response.payload.sessionId);
        this.onModelStateChanged?.(this._modelState);
        break;

      case "session_resumed":
        this.sessionId = response.payload.sessionId;
        this.pendingSessionTarget = null;
        this._promptCapabilities = response.payload.promptCapabilities ?? null;
        this.applySessionModelState(response.payload.models, response.payload.configOptions);
        console.log("[ACPClient] Session resumed:", response.payload.sessionId);
        this.pendingSessionResume?.resolve(response.payload.sessionId);
        this.pendingSessionResume = null;
        this.onSessionLoaded?.(response.payload.sessionId);
        this.onModelStateChanged?.(this._modelState);
        break;

      case "session_update":
        this.onSessionUpdate?.(response.payload.sessionId, response.payload.update);
        for (const listener of this.sessionUpdateListeners) {
          try {
            listener(response.payload.sessionId, response.payload.update);
          } catch (error) {
            console.error("[ACPClient] session update listener failed:", error);
          }
        }
        break;

      case "prompt_complete":
        this.onPromptComplete?.(response.payload.stopReason);
        this.emitTurn({ kind: "completed", stopReason: response.payload.stopReason });
        break;

      case "permission_request":
        console.log("[ACPClient] Permission request:", response.payload);
        this.onPermissionRequest?.(response.payload);
        break;

      case "model_changed":
        console.log("[ACPClient] Model changed:", response.payload.modelId);
        if (this._modelState) {
          this._modelState = {
            ...this._modelState,
            currentModelId: response.payload.modelId,
          };
        }
        this.onModelChanged?.(response.payload.modelId);
        break;

      case "browser_tool_call":
        this.handleBrowserToolCall(response.callId, response.params);
        break;

      case "frame": {
        // Routing metadata the relay adds on top of the payload. The shared
        // message type does not declare it yet, so it is read as an optional
        // extra: a picture without it is passed on as-is rather than guessed at.
        const relayed = response as { tabId?: unknown; sessionId?: unknown };
        for (const handler of this.frameHandlers) {
          handler({
            callId: response.callId,
            tabId: typeof relayed.tabId === "number" ? relayed.tabId : undefined,
            sessionId:
              typeof relayed.sessionId === "string" ? relayed.sessionId : undefined,
            payload: response.payload,
          });
        }
        break;
      }

      case "screencast_state":
        for (const handler of this.screencastStateHandlers) {
          handler(response.payload);
        }
        break;

      case "dir_listing": {
        const matched = settleFileRequest(this.pendingDirListing, response.payload, response.payload.items);
        if (!matched && response.payload.requestId === undefined) {
          // Server-pushed listing (e.g., after session cwd change)
          this.onDirListingPush?.(response.payload.path, response.payload.items);
        }
        break;
      }

      case "file_content": {
        settleFileRequest(this.pendingFileRead, response.payload, response.payload);
        break;
      }

      case "file_changes":
        for (const handler of this.fileChangesHandlers) {
          handler(response.payload.changes);
        }
        break;

      case "pong":
        this.missedPongs = 0;
        if (this.heartbeatTimeout) {
          clearTimeout(this.heartbeatTimeout);
          this.heartbeatTimeout = null;
        }
        break;

      case "ping":
        // Server-side app-level heartbeat (keeps MV3 service workers alive).
        this.send({ type: "pong" });
        break;
    }
  }

  private async handleBrowserToolCall(
    callId: string,
    params: BrowserToolParams,
  ): Promise<void> {
    console.log("[ACPClient] Browser tool call:", callId, params);

    if (!this.onBrowserToolCall) {
      console.error("[ACPClient] No browser tool handler registered");
      this.send({
        type: "browser_tool_result",
        callId,
        result: { error: "No browser tool handler registered" },
      });
      return;
    }

    try {
      const result = await this.onBrowserToolCall(params);
      this.send({
        type: "browser_tool_result",
        callId,
        result,
      });
    } catch (error) {
      console.error("[ACPClient] Browser tool error:", error);
      this.send({
        type: "browser_tool_result",
        callId,
        result: { error: (error as Error).message },
      });
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.missedPongs = 0;

    this.heartbeatInterval = setInterval(() => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        this.stopHeartbeat();
        return;
      }

      this.ws.send(JSON.stringify({ type: "ping" }));

      this.heartbeatTimeout = setTimeout(() => {
        this.missedPongs++;
        if (this.missedPongs >= ACPClient.MAX_MISSED_PONGS) {
          console.warn(`[ACPClient] Server unresponsive (${this.missedPongs} missed pongs), closing connection`);
          this.stopHeartbeat();
          this.ws?.close(4000, "Heartbeat timeout");
        }
      }, ACPClient.PONG_TIMEOUT_MS);
    }, ACPClient.HEARTBEAT_INTERVAL_MS);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout);
      this.heartbeatTimeout = null;
    }
  }

  private send(message: ProxyMessage): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error("WebSocket not connected");
    }
    this.ws.send(JSON.stringify(message));
  }

  async createSession(cwd?: string, tabId?: number): Promise<void> {
    // Use provided cwd, or fall back to settings.cwd
    const sessionCwd = cwd ?? this.settings.cwd;
    this.send({ type: "new_session", payload: { cwd: sessionCwd, tabId } });
  }

  // Reference: Zed's MessageEditor.contents() builds Vec<acp::ContentBlock>
  // and sends via AcpThread.send()
  // Accepts either a string (for backward compatibility) or ContentBlock[]
  async sendPrompt(content: string | ContentBlock[]): Promise<void> {
    if (!this.sessionId) {
      throw new Error("No active session");
    }
    // Convert string to ContentBlock[] for backward compatibility
    const contentBlocks: ContentBlock[] = typeof content === "string"
      ? [{ type: "text", text: content }]
      : content;

    this.send({ type: "prompt", payload: { content: contentBlocks } });
    // The protocol has no "turn started" notification; sending the prompt is
    // the observable start of one.
    this.emitTurn({ kind: "started" });
  }

  cancel(): void {
    this.send({ type: "cancel" });
    // The agent answers a cancel with prompt_complete (stopReason
    // "cancelled"), but that can take a while or never arrive (the prompt may
    // already have failed agent-side). Report the request now; listeners that
    // close a turn on it are expected to treat later events as idempotent.
    this.emitTurn({ kind: "cancel-requested" });
  }

  /**
   * Set the model for the current session.
   * Reference: Zed's AgentModelSelector.select_model() calls connection.set_session_model()
   * For new-style agents (configOptions), routes to session/set_config_option instead.
   */
  async setSessionModel(modelId: string): Promise<void> {
    if (!this.sessionId) {
      throw new Error("No active session");
    }
    if (this._modelConfigId) {
      this.send({
        type: "set_config_option",
        payload: { configId: this._modelConfigId, value: modelId },
      });
    } else {
      this.send({ type: "set_session_model", payload: { modelId } });
    }
  }

  respondToPermission(requestId: string, optionId: string | null): void {
    const outcome = optionId
      ? { outcome: "selected" as const, optionId }
      : { outcome: "cancelled" as const };

    this.send({
      type: "permission_response",
      payload: { requestId, outcome },
    });
  }

  // ============================================================================
  // Session History Methods
  // Reference: Zed's AgentSessionList trait and AgentConnection methods
  // ============================================================================

  /**
   * Set handler for session loaded/resumed events.
   */
  setSessionLoadedHandler(handler: SessionLoadedHandler): void {
    this.onSessionLoaded = handler;
  }

  /**
   * List existing sessions from the agent.
   * Reference: Zed's AcpSessionList.list_sessions()
   * @throws Error if agent doesn't support session listing
   */
  async listSessions(request?: ListSessionsRequest): Promise<ListSessionsResponse> {
    if (!this.supportsSessionList) {
      throw new Error("Listing sessions is not supported by this agent");
    }
    return new Promise((resolve, reject) => {
      this.pendingSessionList = { resolve, reject };
      try {
        this.send({ type: "list_sessions", payload: request });
      } catch (err) {
        this.pendingSessionList = null;
        reject(err);
        return;
      }
      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.pendingSessionList) {
          const pending = this.pendingSessionList;
          this.pendingSessionList = null;
          pending.reject(new Error("List sessions timed out"));
        }
      }, 30000);
    });
  }

  /**
   * Load an existing session with history replay.
   * Reference: Zed's AcpConnection.load_session()
   * @throws Error if agent doesn't support session loading
   */
  async loadSession(request: LoadSessionRequest): Promise<string> {
    if (!this.supportsLoadSession) {
      throw new Error("Loading sessions is not supported by this agent");
    }
    return new Promise((resolve, reject) => {
      this.pendingSessionTarget = request.sessionId;
      this.onSessionSwitching?.(request.sessionId);
      this.pendingSessionLoad = { resolve, reject };
      try {
        this.send({ type: "load_session", payload: request });
      } catch (err) {
        this.pendingSessionTarget = null;
        this.pendingSessionLoad = null;
        reject(err);
        return;
      }
      // Timeout after 60 seconds (loading may take time for large sessions)
      setTimeout(() => {
        if (this.pendingSessionLoad) {
          this.pendingSessionTarget = null;
          const pending = this.pendingSessionLoad;
          this.pendingSessionLoad = null;
          pending.reject(new Error("Load session timed out"));
        }
      }, 60000);
    });
  }

  /**
   * Resume an existing session without history replay.
   * Reference: Zed's AcpConnection.resume_session()
   * @throws Error if agent doesn't support session resuming
   */
  async resumeSession(request: ResumeSessionRequest): Promise<string> {
    if (!this.supportsResumeSession) {
      throw new Error("Resuming sessions is not supported by this agent");
    }
    return new Promise((resolve, reject) => {
      this.pendingSessionTarget = request.sessionId;
      this.onSessionSwitching?.(request.sessionId);
      this.pendingSessionResume = { resolve, reject };
      try {
        this.send({ type: "resume_session", payload: request });
      } catch (err) {
        this.pendingSessionTarget = null;
        this.pendingSessionResume = null;
        reject(err);
        return;
      }
      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.pendingSessionResume) {
          this.pendingSessionTarget = null;
          const pending = this.pendingSessionResume;
          this.pendingSessionResume = null;
          pending.reject(new Error("Resume session timed out"));
        }
      }, 30000);
    });
  }

  // ============================================================================
  // File Explorer Methods
  // ============================================================================

  /**
   * List contents of a directory.
   * @param path - Relative path from agent CWD, empty string for root
   */
  async listDir(path: string): Promise<FileItem[]> {
    const requestId = ++this.requestIdCounter;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingDirListing.delete(requestId);
        reject(new Error("Directory listing timed out"));
      }, 10000);
      this.pendingDirListing.set(requestId, { path, resolve, reject, timer });
      try {
        this.send({ type: "list_dir", payload: { path, requestId } });
      } catch (err) {
        clearTimeout(timer);
        this.pendingDirListing.delete(requestId);
        reject(err);
        return;
      }
    });
  }

  /**
   * Read file content.
   * @param path - Relative path from agent CWD
   */
  async readFile(path: string): Promise<FileContent> {
    const requestId = ++this.requestIdCounter;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingFileRead.delete(requestId);
        reject(new Error("File read timed out"));
      }, 10000);
      this.pendingFileRead.set(requestId, { path, resolve, reject, timer });
      try {
        this.send({ type: "read_file", payload: { path, requestId } });
      } catch (err) {
        clearTimeout(timer);
        this.pendingFileRead.delete(requestId);
        reject(err);
        return;
      }
    });
  }

  /**
   * Subscribe to file change events.
   * @returns Unsubscribe function
   */
  onFileChanges(handler: FileChangesHandler): () => void {
    this.fileChangesHandlers.add(handler);
    return () => {
      this.fileChangesHandlers.delete(handler);
    };
  }

  /**
   * Subscribe to pictures of the controlled page pushed by the extension.
   * @returns Unsubscribe function
   */
  onFrame(handler: FrameHandler): () => void {
    this.frameHandlers.add(handler);
    return () => {
      this.frameHandlers.delete(handler);
    };
  }

  /**
   * Ask for the live view of the browser tab bound to this session, or turn it
   * off. The proxy resolves the tab, so this works from the web client too.
   */
  setScreencast(enabled: boolean): void {
    // UI unmount cleanup runs after disconnect has closed the socket. The
    // proxy owns stopping the stream on disconnect, so no stop is needed here.
    if (!enabled && (!this.ws || this.ws.readyState !== WebSocket.OPEN)) {
      return;
    }
    this.send({ type: "screencast", payload: { enabled } });
  }

  /**
   * Observe whether the live view is actually streaming.
   * @returns Unsubscribe function
   */
  onScreencastState(handler: ScreencastStateHandler): () => void {
    this.screencastStateHandlers.add(handler);
    return () => {
      this.screencastStateHandlers.delete(handler);
    };
  }

  disconnect(): void {
    this.stopHeartbeat();

    // Reject any pending connect promise with a distinguishable error
    // This ensures the promise settles and callers can catch/ignore it
    if (this.connectReject) {
      this.connectReject(new DisconnectRequestedError());
    }
    this.connectResolve = null;
    this.connectReject = null;

    if (this.ws) {
      try {
        this.send({ type: "disconnect" });
      } catch {
        // Ignore send errors during disconnect
      }
      this.ws.close();
      this.ws = null;
    }
    this.setState("disconnected");
    this.sessionId = null;
    this.pendingSessionTarget = null;
    this._modelState = null;
    this._modelConfigId = null;
    this._agentCapabilities = null;
    // Notify model state subscribers that session is gone
    this.onModelStateChanged?.(null);

    // Reject all pending operations before clearing
    const disconnectError = new Error("Disconnected");
    for (const { reject, timer } of this.pendingDirListing.values()) {
      clearTimeout(timer);
      reject(disconnectError);
    }
    for (const { reject, timer } of this.pendingFileRead.values()) {
      clearTimeout(timer);
      reject(disconnectError);
    }
    // Reject pending session operations
    this.pendingSessionList?.reject(disconnectError);
    this.pendingSessionList = null;
    this.pendingSessionLoad?.reject(disconnectError);
    this.pendingSessionLoad = null;
    this.pendingSessionResume?.reject(disconnectError);
    this.pendingSessionResume = null;

    this.pendingDirListing.clear();
    this.pendingFileRead.clear();
  }
}
