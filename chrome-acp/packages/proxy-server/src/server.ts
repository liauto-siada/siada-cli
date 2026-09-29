import { type ChildProcess } from "node:child_process";
import { createServer as createHttpsServer } from "node:https";
import { connect, createServer as createNetServer } from "node:net";
import { createRequire } from "node:module";
import { homedir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import * as acp from "@agentclientprotocol/sdk";
import { Hono } from "hono";
import { createAdaptorServer, serve } from "@hono/node-server";
import { serveStatic } from "@hono/node-server/serve-static";
import { createNodeWebSocket } from "@hono/node-ws";
import type { WSContext } from "hono/ws";
import type { WebSocket as RawWebSocket } from "ws";
import {
  handleMcpRequest,
  handleBrowserToolResponse,
  executorStatus,
  setDedicatedExecutor,
  setFallbackExecutor,
  setMcpAuthToken,
  unregisterExecutor,
} from "./mcp/handler.js";
import { log } from "./logger.js";
import { renderGhostLogo } from "./ghost-logo.js";
import { getOrCreateCertificate, getLanIPs } from "./cert.js";
import {
  listDir,
  readFile,
  startWatcher,
  type FileChange,
} from "./files.js";
import { appendTrajectoryEvents } from "./trajectory-writer.js";
import { killAgentProcess, launchAgent } from "./agent-connection.js";

// Get the directory of this file to resolve public folder path
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PUBLIC_DIR = join(__dirname, "..", "public");

export interface ServerConfig {
  port: number;
  host: string;
  command: string;
  args: string[];
  cwd: string;
  debug?: boolean;
  token?: string;
  termux?: boolean;
  https?: boolean;
  publicUrl?: string;
}

// Pending permission request
interface PendingPermission {
  resolve: (outcome: { outcome: "cancelled" } | { outcome: "selected"; optionId: string }) => void;
  timeout: ReturnType<typeof setTimeout>;
}

// PromptCapabilities from ACP protocol
// Reference: Zed's prompt_capabilities to check image support
interface PromptCapabilities {
  audio?: boolean;
  embeddedContext?: boolean;
  image?: boolean;
}

// SessionModelState from ACP protocol
// Reference: Zed's AgentModelSelector reads from state.available_models
interface SessionModelState {
  availableModels: Array<{
    modelId: string;
    name: string;
    description?: string | null;
  }>;
  currentModelId: string;
}

// AgentCapabilities from ACP protocol
// Reference: Zed's AcpConnection.agent_capabilities
// Matches SDK's AgentCapabilities exactly
interface AgentCapabilities {
  _meta?: Record<string, unknown> | null;
  loadSession?: boolean;
  mcpCapabilities?: {
    _meta?: Record<string, unknown> | null;
    clientServers?: boolean;
  };
  promptCapabilities?: PromptCapabilities;
  sessionCapabilities?: {
    _meta?: Record<string, unknown> | null;
    fork?: Record<string, unknown> | null;
    list?: Record<string, unknown> | null;
    resume?: Record<string, unknown> | null;
  };
}

// Expand a leading `~` in client-supplied paths. The web client lets users
// type paths like "~/mycli/projects" verbatim, and neither Node's fs APIs nor
// ACP agents (pathlib never expands `~`) handle that form.
function expandHome(path: string): string {
  if (path === "~") return homedir();
  if (path.startsWith("~/") || path.startsWith("~\\")) {
    return join(homedir(), path.slice(2));
  }
  return path;
}

// Track connected clients and their agent connections
interface ClientState {
  process: ChildProcess | null;
  connection: acp.ClientSideConnection | null;
  sessionId: string | null;
  pendingPermissions: Map<string, PendingPermission>;
  // Reference: Zed stores full agentCapabilities from initialize response
  agentCapabilities: AgentCapabilities | null;
  // Reference: Zed stores promptCapabilities from initialize response (convenience accessor)
  promptCapabilities: PromptCapabilities | null;
  // Reference: Zed stores model state from NewSessionResponse.models
  modelState: SessionModelState | null;
  // New-style session config options from NewSessionResponse.configOptions
  // (category="model" select carries model selection for agents like siada
  // that don't implement the legacy `models` field)
  configOptions: acp.SessionConfigOption[] | null;
  // File watcher unsubscribe function
  unsubscribeWatcher: (() => void) | null;
  // Working directory for the current session (used by file explorer)
  sessionCwd: string | null;
  // Heartbeat: tracks whether client responded to the last ping
  isAlive: boolean;
  // Chrome tab id this sidepanel session is attached to (Chrome extension
  // only). Used to route trajectory events to this session's agent
  // subprocess for browser-skill matching (see browser-skill-graph-design.md).
  tabId: number | null;
}

// Module-level state (set when server starts)
let AGENT_COMMAND: string;
let AGENT_ARGS: string[];
let AGENT_CWD: string;
let SERVER_PORT: number;
let SERVER_HOST: string;
let AUTH_TOKEN: string | undefined;

// Proxy version from package.json (createRequire: package.json sits outside
// tsconfig rootDir, so a static import would fail the build)
const require = createRequire(import.meta.url);
const SERVER_VERSION: string = require("../package.json").version as string;

/** MCP endpoint URL handed to agent sessions; carries the auth token (if
 * any) so SDK clients connect without extra header plumbing. Always
 * loopback plaintext: the agent is a local subprocess spawned by this proxy,
 * and the dual-protocol listener keeps plain HTTP available to loopback
 * peers even when TLS is enabled for remote connections. */
function browserMcpUrl(): string {
  const tokenSuffix = AUTH_TOKEN ? `?token=${AUTH_TOKEN}` : "";
  return `http://127.0.0.1:${SERVER_PORT}/mcp${tokenSuffix}`;
}

const clients = new Map<WSContext, ClientState>();

// Chrome tab id -> WSContext, so trajectory events arriving on /ws/trajectory
// (tagged with a tabId by the extension's background worker) can be routed
// to the matching sidepanel session's agent subprocess via extNotification.
// See design_docs/browser-skill-graph-design.md (siada-agenthub repo) §7.1.
const tabIdToWs = new Map<number, WSContext>();

// Permission request timeout (5 minutes)
const PERMISSION_TIMEOUT_MS = 5 * 60 * 1000;

// Heartbeat interval for WebSocket ping/pong (30 seconds)
// Must stay well BELOW the MV3 service-worker idle timeout (30s): the
// app-level ping is what keeps the extension's tool channel alive, and if
// the interval merely equals the idle window a client connecting right after
// a heartbeat tick will sleep before the first ping arrives.
const HEARTBEAT_INTERVAL_MS = 20_000;

// Generate unique request ID
function generateRequestId(): string {
  return `perm_${Date.now()}_${Math.random().toString(36).slice(2, 11)}`;
}

// Send a message to the WebSocket client
function send(ws: WSContext, type: string, payload?: unknown): void {
  if (ws.readyState === 1) {
    // WebSocket.OPEN
    ws.send(JSON.stringify({ type, payload }));
  }
}

// Get the working directory for a client's session
function getClientCwd(ws: WSContext): string {
  const state = clients.get(ws);
  return state?.sessionCwd || AGENT_CWD;
}

// Create a Client implementation that forwards events to WebSocket
function createClient(ws: WSContext, clientState: ClientState): acp.Client {
  return {
    async requestPermission(params) {
      const requestId = generateRequestId();
      log.debug("Permission requested", { requestId, title: params.toolCall.title });

      // Create a promise that will be resolved when user responds
      const outcomePromise = new Promise<{ outcome: "cancelled" } | { outcome: "selected"; optionId: string }>((resolve) => {
        // Set timeout to auto-cancel if no response
        const timeout = setTimeout(() => {
          log.warn("Permission request timed out", { requestId });
          clientState.pendingPermissions.delete(requestId);
          resolve({ outcome: "cancelled" });
        }, PERMISSION_TIMEOUT_MS);

        // Store the pending request in client's map
        clientState.pendingPermissions.set(requestId, { resolve, timeout });
      });

      // Send permission request to client with our requestId
      send(ws, "permission_request", {
        requestId,
        sessionId: params.sessionId,
        options: params.options,
        toolCall: params.toolCall,
      });

      // Wait for user response
      const outcome = await outcomePromise;
      log.debug("Permission response received", { requestId, outcome });

      return { outcome };
    },

    async sessionUpdate(params) {
      send(ws, "session_update", params);
    },

    async readTextFile(params) {
      log.debug("Read file", { path: params.path });
      // TODO: Forward to extension to read file
      return { content: "" };
    },

    async writeTextFile(params) {
      log.debug("Write file", { path: params.path });
      // TODO: Forward to extension to write file
      return {};
    },
  };
}

// Handle permission response from client
function handlePermissionResponse(ws: WSContext, payload: { requestId: string; outcome: { outcome: "cancelled" } | { outcome: "selected"; optionId: string } }): void {
  const state = clients.get(ws);
  if (!state) {
    log.warn("Permission response from unknown client");
    return;
  }

  const pending = state.pendingPermissions.get(payload.requestId);
  if (!pending) {
    log.warn("Permission response for unknown request", { requestId: payload.requestId });
    return;
  }

  // Clear timeout and resolve the promise
  clearTimeout(pending.timeout);
  state.pendingPermissions.delete(payload.requestId);
  pending.resolve(payload.outcome);
}

// Forward a batch of trajectory events to the agent subprocess(es) whose
// sidepanel session is attached to the originating tab (via extNotification,
// method "trajectory_event"). Events are grouped by tabId since a single
// batch pushed by the extension's background worker may span multiple tabs.
// Tabs with no live mapped session (no sidepanel open, or agent not
// connected) are silently skipped — trajectory events are still persisted to
// disk by appendTrajectoryEvents() regardless.
// See design_docs/browser-skill-graph-design.md (siada-agenthub repo) §7.1.
function forwardTrajectoryEventsToAgents(events: unknown[]): void {
  const byTabId = new Map<number, unknown[]>();
  for (const event of events) {
    const tabId = (event as { tabId?: unknown } | null)?.tabId;
    if (typeof tabId !== "number") continue;
    const bucket = byTabId.get(tabId);
    if (bucket) bucket.push(event);
    else byTabId.set(tabId, [event]);
  }

  for (const [tabId, tabEvents] of byTabId) {
    const ws = tabIdToWs.get(tabId);
    if (!ws) continue;
    const state = clients.get(ws);
    if (!state?.connection) continue;
    log.info("[STEP 8] proxy -> agent extNotification _trajectory_event", {
      tabId,
      count: tabEvents.length,
    });
    // ACP extension methods must use a leading-underscore method name per
    // the protocol's extensibility convention; the Python-side router
    // strips it before calling Agent.ext_notification(method, params), so
    // the handler there sees plain "trajectory_event".
    state.connection
      .extNotification("_trajectory_event", { tabId, events: tabEvents })
      .catch((error: unknown) => {
        log.debug("Failed to forward trajectory_event to agent", {
          tabId,
          error: String(error),
        });
      });
  }
}

// Cancel all pending permissions for a client (called on disconnect)
function cancelPendingPermissions(clientState: ClientState): void {
  for (const [requestId, pending] of clientState.pendingPermissions) {
    log.debug("Cancelling pending permission due to disconnect", { requestId });
    clearTimeout(pending.timeout);
    pending.resolve({ outcome: "cancelled" });
  }
  clientState.pendingPermissions.clear();
}

async function handleConnect(ws: WSContext): Promise<void> {
  const state = clients.get(ws);
  if (!state) return;

  // Kill existing process if any
  if (state.process) {
    // Cancel any pending permission requests from previous connection
    cancelPendingPermissions(state);
    killAgentProcess(state.process);
    state.process = null;
    state.connection = null;
  }

  try {
    const launched = await launchAgent({
      command: AGENT_COMMAND,
      args: AGENT_ARGS,
      cwd: AGENT_CWD,
      clientFactory: (_agent) => createClient(ws, state),
      onSpawned: (process, connection) => {
        state.process = process;
        state.connection = connection;
      },
    });

    // Reference: Zed stores full agentCapabilities from initialize response
    // This includes loadSession, promptCapabilities, sessionCapabilities, etc.
    const agentCaps = launched.initResult.agentCapabilities;
    state.agentCapabilities = agentCaps ? {
      _meta: agentCaps._meta,
      loadSession: agentCaps.loadSession,
      mcpCapabilities: agentCaps.mcpCapabilities,
      promptCapabilities: agentCaps.promptCapabilities,
      sessionCapabilities: agentCaps.sessionCapabilities,
    } : null;
    state.promptCapabilities = agentCaps?.promptCapabilities ?? null;

    log.info("Agent initialized", {
      protocolVersion: launched.initResult.protocolVersion,
      loadSession: state.agentCapabilities?.loadSession,
      sessionList: !!state.agentCapabilities?.sessionCapabilities?.list,
      sessionResume: !!state.agentCapabilities?.sessionCapabilities?.resume,
      promptCapabilities: state.promptCapabilities,
      mcpCapabilities: state.agentCapabilities?.mcpCapabilities,
    });

    send(ws, "status", {
      connected: true,
      agentInfo: launched.initResult.agentInfo,
      capabilities: state.agentCapabilities,
    });

    // Handle connection close
    launched.connection.closed.then(() => {
      log.info("Agent connection closed");
      state.connection = null;
      state.sessionId = null;
      send(ws, "status", { connected: false });
    });
  } catch (error) {
    // The agent failed to start (bad command, crash during initialization)
    // or initialize was rejected. Clean up and forward the reason to the
    // client — otherwise the sidepanel stays on "Connecting..." forever.
    // (Cast: TS narrows state.process to null after the early-kill block,
    // but onSpawned may have assigned a live process in between.)
    killAgentProcess(state.process as ChildProcess | null);
    state.process = null;
    state.connection = null;
    log.error("Failed to connect", { error: (error as Error).message });
    send(ws, "error", {
      message: `Failed to connect: ${(error as Error).message}`,
    });
  }
}

async function handleNewSession(
  ws: WSContext,
  params: { cwd?: string; tabId?: number },
): Promise<void> {
  const state = clients.get(ws);
  if (!state?.connection) {
    send(ws, "error", { message: "Not connected to agent" });
    return;
  }

  try {
    const sessionCwd = expandHome(params.cwd || AGENT_CWD);

    // Record the tab <-> session mapping (Chrome extension only; web-client
    // callers omit tabId). Clears any stale mapping for this ws first so a
    // "new session" replacing an old one doesn't leave two tabIds pointing
    // at the same connection.
    if (state.tabId !== null) tabIdToWs.delete(state.tabId);
    state.tabId = typeof params.tabId === "number" ? params.tabId : null;
    if (state.tabId !== null) tabIdToWs.set(state.tabId, ws);
    const mcpServers = [
      {
        type: "http" as const,
        url: browserMcpUrl(),
        name: "browser",
        headers: [],
      },
    ];
    const result = await state.connection.newSession({
      cwd: sessionCwd,
      mcpServers,
      // Forwarded via ACP's standard `_meta` extensibility field (not part
      // of the spec, but explicitly supported for this purpose) so the
      // Python agent can associate this session with a tab for browser
      // skill matching. See design_docs/browser-skill-graph-design.md §7.2.
      _meta: state.tabId !== null ? { tabId: state.tabId } : undefined,
    });

    state.sessionId = result.sessionId;
    state.sessionCwd = sessionCwd;
    // Reference: Zed stores model state from NewSessionResponse.models
    state.modelState = result.models ?? null;
    // Reference: Zed's config_state() also reads response.config_options
    state.configOptions = result.configOptions ?? null;
    log.info("Session created", { sessionId: result.sessionId, cwd: sessionCwd, hasModels: !!result.models, hasConfigOptions: !!result.configOptions });

    // Restart file watcher with the new session cwd
    if (state.unsubscribeWatcher) {
      state.unsubscribeWatcher();
    }
    state.unsubscribeWatcher = await startWatcher(sessionCwd, (changes) => {
      send(ws, "file_changes", { changes });
    });

    // Send fresh root directory listing for the new session cwd
    // This ensures the file explorer shows the correct files immediately
    const rootItems = listDir(sessionCwd, "");
    if (rootItems !== null) {
      send(ws, "dir_listing", { path: "", items: rootItems });
    }

    // Reference: Include promptCapabilities so client can check image support
    // This matches Zed's behavior of checking prompt_capabilities.image
    // Also include models state for model selection support
    send(ws, "session_created", {
      ...result,
      promptCapabilities: state.promptCapabilities,
      models: state.modelState,
      configOptions: state.configOptions,
    });
  } catch (error) {
    log.error("Failed to create session", { error: (error as Error).message });
    send(ws, "error", {
      message: `Failed to create session: ${(error as Error).message}`,
    });
  }
}

// ============================================================================
// Session History Operations
// Reference: Zed's AgentConnection trait - list_sessions, load_session, resume_session
// ============================================================================

/**
 * List sessions from the agent.
 * Reference: Zed's AcpSessionList.list_sessions()
 */
async function handleListSessions(
  ws: WSContext,
  params: { cwd?: string; cursor?: string },
): Promise<void> {
  const state = clients.get(ws);
  if (!state?.connection) {
    send(ws, "error", { message: "Not connected to agent" });
    return;
  }

  // Default to this client's current working directory so the history list
  // only shows sessions belonging to the workspace the user is in — agents
  // with cross-project disk scans (e.g. siada's /resume browser) otherwise
  // return every session on the machine, which is both noisy and slow.
  // Reference: Zed passes the connection's cwd to session/list.
  const effectiveParams = {
    cwd: params.cwd ?? getClientCwd(ws),
    cursor: params.cursor,
  };

  // Check if agent supports listing sessions
  // Reference: Zed checks agent_capabilities.session_capabilities.list
  if (!state.agentCapabilities?.sessionCapabilities?.list) {
    send(ws, "error", { message: "Listing sessions is not supported by this agent" });
    return;
  }

  try {
    // Note: SDK uses unstable_listSessions until API is finalized
    const result = await state.connection.unstable_listSessions({
      cwd: effectiveParams.cwd,
      cursor: effectiveParams.cursor,
    });

    log.info("Sessions listed", { count: result.sessions.length, hasMore: !!result.nextCursor });

    // Map SDK's SessionInfo to our AgentSessionInfo
    // Reference: Zed's AgentSessionList.list_sessions maps acp::SessionInfo -> AgentSessionInfo
    send(ws, "session_list", {
      sessions: result.sessions.map((s: acp.SessionInfo) => ({
        _meta: s._meta,
        cwd: s.cwd,  // Required field in SDK's SessionInfo
        sessionId: s.sessionId,
        title: s.title,
        updatedAt: s.updatedAt,
      })),
      nextCursor: result.nextCursor,
      _meta: result._meta,
    });
  } catch (error) {
    log.error("Failed to list sessions", { error: (error as Error).message });
    send(ws, "error", {
      message: `Failed to list sessions: ${(error as Error).message}`,
    });
  }
}

/**
 * Load an existing session with history replay.
 * Reference: Zed's AcpConnection.load_session()
 */
async function handleLoadSession(
  ws: WSContext,
  params: { sessionId: string; cwd?: string; _meta?: { tabId?: number } | null },
): Promise<void> {
  const state = clients.get(ws);
  if (!state?.connection) {
    send(ws, "error", { message: "Not connected to agent" });
    return;
  }

  // Check if agent supports loading sessions
  // Reference: Zed checks agent_capabilities.load_session
  if (!state.agentCapabilities?.loadSession) {
    send(ws, "error", { message: "Loading sessions is not supported by this agent" });
    return;
  }

  try {
    const sessionCwd = expandHome(params.cwd || AGENT_CWD);
    const sessionId = params.sessionId;

    // Re-bind this ws to the tab declared in _meta (sidepanel reopen path),
    // mirroring handleNewSession: without this, a restored session silently
    // stops receiving trajectory events for its tab. Web clients without a
    // tabId clear any stale binding.
    const metaTabId = params._meta?.tabId;
    if (state.tabId !== null) tabIdToWs.delete(state.tabId);
    state.tabId = typeof metaTabId === "number" ? metaTabId : null;
    if (state.tabId !== null) tabIdToWs.set(state.tabId, ws);

    const result = await state.connection.loadSession({
      sessionId,
      cwd: sessionCwd,
      // Forwarded via ACP's standard `_meta` extensibility field so the
      // Python agent can associate the restored session with its tab (same
      // mechanism as new_session; see browser-skill-graph-design.md §7.2).
      _meta: state.tabId !== null ? { tabId: state.tabId } : undefined,
      mcpServers: [
        {
          type: "http",
          url: browserMcpUrl(),
          name: "browser",
          headers: [],
        },
      ],
    });

    state.sessionId = sessionId;
    state.sessionCwd = sessionCwd;
    // Reference: acp.rs line 659-665 - config_state(response.modes, response.models, response.config_options)
    state.modelState = result.models ?? null;
    state.configOptions = result.configOptions ?? null;
    log.info("Session loaded", { sessionId, cwd: sessionCwd });

    // Restart file watcher with the session cwd
    if (state.unsubscribeWatcher) {
      state.unsubscribeWatcher();
    }
    state.unsubscribeWatcher = await startWatcher(sessionCwd, (changes) => {
      send(ws, "file_changes", { changes });
    });

    // Send fresh root directory listing
    const rootItems = listDir(sessionCwd, "");
    if (rootItems !== null) {
      send(ws, "dir_listing", { path: "", items: rootItems });
    }

    send(ws, "session_loaded", {
      sessionId,
      promptCapabilities: state.promptCapabilities,
      models: state.modelState,
      configOptions: state.configOptions,
    });
  } catch (error) {
    log.error("Failed to load session", { error: (error as Error).message });
    send(ws, "error", {
      message: `Failed to load session: ${(error as Error).message}`,
    });
  }
}

/**
 * Resume an existing session without history replay.
 * Reference: Zed's AcpConnection.resume_session()
 */
async function handleResumeSession(
  ws: WSContext,
  params: { sessionId: string; cwd?: string },
): Promise<void> {
  const state = clients.get(ws);
  if (!state?.connection) {
    send(ws, "error", { message: "Not connected to agent" });
    return;
  }

  // Check if agent supports resuming sessions
  // Reference: Zed checks agent_capabilities.session_capabilities.resume
  if (!state.agentCapabilities?.sessionCapabilities?.resume) {
    send(ws, "error", { message: "Resuming sessions is not supported by this agent" });
    return;
  }

  try {
    const sessionCwd = expandHome(params.cwd || AGENT_CWD);
    const sessionId = params.sessionId;
    // Note: SDK uses unstable_resumeSession until API is finalized
    const result = await state.connection.unstable_resumeSession({
      sessionId,
      cwd: sessionCwd,
      mcpServers: [
        {
          type: "http",
          url: browserMcpUrl(),
          name: "browser",
          headers: [],
        },
      ],
    });

    state.sessionId = sessionId;
    state.sessionCwd = sessionCwd;
    // Reference: acp.rs line 736-742 - config_state(response.modes, response.models, response.config_options)
    state.modelState = result.models ?? null;
    state.configOptions = result.configOptions ?? null;
    log.info("Session resumed", { sessionId, cwd: sessionCwd });

    // Restart file watcher with the session cwd
    if (state.unsubscribeWatcher) {
      state.unsubscribeWatcher();
    }
    state.unsubscribeWatcher = await startWatcher(sessionCwd, (changes) => {
      send(ws, "file_changes", { changes });
    });

    // Send fresh root directory listing
    const rootItems = listDir(sessionCwd, "");
    if (rootItems !== null) {
      send(ws, "dir_listing", { path: "", items: rootItems });
    }

    send(ws, "session_resumed", {
      sessionId,
      promptCapabilities: state.promptCapabilities,
      models: state.modelState,
      configOptions: state.configOptions,
    });
  } catch (error) {
    log.error("Failed to resume session", { error: (error as Error).message });
    send(ws, "error", {
      message: `Failed to resume session: ${(error as Error).message}`,
    });
  }
}

// Reference: Zed's AcpThread.send() forwards Vec<acp::ContentBlock> to agent
async function handlePrompt(
  ws: WSContext,
  params: { content: ContentBlock[] },
): Promise<void> {
  const state = clients.get(ws);
  if (!state?.connection || !state.sessionId) {
    send(ws, "error", { message: "No active session" });
    return;
  }

  try {
    // Log content blocks for debugging
    const firstText = params.content.find(b => b.type === "text")?.text;
    const images = params.content.filter(b => b.type === "image");
    log.debug("Sending prompt", {
      text: firstText?.slice(0, 100),
      imageCount: images.length,
      blockCount: params.content.length,
    });

    // Log image details for debugging
    for (const img of images) {
      log.debug("Image block", {
        mimeType: img.mimeType,
        dataLength: img.data?.length,
        dataSizeKB: img.data ? Math.round(img.data.length * 0.75 / 1024) : 0, // base64 to bytes approx
        dataPrefix: img.data?.slice(0, 50),
      });
    }

    // Forward ContentBlock[] directly to agent (matches Zed's behavior)
    const result = await state.connection.prompt({
      sessionId: state.sessionId,
      prompt: params.content as acp.ContentBlock[],
    });

    log.info("Prompt completed", { stopReason: result.stopReason });
    send(ws, "prompt_complete", result);
  } catch (error) {
    log.error("Prompt failed", { error: (error as Error).message });
    send(ws, "error", {
      message: `Prompt failed: ${(error as Error).message}`,
    });
    // Always send a terminal prompt_complete so clients can clear their
    // loading state. Without this, a failed prompt leaves the UI stuck
    // in "thinking" forever (no prompt_complete ever arrives).
    send(ws, "prompt_complete", { stopReason: "error" });
  }
}

function handleDisconnect(ws: WSContext): void {
  const state = clients.get(ws);
  if (!state) return;

  if (state.process) {
    killAgentProcess(state.process);
    state.process = null;
  }
  state.connection = null;
  state.sessionId = null;

  send(ws, "status", { connected: false });
}

// Handle cancel request from client - matches Zed's cancel() logic
// 1. Cancel any pending permission requests
// 2. Send session/cancel notification to agent via ACP SDK
// The agent should respond to the original prompt with stopReason="cancelled"
async function handleCancel(ws: WSContext): Promise<void> {
  const state = clients.get(ws);
  if (!state?.connection || !state.sessionId) {
    log.warn("Cancel requested but no active session");
    return;
  }

  log.info("Cancel requested", { sessionId: state.sessionId });

  // Cancel any pending permission requests (like Zed does)
  // This ensures permission dialogs are dismissed
  cancelPendingPermissions(state);

  try {
    // Send cancel notification to agent via ACP SDK
    // The agent should:
    // 1. Stop all language model requests
    // 2. Abort all tool call invocations in progress
    // 3. Send any pending session/update notifications
    // 4. Respond to the original session/prompt with stopReason="cancelled"
    await state.connection.cancel({ sessionId: state.sessionId });
    log.debug("Cancel notification sent to agent");
  } catch (error) {
    log.error("Failed to send cancel notification", { error: (error as Error).message });
    // Don't send error to client - the prompt will complete with appropriate status
  }
}

// Reference: Zed's AgentModelSelector.select_model() calls connection.set_session_model()
async function handleSetSessionModel(
  ws: WSContext,
  params: { modelId: string },
): Promise<void> {
  const state = clients.get(ws);
  if (!state?.connection || !state.sessionId) {
    send(ws, "error", { message: "No active session" });
    return;
  }

  if (!state.modelState) {
    send(ws, "error", { message: "Model selection not supported by this agent" });
    return;
  }

  try {
    log.info("Setting session model", { sessionId: state.sessionId, modelId: params.modelId });
    await state.connection.unstable_setSessionModel({
      sessionId: state.sessionId,
      modelId: params.modelId,
    });
    // Update local model state
    state.modelState = {
      ...state.modelState,
      currentModelId: params.modelId,
    };
    send(ws, "model_changed", { modelId: params.modelId });
    log.info("Model changed successfully", { modelId: params.modelId });
  } catch (error) {
    log.error("Failed to set model", { error: (error as Error).message });
    send(ws, "error", {
      message: `Failed to set model: ${(error as Error).message}`,
    });
  }
}

// New-style model selection via session/set_config_option.
// Used when the agent exposes models as a category="model" select in
// configOptions instead of the legacy `models` field (e.g. siada-agenthub).
async function handleSetConfigOption(
  ws: WSContext,
  params: { configId: string; value: string },
): Promise<void> {
  const state = clients.get(ws);
  if (!state?.connection || !state.sessionId) {
    send(ws, "error", { message: "No active session" });
    return;
  }

  try {
    log.info("Setting session config option", {
      sessionId: state.sessionId,
      configId: params.configId,
      value: params.value,
    });
    const result = await state.connection.setSessionConfigOption({
      sessionId: state.sessionId,
      configId: params.configId,
      value: params.value,
    });
    // The response carries the full updated config option set
    state.configOptions = result.configOptions ?? null;
    const updated = state.configOptions?.find((o) => o.id === params.configId);
    const currentValue = updated?.currentValue ?? params.value;
    if (updated?.category === "model") {
      send(ws, "model_changed", { modelId: currentValue });
    }
    log.info("Config option changed successfully", { configId: params.configId, currentValue });
  } catch (error) {
    log.error("Failed to set config option", { error: (error as Error).message });
    send(ws, "error", {
      message: `Failed to set config option: ${(error as Error).message}`,
    });
  }
}

// ============================================================================
// File Explorer Handlers
// ============================================================================

function handleListDir(ws: WSContext, payload: { path: string }): void {
  const cwd = getClientCwd(ws);
  const items = listDir(cwd, payload.path);
  if (items === null) {
    log.debug(`list_dir failed: ${payload.path || "(root)"}`);
    send(ws, "error", { message: `list_dir failed: ${payload.path || "(root)"}` });
    return;
  }
  send(ws, "dir_listing", { path: payload.path, items });
}

function handleReadFile(ws: WSContext, payload: { path: string }): void {
  const cwd = getClientCwd(ws);
  const content = readFile(cwd, payload.path);
  if (content === null) {
    send(ws, "error", { message: "Access denied or file not found" });
    return;
  }
  send(ws, "file_content", content);
}

// ContentBlock type matching @agentclientprotocol/sdk
// Reference: Zed's acp::ContentBlock
interface ContentBlock {
  type: string;
  text?: string;
  data?: string;
  mimeType?: string;
  uri?: string;
  name?: string;
}

interface ProxyMessage {
  type: "connect" | "disconnect" | "new_session" | "prompt" | "cancel" | "set_session_model";
  payload?: { cwd?: string } | { content: ContentBlock[] } | { modelId: string };
}

// Launch PWA via Termux am command
async function launchTermuxPwa(pwaName: string): Promise<void> {
  const { exec } = await import("node:child_process");
  const { promisify } = await import("node:util");
  const execAsync = promisify(exec);

  try {
    // Find WebAPK package by app name using aapt
    const { stdout: packagesOutput } = await execAsync(
      "pm list packages 2>/dev/null | grep webapk | cut -d: -f2"
    );
    const packages = packagesOutput.trim().split("\n").filter(Boolean);

    for (const pkg of packages) {
      try {
        // Get APK path
        const { stdout: pathOutput } = await execAsync(`pm path ${pkg} 2>/dev/null | cut -d: -f2`);
        const apkPath = pathOutput.trim();
        if (!apkPath) continue;

        // Check app label using aapt
        const { stdout: aaptOutput } = await execAsync(`aapt dump badging "${apkPath}" 2>/dev/null`);
        const labelMatch = aaptOutput.match(/application-label:'([^']+)'/);
        if (labelMatch && labelMatch[1] === pwaName) {
          // Found the PWA, launch it
          const activityMatch = aaptOutput.match(/launchable-activity: name='([^']+)'/);
          if (activityMatch) {
            const activity = activityMatch[1];
            await execAsync(`am start -n ${pkg}/${activity}`);
            log.info("Launched PWA via Termux", { package: pkg, activity });
            console.log(`📱 Launched PWA: ${pwaName}`);
            return;
          }
        }
      } catch {
        // Skip this package if any error
        continue;
      }
    }
    log.warn("PWA not found", { name: pwaName });
    console.log(`⚠️  PWA "${pwaName}" not found`);
  } catch (error) {
    log.error("Failed to launch PWA", { error: (error as Error).message });
    console.log(`⚠️  Failed to launch PWA: ${(error as Error).message}`);
  }
}

export async function startServer(config: ServerConfig): Promise<void> {
  const { port, host, command, args, cwd, token, termux, https, publicUrl } = config;

  // Set module-level config
  AGENT_COMMAND = command;
  AGENT_ARGS = args;
  AGENT_CWD = cwd;
  SERVER_PORT = port;
  SERVER_HOST = host;
  AUTH_TOKEN = token;
  setMcpAuthToken(token);

  const app = new Hono();
  const { injectWebSocket, upgradeWebSocket } = createNodeWebSocket({ app });

  // Health check endpoint
  app.get("/health", (c) => {
    return c.json({ status: "ok" });
  });

  // Status endpoint for setup verification (e.g. `siada browser setup`
  // polls it until the extension's tool channel registers).
  app.get("/status", (c) => {
    const executor = executorStatus();
    return c.json({
      status: "ok",
      version: SERVER_VERSION,
      port: SERVER_PORT,
      host: SERVER_HOST,
      authEnabled: !!AUTH_TOKEN,
      extensionConnected: executor.connected,
      executor,
      agentSessions: [...clients.values()].filter((s) => s.process !== null).length,
      clients: clients.size,
    });
  });

  // Root endpoint - redirect to PWA
  app.get("/", (c) => {
    return c.redirect("/app/");
  });

  // MCP Streamable HTTP endpoint for browser tool
  app.post("/mcp", handleMcpRequest);

  // Serve PWA from /app (use absolute path so it works from any CWD)
  app.use("/app/*", serveStatic({
    root: PUBLIC_DIR,
    rewriteRequestPath: (path) => path.replace(/^\/app/, ""),
  }));

  // Redirect /app to /app/ for clean URLs
  app.get("/app", (c) => c.redirect("/app/"));

  // WebSocket endpoint with token validation
  app.get(
    "/ws",
    upgradeWebSocket((c) => {
      // Validate token before upgrade if auth is enabled
      if (AUTH_TOKEN) {
        const url = new URL(c.req.url);
        const providedToken = url.searchParams.get("token");
        if (providedToken !== AUTH_TOKEN) {
          log.warn("WebSocket connection rejected: invalid token");
          // Return empty handlers - connection will be rejected
          return {
            onOpen(_event, ws) {
              ws.close(4001, "Unauthorized: Invalid token");
            },
            onMessage() {},
            onClose() {},
          };
        }
      }

      return {
        onOpen(_event, ws) {
          log.info("Client connected");
          const state: ClientState = {
            process: null,
            connection: null,
            sessionId: null,
            pendingPermissions: new Map(),
            agentCapabilities: null,
            promptCapabilities: null,
            modelState: null,
            configOptions: null,
            unsubscribeWatcher: null,
            sessionCwd: null,
            isAlive: true,
            tabId: null,
          };
          clients.set(ws, state);

          // Listen for protocol-level pong frames to track liveness
          const rawWs = ws.raw as RawWebSocket;
          rawWs.on("pong", () => {
            state.isAlive = true;
          });

          // Register as fallback executor for browser tool calls (legacy
          // sidepanel behavior; dedicated executors register explicitly)
          setFallbackExecutor(ws);
        },
      async onMessage(event, ws) {
        try {
          const data = JSON.parse(event.data.toString());
          log.debug("Received message", { type: data.type });

          switch (data.type) {
            case "connect":
              await handleConnect(ws);
              break;
            case "disconnect":
              handleDisconnect(ws);
              break;
            case "new_session":
              await handleNewSession(
                ws,
                (data.payload as { cwd?: string; tabId?: number }) || {},
              );
              break;
            case "prompt":
              await handlePrompt(ws, data.payload as { content: ContentBlock[] });
              break;
            case "browser_tool_result":
              // Handle response from extension for browser tool call
              log.trace("Raw browser_tool_result from extension", {
                callId: data.callId,
                result: data.result,
              });
              handleBrowserToolResponse(data.callId, data.result);
              break;
            case "register_executor":
              // Dedicated tool channel (extension background service worker).
              // Preferred executor; never sends "connect", so no agent spawn.
              setDedicatedExecutor(ws);
              log.info("Dedicated executor registered");
              send(ws, "executor_registered");
              break;
            case "permission_response":
              // Handle user's permission decision
              handlePermissionResponse(ws, data.payload);
              break;
            case "cancel":
              // Handle cancel request - send session/cancel to agent
              await handleCancel(ws);
              break;
            case "set_session_model":
              // Handle model selection request
              await handleSetSessionModel(ws, data.payload as { modelId: string });
              break;
            case "set_config_option":
              // Handle new-style model selection via session/set_config_option
              await handleSetConfigOption(ws, data.payload as { configId: string; value: string });
              break;
            // Session history operations - Reference: Zed's AgentSessionList
            case "list_sessions":
              await handleListSessions(ws, (data.payload as { cwd?: string; cursor?: string }) || {});
              break;
            case "load_session":
              await handleLoadSession(
                ws,
                data.payload as { sessionId: string; cwd?: string; _meta?: { tabId?: number } | null },
              );
              break;
            case "resume_session":
              await handleResumeSession(ws, data.payload as { sessionId: string; cwd?: string });
              break;
            case "list_dir":
              handleListDir(ws, data.payload as { path: string });
              break;
            case "read_file":
              handleReadFile(ws, data.payload as { path: string });
              break;
            case "ping":
              send(ws, "pong");
              break;
            case "pong":
              // Reply to the app-level heartbeat (see HEARTBEAT_INTERVAL_MS);
              // nothing to track — protocol-level pong already flips isAlive.
              break;
            default:
              send(ws, "error", {
                message: `Unknown message type: ${data.type}`,
              });
          }
        } catch (error) {
          log.error("WebSocket message error", { error: (error as Error).message });
          send(ws, "error", { message: `Error: ${(error as Error).message}` });
        }
      },
      onClose(_event, ws) {
        log.info("Client disconnected");
        const state = clients.get(ws);
        if (state) {
          // Cancel any pending permission requests
          cancelPendingPermissions(state);
          // Unsubscribe from file watcher
          state.unsubscribeWatcher?.();
          // Remove the tab <-> session mapping so trajectory events for this
          // tab stop being forwarded to a dead connection.
          if (state.tabId !== null) tabIdToWs.delete(state.tabId);
        }
        handleDisconnect(ws);
        clients.delete(ws);
        // Drop this WS from whichever executor slot it occupied (dedicated
        // tool channel or fallback); other executors stay registered.
        unregisterExecutor(ws);
      },
    };
    }),
  );

  // Dedicated WebSocket endpoint for trajectory recording events pushed by
  // the extension's background service worker. Kept separate from /ws so it
  // never interferes with the extension registration used for browser tools.
  app.get(
    "/ws/trajectory",
    upgradeWebSocket(() => ({
      onOpen() {
        log.info("Trajectory WS connected");
      },
      onMessage(event) {
        try {
          const data = JSON.parse(event.data.toString());
          if (data.type === "trajectory_events" && Array.isArray(data.payload)) {
            log.info("[STEP 6] proxy received trajectory events", { count: data.payload.length });
            appendTrajectoryEvents(data.payload);
            forwardTrajectoryEventsToAgents(data.payload);
          }
        } catch (error) {
          log.warn("Failed to handle trajectory message", { error: String(error) });
        }
      },
      onClose() {
        log.info("Trajectory WS closed");
      },
    })),
  );

  // Create server with optional HTTPS. With --https the port speaks BOTH
  // protocols: a raw net listener peeks the first byte of every connection
  // (0x16 = TLS ClientHello) and pipes it to a TLS server or a plain HTTP
  // server, both bound to private loopback ports. Loopback clients (the
  // extension on this machine, the local agent subprocess) keep zero-setup
  // ws/http, while remote peers get TLS. Plaintext from non-loopback peers
  // is refused so LAN traffic stays encrypted — the same guarantee the old
  // TLS-only port gave.
  if (https) {
    const tlsOptions = await getOrCreateCertificate();
    const tlsServer = createAdaptorServer({
      fetch: app.fetch,
      createServer: createHttpsServer,
      serverOptions: tlsOptions,
    });
    const plainServer = createAdaptorServer({ fetch: app.fetch });
    injectWebSocket(tlsServer);
    injectWebSocket(plainServer);
    await new Promise<void>((resolve) => tlsServer.listen(0, "127.0.0.1", resolve));
    await new Promise<void>((resolve) => plainServer.listen(0, "127.0.0.1", resolve));
    const tlsPort = (tlsServer.address() as { port: number }).port;
    const plainPort = (plainServer.address() as { port: number }).port;
    const isLoopbackPeer = (address: string | undefined): boolean => {
      const peer = (address ?? "").replace(/^::ffff:/, "");
      return peer === "::1" || peer.startsWith("127.");
    };
    const sniffer = createNetServer((socket) => {
      socket.on("error", () => socket.destroy());
      socket.once("data", (chunk: Buffer) => {
        const isTls = chunk.length > 0 && chunk[0] === 0x16;
        if (!isTls && !isLoopbackPeer(socket.remoteAddress)) {
          log.warn("Refused plaintext connection from non-loopback peer", {
            remoteAddress: socket.remoteAddress,
          });
          socket.destroy();
          return;
        }
        // The first chunk already put the socket into flowing mode, so any
        // further chunks that arrive while connect() is still in flight (e.g.
        // an MCP POST whose headers and body land as two TCP segments) would
        // be dropped without a 'data' listener, leaving the upstream server
        // waiting forever for the request body. Buffer everything until the
        // upstream is ready, then flush.
        const pending: Buffer[] = [chunk];
        socket.on("data", (c: Buffer) => pending.push(c));
        const upstream = connect({ host: "127.0.0.1", port: isTls ? tlsPort : plainPort }, () => {
          while (pending.length > 0) upstream.write(pending.shift()!);
          socket.pipe(upstream).pipe(socket);
        });
        // Tear both sides down together: a failure on either end must not
        // leave the other half hanging.
        upstream.on("error", () => socket.destroy());
        upstream.on("close", () => socket.destroy());
        socket.on("close", () => upstream.destroy());
      });
    });
    sniffer.listen(port, host);
  } else {
    const server = serve({ fetch: app.fetch, port, hostname: host });
    injectWebSocket(server);
  }

  // Heartbeat: periodically ping all connected clients to keep
  // connections alive through intermediate gateways and detect dead clients.
  // Two layers, both required:
  //  - Protocol-level ws ping (below): detects dead peers via the isAlive
  //    pong flag.
  //  - Application-level {type:"ping"} JSON message: MV3 extension service
  //    workers only reset their 30s idle timer when a WebSocket message is
  //    DELIVERED to onmessage — protocol pings are handled by the network
  //    stack and never wake the worker. Without the app-level ping the
  //    service worker (and with it the browser-tool channel) dies every 30s.
  setInterval(() => {
    for (const [ws, state] of clients) {
      if (!state.isAlive) {
        log.info("Client heartbeat timeout, terminating connection");
        const rawWs = ws.raw as RawWebSocket;
        rawWs.terminate();
        continue;
      }
      state.isAlive = false;
      (ws.raw as RawWebSocket).ping();
      send(ws, "ping");
    }
  }, HEARTBEAT_INTERVAL_MS);

  // Protocol strings for NETWORK URLs. Local URLs stay plain: the
  // dual-protocol listener keeps loopback ws/http working with zero
  // certificate setup even in --https mode.
  const httpProtocol = https ? "https" : "http";
  const wsProtocol = https ? "wss" : "ws";

  // Get actual LAN IP when binding to 0.0.0.0
  let displayHost = host;
  if (host === "0.0.0.0") {
    const lanIPs = getLanIPs();
    displayHost = lanIPs[0] || "localhost";
  }

  // Build URLs
  const localWsUrl = `ws://localhost:${port}/ws`;
  const networkWsUrl = `${wsProtocol}://${displayHost}:${port}/ws`;
  const localAppUrl = `http://localhost:${port}/app`;
  const networkAppUrl = `${httpProtocol}://${displayHost}:${port}/app`;
  const tokenSuffix = AUTH_TOKEN ? `?token=${AUTH_TOKEN}` : "";

  // Print startup banner
  console.log();
  for (const line of renderGhostLogo(process.stdout.isTTY)) {
    console.log(line);
  }
  console.log();
  console.log(`  🚀 ACP Proxy Server${https ? " (HTTPS + loopback ws)" : ""}`);
  console.log();

  // One-click URLs (open in browser)
  console.log(`  Open in browser:`);
  console.log(`    ➜ Local:   ${localAppUrl}${tokenSuffix}`);
  if (host === "0.0.0.0") {
    console.log(`    ➜ Network: ${networkAppUrl}${tokenSuffix}`);
  }
  console.log();

  // Manual connection info (for form input)
  console.log(`  Manual connection:`);
  if (host === "0.0.0.0") {
    console.log(`    URL:   ${networkWsUrl}`);
  } else {
    console.log(`    URL:   ${localWsUrl}`);
  }
  if (AUTH_TOKEN) {
    console.log(`    Token: ${AUTH_TOKEN}`);
  }
  console.log();

  // Show QR code for mobile connection
  if (AUTH_TOKEN) {
    // Use publicUrl if provided, otherwise fall back to networkWsUrl
    const qrUrl = publicUrl || networkWsUrl;
    const qrData = JSON.stringify({ url: qrUrl, token: AUTH_TOKEN });

    const QRCode = await import("qrcode");
    const qrString = await QRCode.toString(qrData, { type: "terminal", small: true });
    console.log(`  📱 Scan QR to connect on mobile:`);
    if (publicUrl) {
      console.log(`    (using --public-url: ${publicUrl})`);
    }
    console.log();
    console.log(qrString);
  } else {
    console.log(`  ⚠️  Authentication disabled (--no-auth)`);
    console.log();
  }

  // Agent info
  const agentDisplay = AGENT_ARGS.length > 0
    ? `${AGENT_COMMAND} ${AGENT_ARGS.join(" ")}`
    : AGENT_COMMAND;
  console.log(`  📦 Agent: ${agentDisplay}`);
  console.log(`     CWD:   ${AGENT_CWD}`);
  console.log();
  console.log(`  Press Ctrl+C to stop`);
  console.log();

  // Also log to file when debug is enabled
  log.info("Server started", {
    port,
    host,
    https,
    publicUrl,
    wsEndpoint: `${wsProtocol}://${displayHost}:${port}/ws`,
    mcpEndpoint: `${httpProtocol}://${displayHost}:${port}/mcp`,
    agent: AGENT_COMMAND,
    agentArgs: AGENT_ARGS,
    cwd: AGENT_CWD,
    authEnabled: !!AUTH_TOKEN,
  });

  // Launch PWA via Termux if --termux flag is set
  if (termux) {
    // Small delay to ensure server is ready
    setTimeout(() => {
      launchTermuxPwa("ACP");
    }, 500);
  }

  // Keep the server running
  await new Promise(() => {});
}
