import { useEffect } from 'react';
import { logger } from '../utils/logger.js';
import { Message, MessageType } from '../types/index.js';
import type { PluginManagerData } from '../components/PluginManager/index.js';
import type { TaskItem } from '../components/TaskSelector/index.js';
import { isRenderableToolDiff } from '../utils/diff.js';

export interface EffortSelectorData {
  model: string;
  efforts: string[];
  current: string | null;
}

export interface ThemeSelectorData {
  themes: string[];
  current: string;
}

interface AdapterEventHandlers {
  setShowSessionBrowser: (v: boolean) => void;
  addMessage: (msg: Message) => void;
  setModelSelectorData: (v: { models: string[]; currentModel: string; modelNotes?: Record<string, string> } | null) => void;
  setEffortSelectorData: (v: EffortSelectorData | null) => void;
  setThemeSelectorData: (v: ThemeSelectorData | null) => void;
  setTaskSelectorTasks: (v: TaskItem[] | null) => void;
  setInstallProgress: (v: { skillName: string; phase: string; percent: number } | null) => void;
  setPluginManagerData: (v: PluginManagerData | null) => void;
  appendSideQuestion: (item: { question: string; answer: string }) => void;
}

export function useAdapterEvents(client: any, handlers: AdapterEventHandlers): void {
  const {
    setShowSessionBrowser, addMessage,
    setModelSelectorData, setEffortSelectorData, setThemeSelectorData, setTaskSelectorTasks,
    setInstallProgress, setPluginManagerData,
    appendSideQuestion,
  } = handlers;

  useEffect(() => {
    if (!client) return;

    const handleShowSessionBrowser = () => {
      logger.info('Received ui:showSessionBrowser');
      setShowSessionBrowser(true);
    };

    // Append-only history handler for deferred rendering (no clear)
    const handleAppendHistory = (params: any) => {
      logger.info('Received ui:appendHistory event', {
        component: 'App',
        operation: 'append_history',
        messageCount: params?.messages?.length || 0,
      });

      if (params?.messages && Array.isArray(params.messages)) {
        for (const msg of params.messages) {
          if (msg.role && msg.content) {
            const newMessage = {
              id: `deferred-${Date.now()}-${Math.random()}`,
              type: (msg.role === 'user' ? 'user' : 'agent') as MessageType,
              content: msg.content,
              timestamp: new Date().toISOString(),
              author: msg.role === 'user' ? 'User' : 'Assistant',
              metadata: msg.subtype ? {
                subtype: msg.subtype,
                ...(msg.subtype === 'tool_use' && isRenderableToolDiff(msg.content) ? { streamEnd: true } : {}),
              } : undefined,
            };

            addMessage(newMessage);
          }
        }

        logger.info(`Appended ${params.messages.length} deferred messages to UI`);
      }
    };

    const handleShowModelSelector = (params: any) => {
      setModelSelectorData({
        models: params?.models ?? [],
        currentModel: params?.currentModel ?? '',
        modelNotes: params?.modelNotes ?? {},
      });
    };

    const handleShowEffortSelector = (params: any) => {
      setEffortSelectorData({
        model: params?.model ?? '',
        efforts: params?.efforts ?? [],
        current: params?.current ?? null,
      });
    };

    const handleShowThemeSelector = (params: any) => {
      setThemeSelectorData({
        themes: params?.themes ?? [],
        current: params?.current ?? 'dark',
      });
    };

    const handleShowTaskSelector = (params: any) => {
      setTaskSelectorTasks(params?.tasks ?? []);
    };

    const handlePluginInstallProgress = (params: any) => {
      if (params?.phase === 'done') {
        setInstallProgress(null);
      } else {
        setInstallProgress({
          skillName: params?.skillName ?? '',
          phase: params?.phase ?? '',
          percent: params?.percent ?? 0,
        });
      }
    };

    const handleShowPluginManager = (params: any) => {
      setPluginManagerData({
        installed: params?.installed ?? [],
        marketplaces: params?.marketplaces ?? [],
        errors: params?.errors ?? [],
        discover: params?.discover ?? [],
        disabledSkills: params?.disabledSkills ?? [],
      });
    };

    const handleShowSideQuestion = (params: any) => {
      if (params?.question && params?.answer) {
        logger.info('Received ui:showSideQuestion', { questionLen: params.question.length });
        appendSideQuestion({
          question: params.question as string,
          answer:   params.answer as string,
        });
      }
    };

    client.adapter.on('ui:showSessionBrowser', handleShowSessionBrowser);
    client.adapter.on('ui:appendHistory', handleAppendHistory);
    client.adapter.on('ui:showModelSelector', handleShowModelSelector);
    client.adapter.on('ui:showEffortSelector', handleShowEffortSelector);
    client.adapter.on('ui:showThemeSelector', handleShowThemeSelector);
    client.adapter.on('ui:showTaskSelector', handleShowTaskSelector);
    client.adapter.on('ui:showPluginManager', handleShowPluginManager);
    client.adapter.on('ui:pluginInstallProgress', handlePluginInstallProgress);
    client.adapter.on('ui:showSideQuestion', handleShowSideQuestion);

    return () => {
      client.adapter.off('ui:showSessionBrowser', handleShowSessionBrowser);
      client.adapter.off('ui:appendHistory', handleAppendHistory);
      client.adapter.off('ui:showModelSelector', handleShowModelSelector);
      client.adapter.off('ui:showEffortSelector', handleShowEffortSelector);
      client.adapter.off('ui:showThemeSelector', handleShowThemeSelector);
      client.adapter.off('ui:showTaskSelector', handleShowTaskSelector);
      client.adapter.off('ui:showPluginManager', handleShowPluginManager);
      client.adapter.off('ui:pluginInstallProgress', handlePluginInstallProgress);
      client.adapter.off('ui:showSideQuestion', handleShowSideQuestion);
    };
  }, [client, setShowSessionBrowser, addMessage,
      setModelSelectorData, setEffortSelectorData, setThemeSelectorData, setTaskSelectorTasks, setInstallProgress, setPluginManagerData,
      appendSideQuestion]);
}
