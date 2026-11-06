/**
 * LoginSelector Component
 * Multi-phase sign-in wizard with provider and model selection.
 * Model data is sourced from models.dev/api.json (via backend) with a bundled snapshot fallback.
 */

import React, { useState } from 'react';
import { PANEL_TIPS } from '../../constants/tips.js';
import { t, useUiLanguage } from '../../i18n/index.js';
import { Box, Text } from '@jrichman/ink';
import { useKeypress } from '../../hooks/useKeypress.js';
import { ShortcutTextInput } from '../Input/ShortcutTextInput.js';
import { PickerFrame, PickerHeader, PickerFooter, PickerRow, PickerScrollHint, pickerHint, usePickerWindow } from '../Picker/Picker.js';

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

export type LoginChoice = '1' | '2' | '3' | '4' | 'skip' | 'cancel';

export interface LoginSelectorProps {
  onSelect: (choice: LoginChoice, apiKey?: string) => void;
  /** Provider/model data from backend (models.dev cache). Overrides bundled snapshot when provided. */
  providers?: ProviderInfo[];
  freeTrialModels?: ModelInfo[];
  /** When true (reconfigure flow), Esc cancels without error instead of sending 'skip'. */
  cancelable?: boolean;
  /** When true, hide LiId / Device Code options and only allow API key configuration. */
  liidDisabled?: boolean;
  /** When true, temporarily disable input while the selection is being submitted. */
  submitting?: boolean;
  /** Error to show under the input when a submit timed out or failed. */
  submitError?: string | null;
}

// ── Bundled snapshot (curated from models.dev/api.json) ───────────────────────

const PROVIDERS_SNAPSHOT: ProviderInfo[] = [
  {
    id: 'kimi',
    name: 'Kimi (Moonshot AI)',
    baseUrl: 'https://api.moonshot.cn/v1',
    get apiKeyHint() { return t('请输入 API Key，例如 sk-…', 'Enter API key like sk-...'); },
    models: [
      { id: 'kimi-k2.5',             name: 'Kimi K2.5',              context: 262 },
      { id: 'kimi-k2-thinking',       name: 'Kimi K2 Thinking',       context: 262 },
      { id: 'kimi-k2-thinking-turbo', name: 'Kimi K2 Thinking Turbo', context: 262 },
      { id: 'kimi-k2-turbo-preview',  name: 'Kimi K2 Turbo',          context: 262 },
      { id: 'kimi-k2-0905-preview',   name: 'Kimi K2 0905',           context: 262 },
    ],
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    get apiKeyHint() { return t('请输入从 platform.deepseek.com 获取的 API Key', 'Enter API key from platform.deepseek.com'); },
    models: [
      { id: 'deepseek-flash', name: 'DeepSeek Flash', context: 1000 },
      { id: 'deepseek-v4-pro', name: 'DeepSeek V4 Pro', context: 1000 },
    ],
  },
  {
    id: 'glm',
    name: 'GLM (ZhipuAI)',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    get apiKeyHint() { return t('请输入从 zhipuai.cn 获取的 API Key', 'Enter API key from zhipuai.cn'); },
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
    get apiKeyHint() { return t('请输入从 minimax.io 获取的 API Key', 'Enter API key from minimax.io'); },
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
    get apiKeyHint() { return t('请输入 API Key，例如 sk-…', 'Enter API key like sk-...'); },
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
    get apiKeyHint() { return t('请输入 API Key，例如 sk-ant-…', 'Enter API key like sk-ant-...'); },
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
    get apiKeyHint() { return t('请输入 API Key，例如 AIza…', 'Enter API key like AIza...'); },
    models: [
      { id: 'gemini-2.5-flash',      name: 'Gemini 2.5 Flash',      context: 1048 },
      { id: 'gemini-2.5-pro',        name: 'Gemini 2.5 Pro',        context: 1048 },
      { id: 'gemini-3-flash-preview', name: 'Gemini 3 Flash Preview', context: 1048 },
      { id: 'gemini-3-pro-preview',  name: 'Gemini 3 Pro Preview',  context: 1000 },
    ],
  },
  {
    id: 'custom',
    get name() { return t('自定义服务商', 'Custom Provider'); },
    baseUrl: '',
    get apiKeyHint() { return t('请输入你的 API Key', 'Enter your API key'); },
    models: [],
  },
];

// ── Main options ───────────────────────────────────────────────────────────────

const OPTIONS = [
  { id: '1' as const, get label() { return t('使用 LiId 登录', 'Sign in with LiId'); },
    get description() { return t('自动打开浏览器', 'Opens browser automatically'); } },
  { id: '2' as const, get label() { return t('使用设备码登录', 'Sign in with Device Code'); },
    get description() { return t('显示登录链接，可在其他设备上打开', 'Print URL — works without a browser'); } },
  { id: '3' as const, get label() { return t('配置 API Key', 'Configure API Key'); },
    get description() { return t('使用自己的 API Key（Kimi、DeepSeek、OpenAI、Claude 等）', 'Use your own API key (kimi, deepseek, openai, claude...)'); } },
  { id: '4' as const, label: 'Free Trial',
    get description() { return t('选择免费模型，无需 API Key', 'Choose a free model, no API key required'); } },
];

// ── Phase type ─────────────────────────────────────────────────────────────────

type Phase =
  | 'selecting'
  | 'free-model-select'
  | 'provider-select'
  | 'model-select'
  | 'baseurl-input'
  | 'model-name-input'
  | 'apikey-input';

// ── Component ─────────────────────────────────────────────────────────────────

export const LoginSelector: React.FC<LoginSelectorProps> = ({ onSelect, providers, freeTrialModels = [], cancelable, liidDisabled, submitting = false, submitError = null }) => {
  useUiLanguage();
  const effectiveProviders =
    providers && providers.length > 0 ? providers : PROVIDERS_SNAPSHOT;
  const visibleOptions = OPTIONS.filter(option =>
    option.id === '4' ? freeTrialModels.length > 0 : option.id === '3' || liidDisabled === false);

  const [activeIndex, setActiveIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>('selecting');
  const [selectedProvider, setSelectedProvider] = useState<ProviderInfo | null>(null);
  const [selectedModel, setSelectedModel] = useState<ModelInfo | null>(null);
  const [customBaseUrl, setCustomBaseUrl] = useState('');
  const [customModelName, setCustomModelName] = useState('');
  const selectionCount = phase === 'provider-select' ? effectiveProviders.length
    : phase === 'model-select' ? selectedProvider?.models.length ?? 0
    : phase === 'free-model-select' ? freeTrialModels.length : visibleOptions.length;
  const { startIndex, endIndex } = usePickerWindow(selectionCount, activeIndex, { summary: true });

  const clamp = (val: number, len: number) => Math.min(Math.max(0, val), len - 1);
  const isSubmitKey = (key: { name: string }) => key.name === 'return' || key.name === 'enter';

  useKeypress((key) => {
    // The text-entry phases are owned by ShortcutTextInput (its own key
    // handler), so the wizard must not also act on those keys.
    if (phase === 'baseurl-input' || phase === 'model-name-input' || phase === 'apikey-input') {
      return;
    }
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
        } else if (choice === '4') {
          setPhase('free-model-select');
          setActiveIndex(0);
        } else {
          onSelect(choice);
        }
      } else if (key.name === 'escape' || (key.ctrl && key.name === 'c') || key.sequence === 'q') {
        onSelect(cancelable ? 'cancel' : 'skip');
      }

    } else if (phase === 'free-model-select') {
      if (key.name === 'up' || key.sequence === 'k') {
        setActiveIndex(i => clamp(i - 1, freeTrialModels.length));
      } else if (key.name === 'down' || key.sequence === 'j') {
        setActiveIndex(i => clamp(i + 1, freeTrialModels.length));
      } else if (isSubmitKey(key)) {
        const model = freeTrialModels[activeIndex];
        if (model) onSelect('4', JSON.stringify({ model: model.id }));
      } else if (key.name === 'escape') {
        setPhase('selecting');
        setActiveIndex(Math.max(0, visibleOptions.findIndex(option => option.id === '4')));
      }
    } else if (phase === 'provider-select') {
      if (key.name === 'up' || key.sequence === 'k') {
        setActiveIndex(i => clamp(i - 1, effectiveProviders.length));
      } else if (key.name === 'down' || key.sequence === 'j') {
        setActiveIndex(i => clamp(i + 1, effectiveProviders.length));
      } else if (isSubmitKey(key)) {
        const p = effectiveProviders[activeIndex];
        setSelectedProvider(p);
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
          setPhase('apikey-input');
        }
      } else if (key.name === 'escape') {
        const idx = effectiveProviders.findIndex(p => p.id === selectedProvider?.id);
        setPhase('provider-select');
        setActiveIndex(idx >= 0 ? idx : 0);
      }
    }
  }, { isActive: !submitting });

  // While a submit is in flight the wizard disables the handlers above; keep
  // Escape available so the user can always back out instead of being stuck on
  // "Submitting login..." with no way forward.
  useKeypress((key) => {
    if (key.name === 'escape') {
      onSelect(cancelable ? 'cancel' : 'skip');
    }
  }, { isActive: submitting });

  // ── Renders ──────────────────────────────────────────────────────────────────

  if (phase === 'free-model-select') {
    return (
      <PickerFrame title="Free Trial — Choose Model"
        summary={t('Kilo · 无需 API Key · 免费模型的可用性可能变化', 'Kilo · No API key required · Free availability may change')}
        hint={submitting ? PANEL_TIPS.loginSubmitting : pickerHint('vertical')}>
        <PickerScrollHint visible={startIndex > 0} direction="up" />
        {freeTrialModels.slice(startIndex, endIndex).map((model, index) => (
          <PickerRow key={model.id} active={startIndex + index === activeIndex}>{model.name}</PickerRow>
        ))}
        <PickerScrollHint visible={endIndex < freeTrialModels.length} direction="down" />
        <Text dimColor>{activeIndex + 1}/{freeTrialModels.length} · {freeTrialModels[activeIndex]?.id}</Text>
        {submitError && <Text color="red">{submitError}</Text>}
      </PickerFrame>
    );
  }

  if (phase === 'provider-select') {
    return (
      <PickerFrame title={t('配置 API Key · 选择服务商', 'Configure API Key — Choose Provider')}
        summary={t('请选择模型服务商：', 'Select your model provider:')} hint={pickerHint('vertical')}>
          <PickerScrollHint visible={startIndex > 0} direction="up" />
          {effectiveProviders.slice(startIndex, endIndex).map((p, i) => {
            const isActive = i + startIndex === activeIndex;
            return (
              <PickerRow key={p.id} active={isActive}>{p.name}
                {p.models.length > 0 ? `  ${t(`${p.models.length} 个模型`, `${p.models.length} models`)}` : ''}
              </PickerRow>
            );
          })}
          <PickerScrollHint visible={endIndex < effectiveProviders.length} direction="down" />
      </PickerFrame>
    );
  }

  if (phase === 'model-select') {
    const models = selectedProvider?.models ?? [];
    return (
      <PickerFrame title={`${selectedProvider?.name ?? t('服务商', 'Provider')}${t(' · 选择模型', ' — Choose Model')}`}
        summary={t('请选择模型：', 'Select a model:')} hint={pickerHint('vertical')}>
          <PickerScrollHint visible={startIndex > 0} direction="up" />
          {models.slice(startIndex, endIndex).map((m, i) => {
            const isActive = i + startIndex === activeIndex;
            return (
              <PickerRow key={m.id} active={isActive}>{m.id}{`  ${m.name} · ${m.context}K ${t('上下文', 'ctx')}`}</PickerRow>
            );
          })}
          <PickerScrollHint visible={endIndex < models.length} direction="down" />
      </PickerFrame>
    );
  }

  if (phase === 'baseurl-input') {
    return (
      <Box flexDirection="column" paddingX={1} width="100%">
        <PickerHeader title={t('自定义服务商 · API 地址', 'Custom Provider — Base URL')} />
        <Box paddingX={1} marginBottom={1}>
          <Text dimColor>{t('请输入服务商的 API 地址（兼容 OpenAI）：', 'Enter provider base URL (OpenAI-compatible):')}</Text>
        </Box>
        <ShortcutTextInput
          key="baseurl-input"
          initialValue={customBaseUrl}
          placeholder="https://api.example.com/v1"
          active={!submitting}
          onSubmit={(val) => {
            if (!val) return;
            setCustomBaseUrl(val);
            setPhase('model-name-input');
          }}
          onCancel={() => {
            const idx = effectiveProviders.findIndex(p => p.id === 'custom');
            setPhase('provider-select');
            setActiveIndex(idx >= 0 ? idx : 0);
          }}
        />
        <PickerFooter>{PANEL_TIPS.loginEdit}</PickerFooter>
      </Box>
    );
  }

  if (phase === 'model-name-input') {
    return (
      <Box flexDirection="column" paddingX={1} width="100%">
        <PickerHeader title={t('自定义服务商 · 模型名称', 'Custom Provider — Model Name')} />
        <Box paddingX={1} marginBottom={0}>
          <Text dimColor>{t('API 地址：', 'Base URL: ')}</Text>
          <Text color="cyan">{customBaseUrl}</Text>
        </Box>
        <Box paddingX={1} marginBottom={1}>
          <Text dimColor>{t('请输入模型名称（例如 gpt-4o、llama-3-70b）：', 'Enter model name (e.g. gpt-4o, llama-3-70b):')}</Text>
        </Box>
        <ShortcutTextInput
          key="model-name-input"
          initialValue={customModelName}
          placeholder={t('例如 gpt-4o、llama-3-70b', 'e.g. gpt-4o, llama-3-70b')}
          active={!submitting}
          onSubmit={(val) => {
            if (!val) return;
            setCustomModelName(val);
            setPhase('apikey-input');
          }}
          onCancel={() => setPhase('baseurl-input')}
        />
        <PickerFooter>{PANEL_TIPS.loginConfirm}</PickerFooter>
      </Box>
    );
  }

  if (phase === 'apikey-input') {
    const providerName = selectedProvider?.name ?? t('服务商', 'Provider');
    const hint = selectedProvider?.apiKeyHint ?? '';
    const modelDesc = selectedProvider?.id === 'custom' ? customModelName : (selectedModel?.id ?? '');
    return (
      <Box flexDirection="column" paddingX={1} width="100%">
        <PickerHeader title={`${providerName} — API Key`} />
        {modelDesc ? (
          <Box paddingX={1} marginBottom={0}>
            <Text dimColor>{t('模型：', 'Model: ')}</Text>
            <Text color="cyan">{modelDesc}</Text>
          </Box>
        ) : null}
        {hint ? (
          <Box paddingX={1} marginBottom={1}>
            <Text dimColor>{hint}</Text>
          </Box>
        ) : null}
        <ShortcutTextInput
          key={`apikey-${selectedProvider?.id ?? ''}`}
          masked
          active={!submitting}
          onSubmit={(apiKey) => {
            if (!apiKey || !selectedProvider) return;
            const baseUrl = selectedProvider.id === 'custom' ? customBaseUrl : selectedProvider.baseUrl;
            const modelId = selectedProvider.id === 'custom' ? customModelName : (selectedModel?.id ?? '');
            onSelect('3', JSON.stringify({
              provider_id: selectedProvider.id,
              api_key: apiKey,
              base_url: baseUrl,
              model: modelId,
            }));
          }}
          onCancel={() => {
            if (selectedProvider?.id === 'custom') {
              setPhase('model-name-input');
            } else {
              const idx = selectedProvider?.models.findIndex(m => m.id === selectedModel?.id) ?? -1;
              setPhase('model-select');
              setActiveIndex(idx >= 0 ? idx : 0);
            }
          }}
        />
        {submitError ? (
          <Box paddingX={1} marginBottom={1}>
            <Text color="red">{submitError}</Text>
          </Box>
        ) : null}
        <PickerFooter>{submitting ? PANEL_TIPS.loginSubmitting : PANEL_TIPS.loginSubmit}</PickerFooter>
      </Box>
    );
  }

  // Default: 'selecting'
  return (
    <PickerFrame title={t('登录', 'Sign In')}
      summary={t('尚未登录，请选择登录方式：', 'You are not signed in. Choose a sign-in method:')}
      hint={cancelable ? pickerHint('vertical') : PANEL_TIPS.loginSkip}>
          <PickerScrollHint visible={startIndex > 0} direction="up" />
          {visibleOptions.slice(startIndex, endIndex).map((opt, index) => {
          const isActive = index + startIndex === activeIndex;
          return (
            <PickerRow key={opt.id} active={isActive}>{opt.label}{`  ${opt.description}`}</PickerRow>
          );
        })}
          <PickerScrollHint visible={endIndex < visibleOptions.length} direction="down" />
    </PickerFrame>
  );
};
