import React, { useEffect, useSyncExternalStore } from 'react';
import { Box, render, useApp } from '@jrichman/ink';
import { pathToFileURL } from 'node:url';
import { MainLayout } from '../dist/components/layouts/MainLayout.js';
import { AppProvider } from '../dist/store/context.js';
import { promptQueueStore } from '../dist/store/promptQueueStore.js';
import { KeypressProvider } from '../dist/contexts/KeypressContext.js';
import { useKeypress } from '../dist/hooks/useKeypress.js';
import { useQuitShortcut } from '../dist/hooks/useQuitShortcut.js';
import { useTerminalSize } from '../dist/hooks/useTerminalSize.js';
import { createWorkingStdio } from '../dist/utils/stdio.js';
import { getActiveTheme, setActiveTheme } from '../dist/themes/index.js';
import { slashCommandService } from '../dist/services/slashCommandService.js';
import { createDemoController } from './three-pane-demo-controller.mjs';
import { demoCommands, demoTasks } from './three-pane-demo-data.mjs';
import { ModelSelector } from '../dist/components/ModelSelector/ModelSelector.js';
import { ThemeSelector } from '../dist/components/ThemeSelector/ThemeSelector.js';
import { EffortSelector } from '../dist/components/EffortSelector/EffortSelector.js';
import { TaskSelector } from '../dist/components/TaskSelector/TaskSelector.js';
import { Scrollable } from '../dist/components/common/Scrollable.js';

export function Demo({ controller }) {
  const { exit } = useApp();
  const { rows, columns } = useTerminalSize();
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const quitShortcut = useQuitShortcut({
    running: state.loading || Boolean(state.goalState?.verifying) || Boolean(state.interactiveInput) || state.promptQueue.length > 0,
    onStop: controller.stop, onExit: exit, active: !state.screen && !state.sideQuestionPanelVisible,
  });
  useEffect(() => {
    if (state.screen?.startsWith('theme:')) {
      setActiveTheme(state.screen.slice(6));
      controller.closeScreen();
    }
  }, [state.screen, controller]);
  useKeypress(key => {
    if (key.name === 'escape' && state.interactiveInput) controller.cancelInteractiveInput();
    if (key.ctrl && key.name === 'o' && !state.screen && !state.sideQuestionPanelVisible) controller.toggleCollapsed();
  });

  let overlay = null;
  const overlayHeight = state.screen === 'effort' ? Math.min(9, rows - 5)
    : Math.max(8, Math.min(16, rows - 5));
  if (state.screen && !state.screen.startsWith('theme:')) {
    let picker = null;
    if (state.screen === 'model') picker = React.createElement(ModelSelector, {
      models: controller.models, currentModel: state.model, embedded: true, availableRows: overlayHeight,
      onSelect: controller.selectModel, onExit: controller.closeScreen,
    });
    if (state.screen === 'effort') picker = React.createElement(EffortSelector, {
      model: state.model, efforts: controller.efforts, current: state.reasoningEffort,
      embedded: true, onSelect: controller.selectEffort, onExit: controller.closeScreen,
    });
    if (state.screen === 'theme') picker = React.createElement(ThemeSelector, {
      themes: ['dark', 'light'], current: getActiveTheme(), embedded: true,
      onSelect: theme => { setActiveTheme(theme); controller.closeScreen(); }, onExit: controller.closeScreen,
    });
    if (state.screen === 'tasks') picker = React.createElement(TaskSelector, {
      tasks: demoTasks, onSelect: task => { controller.closeScreen(); controller.submit(task.description); },
      onExit: controller.closeScreen,
    });
    overlay = React.createElement(Scrollable, {
      width: columns, height: overlayHeight, hasFocus: true, mouseOnly: true, scrollToBottom: false,
    }, picker);
  }

  return React.createElement(MainLayout, {
    ...state, demoPresentation: true, demoOverlay: overlay, demoOverlayHeight: overlayHeight,
    version: 'demo', workingDir: '.', provider: 'offline', agent: 'coder',
    isReady: true, sessionId: `synthetic-three-pane-demo-${state.sceneId}`,
    onSendMessage: controller.submit, onAddMessage: controller.addMessage, onUpdateMessage: controller.updateMessage,
    onStopExecution: controller.stop, onFlushQueueAndRun: () => controller.stop(false),
    onCtrlC: quitShortcut.onCtrlC, interruptNotice: quitShortcut.notice,
    onCancelPendingQueue: () => {},
    onSendInteractiveInput: controller.sendInteractiveInput,
    onHideSideQuestionPanel: controller.hideSideQuestion,
    onClearSideQuestionsHistory: controller.clearSideQuestions,
    onRemoveSideQuestion: controller.removeSideQuestion, onForkSideQuestion: controller.forkSideQuestion,
  });
}

export async function startDemo() {
  slashCommandService.updateCommandsFromBackend(demoCommands);
  const controller = createDemoController({ queue: promptQueueStore, presentation: true });
  const { stdout, stderr } = createWorkingStdio();
  const app = render(React.createElement(KeypressProvider, null,
    React.createElement(AppProvider, null, React.createElement(Demo, { controller }))), {
    stdout, stderr, stdin: process.stdin, alternateBuffer: true, incrementalRendering: true,
    patchConsole: false, exitOnCtrlC: false, maxFps: 60,
  });
  try { await app.waitUntilExit(); }
  finally { controller.dispose(); app.cleanup(); }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await startDemo();