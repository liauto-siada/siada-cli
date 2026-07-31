#!/usr/bin/env node

/**
 * CLI entry point for siada-cli-ui.
 *
 * Responsibilities:
 *  - readVersion:     reads the package version from pyproject.toml
 *  - configureLogger: maps --debug / --log-level flags to internal LogLevel
 *  - parseSiadaArgs:  shell-like tokenizer for the --siada-args passthrough string
 *  - buildConfig:     resolves launch mode (executable vs. module) and builds ClientConfig
 *  - renderApp:       mounts the React/Ink component tree and manages the process lifecycle
 *  - createProgram:   declares all CLI flags and wires them to the action handler
 */

import { Command } from 'commander';
import { render } from '@jrichman/ink';
import React from 'react';
import { App } from './components/App.js';
import { configManager } from './utils/config.js';
import { logger, LogLevel } from './utils/logger.js';
import { readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { printTerminalWarning, getTerminalInfoString } from './utils/terminalDetector.js';
import { KeypressProvider } from './contexts/KeypressContext.js';
import { createWorkingStdio } from './utils/stdio.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// T0: module load complete (imports done, ready to run)
const _T0 = Date.now();

function readVersion(): string {
  try {
    const content = readFileSync(join(__dirname, '../../pyproject.toml'), 'utf-8');
    const match = content.match(/^version\s*=\s*"([^"]+)"/m);
    return match ? match[1] : '0.1.0';
  } catch (error) {
    logger.error('Failed to read version from pyproject.toml', error);
    return '0.1.0';
  }
}

function configureLogger(options: any): void {
  if (options.debug || process.env.SIADA_DEBUG) {
    process.env.SIADA_DEBUG = '1';
    logger.setLevel(LogLevel.DEBUG);
    return;
  }
  const levelMap: Record<string, LogLevel> = {
    debug: LogLevel.DEBUG,
    info: LogLevel.INFO,
    warn: LogLevel.WARN,
    error: LogLevel.ERROR,
  };
  logger.setLevel(levelMap[options.logLevel] || LogLevel.INFO);
}

function parseSiadaArgs(raw: string): string[] | undefined {
  if (!raw?.trim()) return undefined;
  const args: string[] = [];
  let current = '';
  let inQuote = false;
  let quoteChar = '';
  for (const char of raw.trim()) {
    if ((char === '"' || char === "'") && !inQuote) {
      inQuote = true;
      quoteChar = char;
    } else if (char === quoteChar && inQuote) {
      inQuote = false;
      quoteChar = '';
    } else if (char === ' ' && !inQuote) {
      if (current) { args.push(current); current = ''; }
    } else {
      current += char;
    }
  }
  if (current) args.push(current);
  logger.debug('Parsed siada-args', { original: raw, parsed: args });
  return args;
}

function buildConfig(workingDir: string, options: any) {
  const pythonPath = options.pythonPath || process.env.SIADA_PYTHON_PATH;
  const siadaModule = options.siadaModule || process.env.SIADA_MODULE_PATH;
  const useModuleMode = options.useModuleMode || (pythonPath && siadaModule) || false;

  return configManager.buildClientConfig({
    workingDir,
    model: options.model,
    temperature: options.temperature,
    maxTokens: options.maxTokens,
    thinking: options.thinking,
    reasoningEffort: options.reasoningEffort,
    parallelToolCalls: options.parallelToolCalls,
    siadaPath: options.siadaPath,
    pythonPath,
    siadaModule,
    useModuleMode,
    acpMode: options.acpMode,
    siadaArgs: parseSiadaArgs(options.siadaArgs),
  });
}

function renderApp(config: any, options: any): void {
  const { stdout: inkStdout, stderr: inkStderr } = createWorkingStdio();
  let sessionIdOnExit: string | null = null;

  const AppWithProvider = React.createElement(
    KeypressProvider,
    null,
    React.createElement(App, { config, onExit: (id) => { sessionIdOnExit = id; } })
  );

  // alternateBuffer defaults to false (scrollable mode with terminal history).
  // incrementalRendering must stay in sync: enabling it without alternateBuffer
  // causes frequent eraseLines and is unsafe.
  const useAlternateBuffer = options.alternateBuffer === true;

  logger.info(`[ui-timing] phase=render_called        elapsed_ms=${Date.now() - _T0}`);
  const { waitUntilExit } = render(AppWithProvider, {
    stdout: inkStdout,
    stderr: inkStderr,
    stdin: process.stdin,
    patchConsole: false,
    exitOnCtrlC: false,
    alternateBuffer: useAlternateBuffer,
    incrementalRendering: useAlternateBuffer,
    maxFps: 30,
    onRender: ({ renderTime }: { renderTime: number }) => {
      if (renderTime > 100) logger.warn(`Slow render detected: ${renderTime}ms`);
    },
  });

  waitUntilExit().then(() => {
    logger.info('Application exited normally');
    if (sessionIdOnExit) {
      process.stdout.write(`\nTo continue this session, run: siada-cli --resume ${sessionIdOnExit}\n`);
    }
    // Use setImmediate to give React one event-loop tick to flush any pending
    // state updates (e.g. setPluginManagerData(null)) before process.exit.
    // Without this, yoga WASM crashes during Ink's final render because the
    // PluginManager is still in the component tree when process.exit fires.
    setImmediate(() => process.exit(0));
  }).catch((error) => {
    logger.error('Application exited with error', error);
    setImmediate(() => process.exit(1));
  });
}

function createProgram(): Command {
  return new Command()
    .name('siada-ui')
    .description('Terminal UI for siada-cli')
    .version(readVersion())
    .argument('[working-dir]', 'Working directory', process.cwd())
    .option('-m, --model <model>', 'AI model to use')
    .option('-t, --temperature <temperature>', 'Model temperature', parseFloat)
    .option('--max-tokens <tokens>', 'Maximum tokens', parseInt)
    .option('--thinking', 'Enable thinking/reasoning for models that support it')
    .option('--no-thinking', 'Disable thinking/reasoning')
    .option('--reasoning-effort <level>', 'Set reasoning effort level (low, medium, high)')
    .option('--parallel-tool-calls', 'Enable parallel tool calls for models that support it')
    .option('--no-parallel-tool-calls', 'Disable parallel tool calls')
    .option('--siada-path <path>', 'Path to siada-cli executable')
    .option('--python-path <path>', 'Path to Python interpreter (for module mode)')
    .option('--siada-module <path>', 'Path to siada-agenthub module directory')
    .option('--use-module-mode', 'Use Python module mode instead of executable')
    .option('--siada-args <args>', 'Additional arguments for siada-cli', '')
    .option('--acp-mode', 'Enable ACP mode for siada-agenthub communication (enabled by default)', true)
    .option('--no-acp-mode', 'Disable ACP mode')
    .option('--alternate-buffer', 'Use alternate screen buffer (full-screen mode)')
    .option('--no-alternate-buffer', 'Disable alternate buffer (scrollable mode, preserves history, enabled by default)', true)
    .option('--debug', 'Enable debug logging')
    .option('--log-level <level>', 'Log level (debug, info, warn, error)', 'info');
}

function main(): void {
  process.on('uncaughtException', (error: Error) => {
    logger.error('Uncaught exception', error);
    process.exit(1);
  });

  process.on('unhandledRejection', (reason: any) => {
    logger.error('Unhandled rejection', reason);
    process.exit(1);
  });

  createProgram()
    .action((workingDir: string, options: any) => {
      configureLogger(options);
      logger.info(`[ui-timing] phase=logger_configured  elapsed_ms=${Date.now() - _T0}`);

      logger.info('Starting siada-cli-ui', { workingDir, options });

      const config = buildConfig(workingDir, options);
      logger.info(`[ui-timing] phase=config_built        elapsed_ms=${Date.now() - _T0}`);
      logger.info(getTerminalInfoString());

      try {
        renderApp(config, options);
      } catch (error) {
        logger.error('Failed to render application', error);
        process.exit(1);
      }
    })
    .parse();
}

main();
