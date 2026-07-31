import { MutableRefObject } from 'react';
import { SiadaACPClient } from '../../acp/client.js';
import { Message, ConnectionStatus } from '../../types/index.js';

export interface BannerInfo {
  version: string;
  workingDir: string;
  agent: string;
  provider: string;
  model: string;
  prePlanMode: boolean;
  thinkingTokens?: string;
  reasoningEffort?: string;
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

export interface TodoMessageRange {
  startIdx: number;
  endIdx: number | null;
}

export interface GoalResult {
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
    /**
     * ISO-8601 'Z'-suffixed timestamp (backend's Goal.created_at) — used by
     * GoalStatusBar to render a live "Nm Ns" elapsed-time counter next to
     * the status label. Optional so older backends / stale pushes without
     * it still degrade gracefully (timer just doesn't render).
     */
    createdAt?: string;
    /**
     * Total verifier rounds run so far against this goal (backend's
     * Goal.turns), ticking up in real time as each verification round
     * completes — see push_goal_state_via_acp. Optional so older backends /
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
}


export type LoginState =
  | { phase: 'selecting'; providers?: Record<string, unknown>[]; cancelable?: boolean; liidDisabled?: boolean }
  | { phase: 'waiting'; url: string; openBrowser: boolean }
  | null;

export interface UseACPResult {
  client: SiadaACPClient | null;
  /** Ref to the ACP client — available even before connect() resolves (login window). */
  clientRef: MutableRefObject<SiadaACPClient | null>;
  messages: Message[];
  connectionStatus: ConnectionStatus;
  loading: boolean;
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
  sessionId: string | null;
  clearMessages: () => void;
  todoItems: TodoItem[];
  todoMessageRanges: Map<string, TodoMessageRange>;
  cacheStatus: CacheStatusData | null;
  goalState: GoalState | null;
}
