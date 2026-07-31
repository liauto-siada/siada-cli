import { useState, useRef } from 'react';
import { SiadaACPClient } from '../../../acp/client.js';
import { Message, ConnectionStatus } from '../../../types/index.js';
import { BannerInfo, TokenUsage, InteractiveInputRequest, LoginState, TodoItem, TodoMessageRange, CacheStatusData, GoalState } from '../types.js';

export function useACPState() {
  const [client, setClient] = useState<SiadaACPClient | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>({
    connected: false,
    connecting: true,
    ready: false,
  });
  const [loading, setLoading] = useState(false);
  const [tokenUsage, setTokenUsage] = useState<TokenUsage | null>(null);
  const [cacheStatus, setCacheStatus] = useState<CacheStatusData | null>(null);
  const [bannerInfo, setBannerInfo] = useState<BannerInfo | null>(null);
  const [interactiveInput, setInteractiveInput] = useState<InteractiveInputRequest | null>(null);
  const [loginState, setLoginState] = useState<LoginState>(null);
  const [todoItems, setTodoItems] = useState<TodoItem[]>([]);
  const [todoMessageRanges, setTodoMessageRanges] = useState<Map<string, TodoMessageRange>>(new Map());
  const [goalState, setGoalState] = useState<GoalState | null>(null);

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
    tokenUsage, setTokenUsage,
    cacheStatus, setCacheStatus,
    bannerInfo, setBannerInfo,
    interactiveInput, setInteractiveInput,
    loginState, setLoginState,
    todoItems, setTodoItems,
    todoMessageRanges, setTodoMessageRanges,
    goalState, setGoalState,
    clientRef,
    messagesRef,
    currentSessionIdRef,
    pendingHistoryRef,
    historyBufferRef,
    pendingUserMessageIdRef,
    pullHistoryTimeoutRef,
  };
}

