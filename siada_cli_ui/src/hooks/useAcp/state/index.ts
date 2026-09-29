import { useState, useRef } from 'react';
import { SiadaACPClient } from '../../../acp/client.js';
import { Message, ConnectionStatus } from '../../../types/index.js';
import { BannerInfo, TokenUsage, InteractiveInputRequest, LoginState, TodoItem, TodoMessageRange, CacheStatusData, GoalState, SubAgentItem, SubAgentMessageEntry } from '../types.js';
import type { ThinkingStep } from '../../../constants/phrases.js';

export function useACPState() {
  const [client, setClient] = useState<SiadaACPClient | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    connected: false,
    connecting: true,
    ready: false,
  });
  const [loading, setLoading] = useState(false);
  /** Current agent activity step (reasoning / tool execution / system
   * processing / compaction) driving the thinking indicator's step label. */
  const [activeStep, setActiveStep] = useState<ThinkingStep | null>(null);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage | null>(null);
  const [cacheStatus, setCacheStatus] = useState<CacheStatusData | null>(null);
  const [bannerInfo, setBannerInfo] = useState<BannerInfo | null>(null);
  const [interactiveInput, setInteractiveInput] = useState<InteractiveInputRequest | null>(null);
  const [loginState, setLoginState] = useState<LoginState>(null);
  const [todoItems, setTodoItems] = useState<TodoItem[]>([]);
  const [todoMessageRanges, setTodoMessageRanges] = useState<Map<string, TodoMessageRange>>(new Map());
  const [goalState, setGoalState] = useState<GoalState | null>(null);
  const [subAgentItems, setSubAgentItems] = useState<SubAgentItem[]>([]);
  const [subAgentMessages, setSubAgentMessages] = useState<Map<string, SubAgentMessageEntry[]>>(new Map());

  const clientRef = useRef<SiadaACPClient | null>(null);
  const messagesRef = useRef<Message[]>([]);
  const currentSessionIdRef = useRef<string | null>(null);

  // Deferred rendering refs for cross-session history sync
  const pendingHistoryRef = useRef<boolean>(false);
  const historyBufferRef = useRef<Message[]>([]);
  const pendingUserMessageIdRef = useRef<string | null>(null);
  const pullHistoryTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  return {
    client, setClient,
    messages, setMessages,
    connectionStatus, setConnectionStatus,
    loading, setLoading,
    activeStep, setActiveStep,
    tokenUsage, setTokenUsage,
    cacheStatus, setCacheStatus,
    bannerInfo, setBannerInfo,
    interactiveInput, setInteractiveInput,
    loginState, setLoginState,
    todoItems, setTodoItems,
    todoMessageRanges, setTodoMessageRanges,
    goalState, setGoalState,
    subAgentItems, setSubAgentItems,
    subAgentMessages, setSubAgentMessages,
    clientRef,
    messagesRef,
    currentSessionIdRef,
    pendingHistoryRef,
    historyBufferRef,
    pendingUserMessageIdRef,
    pullHistoryTimeoutRef,
  };
}

