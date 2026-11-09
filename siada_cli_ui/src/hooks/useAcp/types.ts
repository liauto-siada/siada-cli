import { MutableRefObject } from 'react';
import { SiadaACPClient } from '../../acp/client.js';
import { Message, ConnectionStatus } from '../../types/index.js';
import type { ThinkingStep } from '../../constants/phrases.js';

export interface BannerInfo {
  version: string;
  workingDir: string;
  agent: string;
  provider: string;
  model: string;
  thinkingTokens?: string;
  reasoningEffort?: string;
  /** Whether thinking is explicitly disabled via /thinking off; undefined/null = model default (on). */
  thinkingEnabled?: boolean | null;
  parallelToolCalls?: boolean;
  quotaUsage?: string | null;
  memoryEnabled?: boolean;
}

export interface TokenUsage {
  contextSize: number;
  contextMax: number;
  message: string;
}

export interface CacheStatusData {
  model: string;
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
  prompt_total: number;
  hit_rate: number;
  accumulated_hit_rate: number;
  reason: string;
  idle_seconds: number;
  input_cost: number;
  output_cost: number;
  cache_write_cost: number;
  cache_read_cost: number;
  total_cost: number;
  accumulated_input_cost: number;
  accumulated_output_cost: number;
  accumulated_cache_write_cost: number;
  accumulated_cache_read_cost: number;
  accumulated_total_cost: number;
  cost_time_seconds: number;
  accumulated_input: number;
  accumulated_output: number;
  accumulated_cache_write: number;
  accumulated_cache_read: number;
}

export interface InteractiveInputRequest {
  prompt: string;
  inputType: 'text' | 'password' | 'confirmation';
  isPassword: boolean;
}

export interface TodoItem {
  content: string;
  status: 'pending' | 'in_progress' | 'completed';
}

export interface SubAgentItem {
  id: string;
  title: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  summary?: string;
}

export interface SubAgentMessageEntry {
  kind: 'thinking' | 'tool_call' | 'tool_output' | 'message';
  text: string;
  toolName?: string;
  /** Stable identity for replacement snapshots; absent on legacy append entries. */
  id?: string;
  isComplete?: boolean;
}

export interface TodoMessageRange {
  startIdx: number;
  endIdx: number | null;
}

export interface GoalResult {
  id?: string;
  timestamp?: string;
  outcome?: 'achieved' | 'not_achieved' | 'blocked' | 'system_error';
  continuing?: boolean;
  achieved: boolean;
  elapsedSeconds: number;
  turns: number;
  tokensUsed: number;
  objective: string;
  reason: string;
  nextAction?: string;
}

export interface GoalState {
  goal: {
    objective: string;
    status: 'active' | 'paused' | 'blocked' | 'complete';
    /** Goal creation time; also supports elapsed time from older backends. */
    createdAt?: string;
    /** Latest lifecycle update, used to freeze legacy stopped goals. */
    updatedAt?: string;
    /** Accumulated active duration at elapsedUpdatedAt, including verification. */
    elapsedSeconds?: number;
    /** Snapshot timestamp; only active goals extrapolate elapsed time from it. */
    elapsedUpdatedAt?: string;
    /**
     * Total verifier rounds run so far against this goal (backend's
     * Goal.turns), ticking up as each verification round starts.
     * Optional so older backends /
     * stale pushes without it still degrade gracefully (turn count just
     * doesn't render).
     */
    turns?: number;
  } | null;
  verifying: boolean;
  notice?: string;


  /** One-shot payload on a verifier pass / non-blocked fail — see App.tsx's
   * effect that turns this into a persistent collapsible "Goal achieved /
   * not yet achieved" chat message. */
  result?: GoalResult;
  /** Durable latest verdict, also included while a new check is running. */
  latestResult?: GoalResult;
  /** Replayed verification records on session restoration. */
  results?: GoalResult[];
}


export type LoginState =
  | { phase: 'selecting'; providers?: Record<string, unknown>[]; freeTrialModels?: import('../../components/Login/LoginSelector.js').ModelInfo[]; cancelable?: boolean; liidDisabled?: boolean; requestId?: string }
  | { phase: 'waiting'; url: string; openBrowser: boolean }
  | null;

export interface UseACPResult {
  client: SiadaACPClient | null;
  /** Ref to the ACP client — available even before connect() resolves (login window). */
  clientRef: MutableRefObject<SiadaACPClient | null>;
  messages: Message[];
  connectionStatus: ConnectionStatus;
  loading: boolean;
  /** Startup history and restored state have finished arriving. */
  startupComplete: boolean;
  /** Current agent activity step while loading (reasoning / tool execution /
   * system processing / compaction) — drives the thinking indicator label. */
  activeStep: ThinkingStep | null;
  bannerInfo: BannerInfo | null;
  tokenUsage: TokenUsage | null;
  interactiveInput: InteractiveInputRequest | null;
  loginState: LoginState;
  sendMessage: (content: string, imagePaths?: string[], options?: { queueId?: string }) => Promise<void>;
  sendInteractiveInput: (input: string) => Promise<void>;
  stopExecution: (showInterruptMessage?: boolean) => Promise<void>;

  cancelPendingQueue: () => void;
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  removeMessage: (id: string) => void;
  sessionId: string | null;
  clearMessages: () => void;
  todoItems: TodoItem[];
  todoMessageRanges: Map<string, TodoMessageRange>;
  cacheStatus: CacheStatusData | null;
  goalState: GoalState | null;
  subAgentItems: SubAgentItem[];
  subAgentMessages: Map<string, SubAgentMessageEntry[]>;
}
