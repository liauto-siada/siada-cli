/**
 * LoginSelector Component
 * Multi-phase sign-in wizard with provider and model selection.
 * Model data is sourced from models.dev/api.json (via backend) with a bundled snapshot fallback.
 */

import React, { useState } from 'react';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';

// ── Exported types ─────────────────────────────────────────────────────────────

export interface ModelInfo {
  id: string;
  name: string;
  context: number; // context window in K tokens
}

export interface ProviderInfo {
  id: string;
  name: string;
  baseUrl: string;
  apiKeyHint: string;
  models: ModelInfo[];
}

export type LoginChoice = '1' | '2' | '3' | 'skip' | 'cancel';

export interface LoginSelectorProps {
  onSelect: (choice: LoginChoice, apiKey?: string) => void;
  /** Provider/model data from backend (models.dev cache). Overrides bundled snapshot when provided. */
  providers?: ProviderInfo[];
  /** When true (reconfigure flow), Esc cancels without error instead of sending 'skip'. */
  cancelable?: boolean;
  /** When true, hide LiId / Device Code options and only allow API key configuration. */
  liidDisabled?: boolean;
  /** When true, temporarily disable input while the selection is being submitted. */
  submitting?: boolean;
}

// ── Bundled snapshot (curated from models.dev/api.json) ───────────────────────

const PROVIDERS_SNAPSHOT: ProviderInfo[] = [
  {
    id: 'kimi',
    name: 'Kimi (Moonshot AI)',
    baseUrl: 'https://api.moonshot.cn/v1',
    apiKeyHint: 'Enter API key like sk-...',
    models: [
      { id: 'kimi-k2.5',             name: 'Kimi K2.5',              context: 262 },
      { id: 'kimi-k2-thinking',       name: 'Kimi K2 Thinking',       context: 262 },
      { id: 'kimi-k2-thinking-turbo', name: 'Kimi K2 Thinking Turbo', context: 262 },
      { id: 'kimi-k2-turbo-preview',  name: 'Kimi K2 Turbo',          context: 262 },
      { id: 'kimi-k2-0905-preview',   name: 'Kimi K2 0905',           context: 262 },
    ],
  },
  {
    id: 'glm',
    name: 'GLM (ZhipuAI)',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    apiKeyHint: 'Enter API key from zhipuai.cn',
    models: [
      { id: 'glm-5',         name: 'GLM-5',         context: 204 },
      { id: 'glm-4.7',       name: 'GLM-4.7',       context: 204 },
      { id: 'glm-4.7-flash', name: 'GLM-4.7-Flash', context: 200 },
      { id: 'glm-4.6',       name: 'GLM-4.6',       context: 204 },
      { id: 'glm-4.5',       name: 'GLM-4.5',       context: 131 },
    ],
  },
  {
    id: 'minimax',
    name: 'MiniMax',
    baseUrl: 'https://api.minimax.chat/v1',
    apiKeyHint: 'Enter API key from minimax.io',
    models: [
      { id: 'MiniMax-M2.5',           name: 'MiniMax M2.5',           context: 204 },
      { id: 'MiniMax-M2.5-highspeed', name: 'MiniMax M2.5 Highspeed', context: 204 },
      { id: 'MiniMax-M2.1',           name: 'MiniMax M2.1',           context: 204 },
      { id: 'MiniMax-M2',             name: 'MiniMax M2',             context: 196 },
    ],
  },
  {
    id: 'openai',
    name: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    apiKeyHint: 'Enter API key like  sk-...',
    models: [
      { id: 'gpt-4o',      name: 'GPT-4o',      context: 128 },
      { id: 'gpt-4o-mini', name: 'GPT-4o Mini', context: 128 },
      { id: 'gpt-5.2',     name: 'GPT-5.2',     context: 400 },
      { id: 'o3-mini',     name: 'o3-mini',      context: 200 },
      { id: 'o3',          name: 'o3',           context: 200 },
    ],
  },
  {
    id: 'claude',
    name: 'Claude (Anthropic)',
    baseUrl: 'https://api.anthropic.com',
    apiKeyHint: 'Enter API key like sk-ant-...',
    models: [
      { id: 'claude-sonnet-4-5', name: 'Claude Sonnet 4.5', context: 200 },
      { id: 'claude-sonnet-4-6', name: 'Claude Sonnet 4.6', context: 200 },
      { id: 'claude-opus-4-5',   name: 'Claude Opus 4.5',   context: 200 },
      { id: 'claude-haiku-4-5',  name: 'Claude Haiku 4.5',  context: 200 },
    ],
  },
  {
    id: 'gemini',
    name: 'Gemini (Google)',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    apiKeyHint: 'Enter API key like AIza...',
    models: [
      { id: 'gemini-2.5-flash',      name: 'Gemini 2.5 Flash',      context: 1048 },
      { id: 'gemini-2.5-pro',        name: 'Gemini 2.5 Pro',        context: 1048 },
      { id: 'gemini-3-flash-preview', name: 'Gemini 3 Flash Preview', context: 1048 },
      { id: 'gemini-3-pro-preview',  name: 'Gemini 3 Pro Preview',  context: 1000 },
    ],
  },
  {
    id: 'custom',
    name: 'Custom Provider',
    baseUrl: '',
    apiKeyHint: 'your API key',
    models: [],
  },
];

// ── Main options ───────────────────────────────────────────────────────────────

const OPTIONS = [
  { id: '1' as const, label: 'Sign in with LiId',        description: 'Opens browser automatically' },
  { id: '2' as const, label: 'Sign in with Device Code', description: 'Print URL — works without a browser' },
  { id: '3' as const, label: 'Configure API Key',        description: 'Use your own API key (kimi, openai, claude...)' },
];

// ── Phase type ─────────────────────────────────────────────────────────────────

type Phase =
  | 'selecting'
  | 'provider-select'
  | 'model-select'
  | 'baseurl-input'
  | 'model-name-input'
  | 'apikey-input';

// ── Component ─────────────────────────────────────────────────────────────────

export const LoginSelector: React.FC<LoginSelectorProps> = ({ onSelect, providers, cancelable, liidDisabled, submitting = false }) => {
  const effectiveProviders =
    providers && providers.length > 0 ? providers : PROVIDERS_SNAPSHOT;
  const visibleOptions = liidDisabled ? OPTIONS.filter(option => option.id === '3') : OPTIONS;

  const [activeIndex, setActiveIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>('selecting');
  const [selectedProvider, setSelectedProvider] = useState<ProviderInfo | null>(null);
  const [selectedModel, setSelectedModel] = useState<ModelInfo | null>(null);
  const [inputBuffer, setInputBuffer] = useState('');
  const [customBaseUrl, setCustomBaseUrl] = useState('');
  const [customModelName, setCustomModelName] = useState('');

  const clamp = (val: number, len: number) => Math.min(Math.max(0, val), len - 1);
  const isSubmitKey = (key: { name: string }) => key.name === 'return' || key.name === 'enter';

  useKeypress((key) => {
    if (phase === 'selecting') {
      if (key.name === 'up' || key.sequence === 'k') {
        setActiveIndex(i => clamp(i - 1, visibleOptions.length));
      } else if (key.name === 'down' || key.sequence === 'j') {
        setActiveIndex(i => clamp(i + 1, visibleOptions.length));
      } else if (isSubmitKey(key)) {
        const choice = visibleOptions[activeIndex].id;
        if (choice === '3') {
          setPhase('provider-select');
          setActiveIndex(0);
        } else {
          onSelect(choice);
        }
      } else if (key.name === 'escape' || (key.ctrl && key.name === 'c') || key.sequence === 'q') {
        onSelect(cancelable ? 'cancel' : 'skip');
      }

    } else if (phase === 'provider-select') {
      if (key.name === 'up' || key.sequence === 'k') {
        setActiveIndex(i => clamp(i - 1, effectiveProviders.length));
      } else if (key.name === 'down' || key.sequence === 'j') {
        setActiveIndex(i => clamp(i + 1, effectiveProviders.length));
      } else if (isSubmitKey(key)) {
        const p = effectiveProviders[activeIndex];
        setSelectedProvider(p);
        setInputBuffer('');
        if (p.id === 'custom') {
          setPhase('baseurl-input');
        } else {
          setPhase('model-select');
          setActiveIndex(0);
        }
      } else if (key.name === 'escape') {
        setPhase('selecting');
        const apiKeyOptionIndex = visibleOptions.findIndex(option => option.id === '3');
        setActiveIndex(apiKeyOptionIndex >= 0 ? apiKeyOptionIndex : 0);
      }

    } else if (phase === 'model-select') {
      const models = selectedProvider?.models ?? [];
      if (key.name === 'up' || key.sequence === 'k') {
        setActiveIndex(i => clamp(i - 1, models.length));
      } else if (key.name === 'down' || key.sequence === 'j') {
        setActiveIndex(i => clamp(i + 1, models.length));
      } else if (isSubmitKey(key)) {
        const m = models[activeIndex];
        if (m) {
          setSelectedModel(m);
          setInputBuffer('');
          setPhase('apikey-input');
        }
      } else if (key.name === 'escape') {
        const idx = effectiveProviders.findIndex(p => p.id === selectedProvider?.id);
        setPhase('provider-select');
        setActiveIndex(idx >= 0 ? idx : 0);
      }

    } else if (phase === 'baseurl-input') {
      if (isSubmitKey(key)) {
        const val = inputBuffer.trim();
        if (val) {
          setCustomBaseUrl(val);
          setInputBuffer('');
          setPhase('model-name-input');
        }
      } else if (key.name === 'escape') {
        const idx = effectiveProviders.findIndex(p => p.id === 'custom');
        setPhase('provider-select');
        setActiveIndex(idx >= 0 ? idx : 0);
        setInputBuffer('');
      } else if (key.name === 'backspace' || key.name === 'delete') {
        setInputBuffer(prev => prev.slice(0, -1));
      } else if (key.insertable && key.sequence && !key.ctrl && !key.alt) {
        setInputBuffer(prev => prev + key.sequence);
      }

    } else if (phase === 'model-name-input') {
      if (isSubmitKey(key)) {
        const val = inputBuffer.trim();
        if (val) {
          setCustomModelName(val);
          setInputBuffer('');
          setPhase('apikey-input');
        }
      } else if (key.name === 'escape') {
        setPhase('baseurl-input');
        setInputBuffer(customBaseUrl);
      } else if (key.name === 'backspace' || key.name === 'delete') {
        setInputBuffer(prev => prev.slice(0, -1));
      } else if (key.insertable && key.sequence && !key.ctrl && !key.alt) {
        setInputBuffer(prev => prev + key.sequence);
      }

    } else if (phase === 'apikey-input') {
      if (isSubmitKey(key)) {
        const apiKey = inputBuffer.trim();
        if (apiKey && selectedProvider) {
          const baseUrl = selectedProvider.id === 'custom' ? customBaseUrl : selectedProvider.baseUrl;
          const modelId = selectedProvider.id === 'custom' ? customModelName : (selectedModel?.id ?? '');
          onSelect('3', JSON.stringify({
            provider_id: selectedProvider.id,
            api_key: apiKey,
            base_url: baseUrl,
            model: modelId,
          }));
        }
      } else if (key.name === 'escape') {
        if (selectedProvider?.id === 'custom') {
          setInputBuffer(customModelName);
          setPhase('model-name-input');
        } else {
          const idx = selectedProvider?.models.findIndex(m => m.id === selectedModel?.id) ?? -1;
          setInputBuffer('');
          setPhase('model-select');
          setActiveIndex(idx >= 0 ? idx : 0);
        }
      } else if (key.name === 'backspace' || key.name === 'delete') {
        setInputBuffer(prev => prev.slice(0, -1));
      } else if (key.insertable && key.sequence && !key.ctrl && !key.alt) {
        setInputBuffer(prev => prev + key.sequence);
      }
    }
  }, { isActive: !submitting });

  // ── Renders ──────────────────────────────────────────────────────────────────

  if (phase === 'provider-select') {
    return (
      <Box flexDirection="column">
        <Box borderStyle="single" borderColor="cyan" paddingX={1} marginBottom={1}>
          <Text bold color="cyan">Configure API Key — Choose Provider</Text>
        </Box>
        <Box paddingX={1} marginBottom={1}>
          <Text dimColor>Select your model provider:</Text>
        </Box>
        <Box flexDirection="column" paddingX={1}>
          {effectiveProviders.map((p, i) => {
            const isActive = i === activeIndex;
            return (
              <Box key={p.id} flexDirection="row" marginBottom={0}>
                <Text color={isActive ? 'cyan' : 'white'}>{isActive ? '▶ ' : '  '}</Text>
                <Text color={isActive ? 'cyan' : 'white'} bold={isActive}>{p.name}</Text>
                {p.models.length > 0 ? (
                  <Text dimColor>{'  '}{p.models.length} models</Text>
                ) : null}
              </Box>
            );
          })}
        </Box>
        <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
          <Text color="gray" dimColor>↑↓/j/k navigate · Enter select · Esc back</Text>
        </Box>
      </Box>
    );
  }

  if (phase === 'model-select') {
    const models = selectedProvider?.models ?? [];
    return (
      <Box flexDirection="column">
        <Box borderStyle="single" borderColor="cyan" paddingX={1} marginBottom={1}>
          <Text bold color="cyan">{selectedProvider?.name ?? 'Provider'} — Choose Model</Text>
        </Box>
        <Box paddingX={1} marginBottom={1}>
          <Text dimColor>Select a model:</Text>
        </Box>
        <Box flexDirection="column" paddingX={1}>
          {models.map((m, i) => {
            const isActive = i === activeIndex;
            return (
              <Box key={m.id} flexDirection="row" marginBottom={0}>
                <Text color={isActive ? 'cyan' : 'white'}>{isActive ? '▶ ' : '  '}</Text>
                <Text color={isActive ? 'cyan' : 'white'} bold={isActive}>{m.id}</Text>
                <Text dimColor>{'  '}{m.name} · {m.context}K ctx</Text>
              </Box>
            );
          })}
        </Box>
        <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
          <Text color="gray" dimColor>↑↓/j/k navigate · Enter select · Esc back</Text>
        </Box>
      </Box>
    );
  }

  if (phase === 'baseurl-input') {
    return (
      <Box flexDirection="column">
        <Box borderStyle="single" borderColor="cyan" paddingX={1} marginBottom={1}>
          <Text bold color="cyan">Custom Provider — Base URL</Text>
        </Box>
        <Box paddingX={1} marginBottom={1}>
          <Text dimColor>Enter provider base URL (OpenAI-compatible):</Text>
        </Box>
        <Box paddingX={1} marginBottom={1}>
          <Text color="cyan">{'> '}</Text>
          <Text>{inputBuffer}</Text>
          <Text color="cyan">{'█'}</Text>
        </Box>
        <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
          <Text color="gray" dimColor>Enter confirm · Esc back</Text>
        </Box>
      </Box>
    );
  }

  if (phase === 'model-name-input') {
    return (
      <Box flexDirection="column">
        <Box borderStyle="single" borderColor="cyan" paddingX={1} marginBottom={1}>
          <Text bold color="cyan">Custom Provider — Model Name</Text>
        </Box>
        <Box paddingX={1} marginBottom={0}>
          <Text dimColor>Base URL: </Text>
          <Text color="cyan">{customBaseUrl}</Text>
        </Box>
        <Box paddingX={1} marginBottom={1}>
          <Text dimColor>Enter model name (e.g. gpt-4o, llama-3-70b):</Text>
        </Box>
        <Box paddingX={1} marginBottom={1}>
          <Text color="cyan">{'> '}</Text>
          <Text>{inputBuffer}</Text>
          <Text color="cyan">{'█'}</Text>
        </Box>
        <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
          <Text color="gray" dimColor>Enter confirm · Esc back</Text>
        </Box>
      </Box>
    );
  }

  if (phase === 'apikey-input') {
    const providerName = selectedProvider?.name ?? 'Provider';
    const hint = selectedProvider?.apiKeyHint ?? '';
    const modelDesc = selectedProvider?.id === 'custom' ? customModelName : (selectedModel?.id ?? '');
    return (
      <Box flexDirection="column">
        <Box borderStyle="single" borderColor="cyan" paddingX={1} marginBottom={1}>
          <Text bold color="cyan">{providerName} — API Key</Text>
        </Box>
        {modelDesc ? (
          <Box paddingX={1} marginBottom={0}>
            <Text dimColor>Model: </Text>
            <Text color="cyan">{modelDesc}</Text>
          </Box>
        ) : null}
        {hint ? (
          <Box paddingX={1} marginBottom={1}>
            <Text dimColor>Format: {hint}</Text>
          </Box>
        ) : null}
        <Box paddingX={1} marginBottom={1}>
          <Text color="cyan">{'> '}</Text>
          <Text>{inputBuffer}</Text>
          <Text color="cyan">{'█'}</Text>
        </Box>
        <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
          <Text color="gray" dimColor>{submitting ? 'Submitting login...' : 'Enter submit · Esc back'}</Text>
        </Box>
      </Box>
    );
  }

  // Default: 'selecting'
  return (
    <Box flexDirection="column">
      <Box borderStyle="single" borderColor="cyan" paddingX={1} marginBottom={1}>
        <Text bold color="cyan">Sign In</Text>
      </Box>
      <Box paddingX={1} marginBottom={1}>
          <Text dimColor>
            {liidDisabled
              ? 'You are not signed in. Please configure an API key to continue:'
              : 'You are not signed in. Choose a sign-in method:'}
          </Text>
      </Box>
      <Box flexDirection="column" paddingX={1}>
          {visibleOptions.map((opt, index) => {
          const isActive = index === activeIndex;
          return (
            <Box key={opt.id} flexDirection="row" marginBottom={0}>
              <Text color={isActive ? 'cyan' : 'white'}>{isActive ? '▶ ' : '  '}</Text>
              <Text color={isActive ? 'cyan' : 'white'} bold={isActive}>{opt.label}</Text>
              <Text dimColor>{'  '}{opt.description}</Text>
            </Box>
          );
        })}
      </Box>
      <Box borderStyle="single" borderColor="gray" paddingX={1} marginTop={1}>
        <Text color="gray" dimColor>
          {cancelable
            ? '↑↓/j/k navigate · Enter select · Esc cancel'
            : '↑↓/j/k navigate · Enter select · Esc/q skip'}
        </Text>
      </Box>
    </Box>
  );
};
