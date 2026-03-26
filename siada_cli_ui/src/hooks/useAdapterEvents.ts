import { useEffect } from 'react';
import { logger } from '../utils/logger.js';
import { Message, MessageType } from '../types/index.js';
import type { PluginManagerData } from '../components/PluginManager/index.js';
import type { TaskItem } from '../components/TaskSelector/index.js';

interface AdapterEventHandlers {
  setShowSessionBrowser: (v: boolean) => void;
  clearMessages: () => void;
  addMessage: (msg: Message) => void;
  setModelSelectorData: (v: { models: string[]; currentModel: string } | null) => void;
  setTaskSelectorTasks: (v: TaskItem[] | null) => void;
  setInstallProgress: (v: { skillName: string; phase: string; percent: number } | null) => void;
  setPluginManagerData: (v: PluginManagerData | null) => void;
}

export function useAdapterEvents(client: any, handlers: AdapterEventHandlers): void {
  const {
    setShowSessionBrowser, clearMessages, addMessage,
    setModelSelectorData, setTaskSelectorTasks,
    setInstallProgress, setPluginManagerData,
  } = handlers;

  useEffect(() => {
    if (!client) return;

    const handleShowSessionBrowser = () => {
      logger.info('Received ui:showSessionBrowser');
      setShowSessionBrowser(true);
    };

    const handleLoadHistory = (params: any) => {
      logger.info('Received ui:loadHistory', { messageCount: params?.messages?.length ?? 0 });
      clearMessages();
      if (Array.isArray(params?.messages)) {
        for (const msg of params.messages) {
          if (msg.role && msg.content) {
            addMessage({
              id: `history-${Date.now()}-${Math.random()}`,
              type: (msg.role === 'user' ? 'user' : 'agent') as MessageType,
              content: msg.content,
              timestamp: new Date().toISOString(),
              author: msg.role === 'user' ? 'User' : 'Assistant',
              metadata: msg.subtype ? { subtype: msg.subtype } : undefined,
            });
          }
        }
      }
    };

    const handleShowModelSelector = (params: any) => {
      setModelSelectorData({
        models: params?.models ?? [],
        currentModel: params?.currentModel ?? '',
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

    client.adapter.on('ui:showSessionBrowser', handleShowSessionBrowser);
    client.adapter.on('ui:loadHistory', handleLoadHistory);
    client.adapter.on('ui:showModelSelector', handleShowModelSelector);
    client.adapter.on('ui:showTaskSelector', handleShowTaskSelector);
    client.adapter.on('ui:showPluginManager', handleShowPluginManager);
    client.adapter.on('ui:pluginInstallProgress', handlePluginInstallProgress);

    return () => {
      client.adapter.off('ui:showSessionBrowser', handleShowSessionBrowser);
      client.adapter.off('ui:loadHistory', handleLoadHistory);
      client.adapter.off('ui:showModelSelector', handleShowModelSelector);
      client.adapter.off('ui:showTaskSelector', handleShowTaskSelector);
      client.adapter.off('ui:showPluginManager', handleShowPluginManager);
      client.adapter.off('ui:pluginInstallProgress', handlePluginInstallProgress);
    };
  }, [client, setShowSessionBrowser, clearMessages, addMessage,
      setModelSelectorData, setTaskSelectorTasks, setInstallProgress, setPluginManagerData]);
}
