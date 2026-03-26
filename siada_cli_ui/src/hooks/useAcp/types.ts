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
}

export interface TokenUsage {
  contextSize: number;
  contextMax: number;
  message: string;
}

export interface InteractiveInputRequest {
  prompt: string;
  inputType: 'text' | 'password' | 'confirmation';
  isPassword: boolean;
}

export type LoginState =
  | { phase: 'selecting'; providers?: Record<string, unknown>[]; cancelable?: boolean; liidDisabled?: boolean }
  | { phase: 'waiting'; url: string; openBrowser: boolean }
  | null;

export interface UseACPResult {
  client: SiadaACPClient | null;
  messages: Message[];
  connectionStatus: ConnectionStatus;
  loading: boolean;
  bannerInfo: BannerInfo | null;
  tokenUsage: TokenUsage | null;
  interactiveInput: InteractiveInputRequest | null;
  loginState: LoginState;
  sendMessage: (content: string) => Promise<void>;
  sendInteractiveInput: (input: string) => Promise<void>;
  stopExecution: () => Promise<void>;
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  sessionId: string | null;
  clearMessages: () => void;
}
