import { useState, useRef } from 'react';
import { SiadaACPClient } from '../../../acp/client.js';
import { Message, ConnectionStatus } from '../../../types/index.js';
import { BannerInfo, TokenUsage, InteractiveInputRequest, LoginState } from '../types.js';

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
  const [bannerInfo, setBannerInfo] = useState<BannerInfo | null>(null);
  const [interactiveInput, setInteractiveInput] = useState<InteractiveInputRequest | null>(null);
  const [loginState, setLoginState] = useState<LoginState>(null);

  const clientRef = useRef<SiadaACPClient | null>(null);
  const currentSessionIdRef = useRef<string | null>(null);

  return {
    client, setClient,
    messages, setMessages,
    connectionStatus, setConnectionStatus,
    loading, setLoading,
    tokenUsage, setTokenUsage,
    bannerInfo, setBannerInfo,
    interactiveInput, setInteractiveInput,
    loginState, setLoginState,
    clientRef,
    currentSessionIdRef,
  };
}
