/**
 * siada-cli ACP Adapter
 * Bridges communication between ACP protocol and siada-cli process
 * 
 * DESIGN NOTES:
 * siada-cli uses plain text I/O, NOT structured protocols like ACP:
 * - INPUT: Text goes directly to stdin (like typing in a terminal)
 * - OUTPUT: Plain text from stdout (human-readable, not machine-parsable)
 * 
 * This adapter:
 * 1. Converts ACP messages to plain text input for siada-cli
 * 2. Captures stdout line-by-line and wraps as ACP message events
 * 3. Does NOT parse for special markers or structured data
 * 4. Preserves the natural text-based interaction flow
 */

import { spawn, ChildProcess } from 'child_process';
import { EventEmitter } from 'events';
import { ClientConfig, ACPMessage, ACPEvent } from '../types/index.js';
import { logger, LogLevel } from '../utils/logger.js';

const MAX_RESTART_ATTEMPTS = 3;
const RESTART_DELAY = 2000;
const MAX_BUFFER_SIZE = 100*1024 * 1024;
const MAX_LINE_LENGTH = 100*1024 * 1024;

export class SiadaACPAdapter extends EventEmitter {
  private process: ChildProcess | null = null;
  private messageBuffer: string = '';
  private restartAttempts: number = 0;
  private isReady: boolean = false;
  private readyResolver: (() => void) | null = null;
  
  // Lifecycle event tracking (for Slash commands)
  private slashCommandBuffer: {
    command: string;
    taskId: string;
    content: string[];
    startTime: number;
    isActive: boolean;
  } | null = null;
  
  // Streaming message tracking (for conversations)
  private streamingBuffer: {
    messageId: string;
    messageType: string;
    content: string[];
    isActive: boolean;
  } | null = null;
  
  // Tool use tracking (for tool call lifecycle events)
  private toolUseBuffer: {
    content: string[];
    chunkCount: number;
  } | null = null;
  
  // Flag to prevent duplicate message emission
  private isProcessingLifecycleEvent: boolean = false;

  private redactSensitiveInput(input: string): string {
    if (!input) return input;

    if (input.startsWith('__LOGIN_CHOICE__:3:')) {
      return '__LOGIN_CHOICE__:3:[REDACTED_LOGIN_PAYLOAD]';
    }

    return input
      .replace(/("api_key"\s*:\s*")([^"]+)(")/gi, '$1***FILTERED***$3')
      .replace(/("token"\s*:\s*")([^"]+)(")/gi, '$1***FILTERED***$3')
      .replace(/("authorization"\s*:\s*")([^"]+)(")/gi, '$1***FILTERED***$3');
  }

  private async writeInputToStdin(input: string, meta: { messageId?: string; operation: string; method: string }): Promise<void> {
    const writeData = `<<<SIADA_MSG_START>>>\n${input}\n<<<SIADA_MSG_END>>>\n`;
    const safeInput = this.redactSensitiveInput(input);
    const safeWriteData = this.redactSensitiveInput(writeData);

    logger.info('About to write to stdin', {
      component: 'Adapter',
      operation: meta.operation,
      messageId: meta.messageId,
      method: meta.method,
      writeData: safeWriteData,
      stdinWritable: this.process?.stdin?.writable,
      stdinDestroyed: this.process?.stdin?.destroyed,
    });

    const written = this.process?.stdin?.write(writeData);

    logger.info('Write completed', {
      component: 'Adapter',
      operation: meta.operation,
      messageId: meta.messageId,
      method: meta.method,
      written,
      stdinWritable: this.process?.stdin?.writable,
    });

    logger.debug('Stdin write result', {
      component: 'Adapter',
      operation: meta.operation,
      messageId: meta.messageId,
      method: meta.method,
      written,
      dataLength: writeData.length,
      safeInput,
    });
  }

  /**
   * Start siada-cli process
   */
  async start(config: ClientConfig): Promise<void> {
    const startTime = Date.now();
    logger.info('Starting siada-cli adapter', {
      component: 'Adapter',
      operation: 'start',
      config: {
        workingDir: config.workingDir,
        model: config.model,
        siadaPath: config.siadaPath || 'siada-cli',
      },
    });

    const { command, args } = this.buildCommand(config);
    logger.debug('Built siada-cli command', {
      component: 'Adapter',
      operation: 'start',
      command,
      args,
    });
    
    // Build environment variables
    const env: Record<string, string> = { 
      ...process.env as Record<string, string>, 
      ...(config.env || {}),
      PYTHONIOENCODING: 'utf-8',
      PYTHONUNBUFFERED: '1',
    };

    // Set ACP mode environment variable
    if (config.acpMode) {
      env.SIADA_ACP_MODE = '1';
      logger.debug('Set SIADA_ACP_MODE environment variable', {
        component: 'Adapter',
        operation: 'start',
      });
    }

    // Add PYTHONPATH for module mode
    if (config.useModuleMode && config.siadaModule) {
      const existingPath = env.PYTHONPATH || '';
      env.PYTHONPATH = existingPath 
        ? `${config.siadaModule}:${existingPath}`
        : config.siadaModule;
      
      logger.debug('Set PYTHONPATH for module mode', {
        component: 'Adapter',
        operation: 'start',
        pythonPath: env.PYTHONPATH,
      });
    }
    
    try {
      const spawnStart = Date.now();
      this.process = spawn(command, args, {
        cwd: config.workingDir,
        stdio: ['pipe', 'pipe', 'pipe'],
        env,
        // On Windows, hide the console window that Node.js would otherwise
        // create for the spawned Python subprocess. Without this flag a blank
        // black cmd window pops up every time the backend process starts.
        windowsHide: true,
      });

      logger.info(`[PERF][adapter] Python process spawned (pid=${this.process.pid}) | +${Date.now() - startTime}ms since adapter.start()`);

      this.setupEventHandlers();
      
      // Wait for siada-cli to be ready (shows welcome banner)
      const waitStart = Date.now();
      await this.waitForReady();
      logger.info(`[PERF][adapter] waitForReady done | waited ${Date.now() - waitStart}ms | total +${Date.now() - startTime}ms`);
      
      logger.logWithTiming(
        LogLevel.INFO,
        'siada-cli adapter started successfully',
        startTime,
        {
          component: 'Adapter',
          operation: 'start',
          pid: this.process.pid,
        }
      );
      
      // Emit ready event after siada-cli is confirmed ready
      this.emit('ready');
    } catch (error) {
      logger.error('Failed to start siada-cli adapter', error, {
        component: 'Adapter',
        operation: 'start',
        duration: Date.now() - startTime,
      });
      throw error;
    }
  }

  /**
   * Build command and arguments for siada-cli
   */
  private buildCommand(config: ClientConfig): { command: string; args: string[] } {
    const args: string[] = [...(config.siadaArgs || [])];

    // Add --no-fancy-input to disable prompt_toolkit fancy input
    // This is critical when stdin is not a TTY (piped/programmatic input)
    args.push('--no-fancy-input');

    // Add --no-banner to disable banner output from siada-cli
    // The UI will handle banner display independently
    args.push('--no-banner');

    // Add --acp flag if ACP mode is enabled
    if (config.acpMode) {
      args.push('--acp');
      logger.info('ACP mode enabled, adding --acp flag', {
        component: 'Adapter',
        operation: 'buildCommand',
      });
    }

    // Only add --model if it's not already in siadaArgs
    // This prevents duplicate --model parameters where siadaArgs takes precedence
    if (config.model) {
      const hasModelInSiadaArgs = config.siadaArgs?.some((arg, index, arr) => 
        arg === '--model' || (index > 0 && arr[index - 1] === '--model')
      );
      
      if (!hasModelInSiadaArgs) {
        args.push('--model', config.model);
        logger.info('Adding --model from config', {
          component: 'Adapter',
          operation: 'buildCommand',
          model: config.model,
        });
      } else {
        logger.info('Skipping --model from config (already in siadaArgs)', {
          component: 'Adapter',
          operation: 'buildCommand',
          configModel: config.model,
          siadaArgs: config.siadaArgs,
        });
      }
    }

    // Add --reasoning-effort if specified
    if (config.reasoningEffort) {
      args.push('--reasoning-effort', config.reasoningEffort);
      logger.info('Adding --reasoning-effort flag', {
        component: 'Adapter',
        operation: 'buildCommand',
        reasoningEffort: config.reasoningEffort,
      });
    }

    // Add --thinking or --no-thinking if specified
    if (config.thinking !== undefined) {
      if (config.thinking) {
        args.push('--thinking');
        logger.info('Adding --thinking flag', {
          component: 'Adapter',
          operation: 'buildCommand',
        });
      } else {
        args.push('--no-thinking');
        logger.info('Adding --no-thinking flag', {
          component: 'Adapter',
          operation: 'buildCommand',
        });
      }
    }

    // Add --parallel-tool-calls or --no-parallel-tool-calls if specified
    if (config.parallelToolCalls !== undefined) {
      if (config.parallelToolCalls) {
        args.push('--parallel-tool-calls');
        logger.info('Adding --parallel-tool-calls flag', {
          component: 'Adapter',
          operation: 'buildCommand',
        });
      } else {
        args.push('--no-parallel-tool-calls');
        logger.info('Adding --no-parallel-tool-calls flag', {
          component: 'Adapter',
          operation: 'buildCommand',
        });
      }
    }

    // Check if using module mode
    if (config.useModuleMode && config.pythonPath && config.siadaModule) {
      logger.info('Using Python module mode', {
        component: 'Adapter',
        operation: 'buildCommand',
        pythonPath: config.pythonPath,
        siadaModule: config.siadaModule,
      });

      // Module mode: python -m siada.entrypoint.siadahub
      return {
        command: config.pythonPath,
        args: ['-m', 'siada.entrypoint.siadahub', ...args],
      };
    }

    // Executable mode: siada-cli
    logger.info('Using executable mode', {
      component: 'Adapter',
      operation: 'buildCommand',
      siadaPath: config.siadaPath || 'siada-cli',
    });

    return {
      command: config.siadaPath || 'siada-cli',
      args,
    };
  }

  /**
   * Setup event handlers for siada-cli process
   */
  private setupEventHandlers(): void {
    if (!this.process) return;

    logger.info('Setting up event handlers for siada-cli process', {
      component: 'Adapter',
      operation: 'setupEventHandlers',
      pid: this.process.pid,
      hasStdout: !!this.process.stdout,
      hasStderr: !!this.process.stderr,
      hasStdin: !!this.process.stdin,
    });

    if (!this.process.stdout) {
      logger.error('process.stdout is null!', undefined, {
        component: 'Adapter',
        operation: 'setupEventHandlers',
      });
    }

    this.process.stdout?.on('data', (data: Buffer) => {
      // Limit chunk size to prevent excessive memory usage, but don't skip data
      const chunk = data.toString('utf8', 0, Math.min(data.length, 65536)); // Limit chunk size to 64KB
      
      // Log data reception (debug level to reduce log volume)
      logger.debug('STDOUT data received', {
        component: 'Adapter',
        operation: 'stdout',
        chunkSize: chunk.length,
        preview: chunk.substring(0, 100),
      });
      
      // Check buffer size before adding more data
      if (this.messageBuffer.length + chunk.length > MAX_BUFFER_SIZE) {
        logger.warn('Buffer size limit exceeded, clearing old data', {
          component: 'Adapter',
          operation: 'stdout',
          bufferSize: this.messageBuffer.length,
          chunkSize: chunk.length,
          maxSize: MAX_BUFFER_SIZE,
        });
        // Keep only the last half of the buffer to prevent complete data loss
        this.messageBuffer = this.messageBuffer.substring(this.messageBuffer.length / 2);
      }
      
      // Ready detection is now handled by handleACPSessionUpdate (banner_info signal).
      
      logger.debug('Adding chunk to message buffer', {
        component: 'Adapter',
        operation: 'stdout',
        bufferSizeBefore: this.messageBuffer.length,
        chunkSize: chunk.length,
      });
      
      this.messageBuffer += chunk;
      
      logger.debug('Buffer state before processing', {
        component: 'Adapter',
        operation: 'stdout',
        bufferSize: this.messageBuffer.length,
      });
      
      this.processBuffer();
    });

    this.process.stderr?.on('data', (data: Buffer) => {
      const message = data.toString();
      
      // ALWAYS print stderr to console for debugging
      // console.error('\n========== STDERR OUTPUT ==========');
      // console.error(message);
      // console.error('===================================\n');
      
      // Filter out harmless warnings that don't need user attention
      const isHarmlessWarning = 
        message.includes('Input is not a terminal') ||
        message.includes('fd=0') ||
        message.includes('not a tty');
      
      if (isHarmlessWarning) {
        // Log at debug level instead of warning
        logger.debug('siada-cli stderr (filtered harmless warning)', {
          component: 'Adapter',
          operation: 'stderr',
          message: message.substring(0, 100),
        });
      } else {
        // Log actual warnings/errors normally
        logger.warn('siada-cli stderr output', {
          component: 'Adapter',
          operation: 'stderr',
          message,
        });
        this.emit('stderr', message);
      }
    });

    this.process.on('error', (error: Error) => {
      logger.error('siada-cli process error', error, {
        component: 'Adapter',
        operation: 'process_error',
        pid: this.process?.pid,
      });
      this.emit('error', error);
    });

    this.process.on('exit', (code: number | null) => {
      logger.logStateChange('Adapter', 'running', 'exited', {
        exitCode: code,
        pid: this.process?.pid,
      });
      this.emit('exit', code);
      
      if (code !== 0 && code !== null) {
        this.handleCrash(code);
      }
    });
  }

  /**
   * Process output buffer - groups siada-cli output into logical blocks
   * siada-cli uses box-drawing characters and multi-line formatted output
   * 
   * Uses \x1E (Record Separator) as message delimiter for reliable parsing
   */
  private processBuffer(): void {
    logger.debug('Process buffer start', {
      component: 'Adapter',
      operation: 'processBuffer',
      bufferSize: this.messageBuffer.length,
    });
    
    // First, split by Record Separator (\x1E) to get individual messages
    // This ensures ACP JSON messages are properly separated even if they arrive in the same chunk
    const RS = '\x1E';  // Record Separator character
    let processedBuffer = this.messageBuffer;
    const linesToProcess: string[] = [];
    let remainingBuffer = '';
    
    // If buffer contains RS, split by RS first to extract ACP messages
    if (processedBuffer.includes(RS)) {
      const parts = processedBuffer.split(RS);
      
      for (let i = 0; i < parts.length; i++) {
        const part = parts[i];
        if (i === 0) {
          // First part is content before first RS (may be incomplete line from previous chunk)
          if (part.trim()) {
            const subLines = part.split('\n');
            // Last line before RS might be incomplete
            for (let j = 0; j < subLines.length - 1; j++) {
              if (subLines[j].trim()) {
                linesToProcess.push(subLines[j]);
              }
            }
            // Keep last line if it doesn't end with newline
            const lastSubLine = subLines[subLines.length - 1];
            if (lastSubLine.trim()) {
              linesToProcess.push(lastSubLine);
            }
          }
        } else if (i === parts.length - 1) {
          // Last part after RS - might be incomplete (no trailing newline)
          // NOTE:
          // The last RS-part may contain *multiple* newline-separated lines, e.g.
          //   {"jsonrpc": ... "reason": "input_ready" ...}\n
          //   ───────────────────────────────...\n
          // In this case, treating the whole part as "incomplete JSON" (just because it
          // doesn't end with `}`) would delay parsing of the JSON line until next stdout chunk.
          //
          // Strategy:
          // - Split into lines.
          // - Push all *complete* lines into processing queue.
          // - Only keep the very last line as remainingBuffer (possible incomplete JSON).

          const subLines = part.split('\n');

          // Process all lines except the last one (they are complete because we saw a '\n')
          for (let j = 0; j < subLines.length - 1; j++) {
            const subLine = subLines[j].trim();
            if (subLine) {
              linesToProcess.push(subLine);
            }
          }

          // Keep only the last (possibly incomplete) line in buffer
          const lastSubLineRaw = subLines[subLines.length - 1] ?? '';
          const lastSubLine = lastSubLineRaw.trim();
          if (lastSubLine) {
            // Decide completeness by actually trying to parse the JSON,
            // instead of a naive startsWith('{')/endsWith('}') heuristic.
            // The naive check breaks when a large message (e.g. banner_info,
            // which embeds long command descriptions) gets split by the OS
            // pipe right after an inner, non-terminal '}' character - the
            // heuristic would wrongly treat the truncated half as "complete",
            // causing JSON.parse to throw and the whole message to be
            // silently dropped instead of being buffered for the next chunk.
            if (lastSubLine.startsWith('{')) {
              try {
                JSON.parse(lastSubLine);
                // Parses cleanly as a whole JSON value -> genuinely complete.
                linesToProcess.push(lastSubLine);
              } catch (err) {
                // Not valid JSON yet -> likely truncated, wait for more data.
                logger.info('Incomplete JSON in last sub-line, buffering for next chunk', {
                  length: lastSubLine.length,
                  preview: lastSubLine.slice(0, 200),
                  tail: lastSubLine.slice(-200),
                  error: err instanceof Error ? err.message : String(err),
                });
                remainingBuffer = lastSubLine;
              }
            } else {
              linesToProcess.push(lastSubLine);
            }
          }
        } else {
          // Middle parts after RS are complete ACP messages
          const subLines = part.split('\n');
          for (const subLine of subLines) {
            if (subLine.trim()) {
              linesToProcess.push(subLine);
            }
          }
        }
      }
      
      // Set remaining buffer
      this.messageBuffer = remainingBuffer.length > MAX_LINE_LENGTH 
        ? remainingBuffer.substring(remainingBuffer.length - MAX_LINE_LENGTH) 
        : remainingBuffer;
    } else {
      // No RS in buffer, use traditional newline-based splitting
      const lines = processedBuffer.split('\n');
      // Keep the last incomplete line in buffer (with size limit)
      const lastLine = lines.pop() || '';
      this.messageBuffer = lastLine.length > MAX_LINE_LENGTH 
        ? lastLine.substring(lastLine.length - MAX_LINE_LENGTH) 
        : lastLine;
      
      for (const line of lines) {
        if (line.trim()) {
          linesToProcess.push(line);
        }
      }
    }

    logger.debug('Buffer split into lines', {
      component: 'Adapter',
      operation: 'processBuffer',
      lineCount: linesToProcess.length,
      bufferRemaining: this.messageBuffer.length,
    });

    for (let i = 0; i < linesToProcess.length; i++) {
      let line = linesToProcess[i];
      
      // Truncate excessively long lines to prevent memory issues
      if (line.length > MAX_LINE_LENGTH) {
        logger.warn('Line exceeds maximum length, truncating', {
          component: 'Adapter',
          operation: 'processBuffer',
          lineIndex: i,
          originalLength: line.length,
          maxLength: MAX_LINE_LENGTH,
        });
        line = line.substring(0, MAX_LINE_LENGTH) + '... [truncated]';
      }
      
      logger.debug(`Processing line ${i + 1}/${linesToProcess.length}`, {
        component: 'Adapter',
        operation: 'processBuffer',
        lineIndex: i,
        lineLength: line.length,
      });
      this.processLine(line);
    }
    
    logger.debug('Process buffer end', {
      component: 'Adapter',
      operation: 'processBuffer',
      processedLines: linesToProcess.length,
      remainingBuffer: this.messageBuffer.length,
    });
  }

  /**
   * Process a single line - parse as ACP JSON, skip all non-JSON output
   */
  private processLine(line: string): void {
    const cleanedLine = line.replace(/\r/g, '');
    if (!cleanedLine.trim()) return;
    if (this.tryParseACPJson(cleanedLine)) return;
    logger.debug('Non-ACP output, skipping', {
      component: 'Adapter',
      operation: 'processLine',
      linePreview: cleanedLine.substring(0, 100),
    });
  }

  /**
   * Try to parse line as ACP JSON message
   * Returns true if successfully parsed and emitted
   */
  private tryParseACPJson(line: string): boolean {
    try {
      const json = JSON.parse(line);
      
      // Check if it's a valid ACP message (JSON-RPC 2.0)
      if (json.jsonrpc === '2.0' && json.method) {
        logger.info('✅ Parsed ACP JSON message', {
          component: 'Adapter',
          operation: 'tryParseACPJson',
          method: json.method,
          hasParams: !!json.params,
          reason: json.params?.reason,
        });
        
        // Handle session/update notifications
        if (json.method === 'session/update') {
          this.handleACPSessionUpdate(json);
          return true;
        }
        
        // Handle ui/showSessionBrowser notifications
        if (json.method === 'ui/showSessionBrowser') {
          logger.info('Received ui/showSessionBrowser notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            params: json.params,
          });

          // Emit as a custom event that App.tsx can listen to
          this.emit('ui:showSessionBrowser', json.params);
          return true;
        }

        // Handle ui/showTaskSelector notifications
        if (json.method === 'ui/showTaskSelector') {
          logger.info('Received ui/showTaskSelector notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            taskCount: json.params?.tasks?.length || 0,
          });

          this.emit('ui:showTaskSelector', json.params);
          return true;
        }

        // Handle ui/showModelSelector notifications
        if (json.method === 'ui/showModelSelector') {
          logger.info('Received ui/showModelSelector notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            modelCount: json.params?.models?.length || 0,
            currentModel: json.params?.currentModel,
          });

          this.emit('ui:showModelSelector', json.params);
          return true;
        }

        // Handle ui/showPluginManager notifications
        if (json.method === 'ui/showPluginManager') {
          logger.info('Received ui/showPluginManager notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            installedCount: json.params?.installed?.length || 0,
            marketplacesCount: json.params?.marketplaces?.length || 0,
          });

          this.emit('ui:showPluginManager', json.params);
          return true;
        }

        // Handle ui/showSideQuestion notifications
        if (json.method === 'ui/showSideQuestion') {
          logger.info('Received ui/showSideQuestion notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            questionLen: json.params?.question?.length ?? 0,
            answerLen:   json.params?.answer?.length ?? 0,
          });
          this.emit('ui:showSideQuestion', json.params);
          return true;
        }

        // Handle ui/memoryStatusChanged notifications
        if (json.method === 'ui/memoryStatusChanged') {
          logger.info('Received ui/memoryStatusChanged notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            enabled: json.params?.enabled,
          });
          this.emit('ui:memoryStatusChanged', json.params);
          return true;
        }

        if (json.method === 'ui/pluginInstallProgress') {
          this.emit('ui:pluginInstallProgress', json.params);
          return true;
        }

        // Handle ui/loadHistory notifications (batch load, clears existing)
        if (json.method === 'ui/loadHistory') {
          logger.info('Received ui/loadHistory notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            messageCount: json.params?.messages?.length || 0,
          });

          this.emit('ui:loadHistory', json.params);
          return true;
        }

        // Handle ui/appendHistory notifications (append-only, for deferred rendering)
        if (json.method === 'ui/appendHistory') {
          logger.info('Received ui/appendHistory notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            messageCount: json.params?.messages?.length || 0,
          });

          this.emit('ui:appendHistory', json.params);
          return true;
        }

        // Handle session/pullHistoryDone notifications (deferred rendering completion signal)
        if (json.method === 'session/pullHistoryDone') {
          logger.info('Received session/pullHistoryDone notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            signature: json.params?.signature,
          });

          this.emit('session:pullHistoryDone', json.params);
          return true;
        }

        // Handle login flow notifications
        if (json.method === 'ui/showLoginSelector') {
          logger.info('Received ui/showLoginSelector notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
          });
          this.emit('ui:showLoginSelector', json.params);
          return true;
        }

        if (json.method === 'ui/loginDeviceUrl') {
          logger.info('Received ui/loginDeviceUrl notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            url: json.params?.url,
          });
          this.emit('ui:loginDeviceUrl', json.params);
          return true;
        }

        if (json.method === 'ui/loginSuccess') {
          logger.info('Received ui/loginSuccess notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            userId: json.params?.userId,
          });
          this.emit('ui:loginSuccess', json.params);
          return true;
        }

        if (json.method === 'ui/loginError' || json.method === 'ui/loginCancelled') {
          logger.info(`Received ${json.method} notification`, {
            component: 'Adapter',
            operation: 'tryParseACPJson',
          });
          this.emit('ui:loginDismiss', json.params);
          return true;
        }

        // Handle context/todoState notifications (live todo state push from backend)
        if (json.method === 'context/todoState') {
          logger.info('Received context/todoState notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            todoCount: json.params?.todos?.length || 0,
          });
          this.emit('context:todoState', json.params);
          return true;
        }

        // Handle context/goalState notifications (live /goal state push from backend)
        if (json.method === 'context/goalState') {
          logger.info('Received context/goalState notification', {
            component: 'Adapter',
            operation: 'tryParseACPJson',
            goalStatus: json.params?.goal?.status,
            verifying: json.params?.verifying,
          });
          this.emit('context:goalState', json.params);
          return true;
        }

        // Handle other ACP messages
        logger.debug('Received ACP message', {
          component: 'Adapter',
          method: json.method,
          params: json.params,
        });
        
        return true;
      }
      
      // Valid JSON but not ACP format
      return false;
    } catch (e) {
      // Not JSON, will be handled as text
      return false;
    }
  }
  
  /**
   * Handle ACP session/update notification
   */
  private handleACPSessionUpdate(json: any): void {
    const params = json.params || {};
    const reason = params.reason;
    const content = params.content || '';
    const metadata = params._meta || params.metadata || {};
    const chunkType = metadata.chunkType;
    const isStreaming = metadata.isStreaming !== undefined ? metadata.isStreaming : true;
    const streamEnd = metadata.streamEnd || false;
    const streamStartId = metadata.streamStartId; // 🆕 Extract streamStartId from metadata
    
    logger.info('📨 ACP session/update', {
      component: 'Adapter',
      operation: 'handleACPSessionUpdate',
      reason,
      chunkType,
      isStreaming,
      streamEnd,
      contentLength: content.length,
    });
    
    // Map ACP reasons to our event types
    switch (reason) {
      case 'thinking':
      case 'message_chunk':
        // If there's an active slash command, buffer the content instead of emitting
        if (this.slashCommandBuffer && this.slashCommandBuffer.isActive) {
          logger.debug('📦 Buffering message for slash command', {
            component: 'Adapter',
            command: this.slashCommandBuffer.command,
            contentLength: content.length,
          });
          this.slashCommandBuffer.content.push(content);
          break;
        }
        
        // Skip if we're processing this through lifecycle streaming events
        // This prevents duplicate message emission for conversations
        if (this.streamingBuffer && this.streamingBuffer.isActive) {
          logger.debug('⏭️ Skipping message_chunk - handled by lifecycle streaming', {
            component: 'Adapter',
            reason,
          });
          break;
        }
        
        // Normal message handling (for backward compatibility)
        // Determine subtype from chunkType or reason
        let subtype: string | undefined;
        if (chunkType) {
          subtype = chunkType; // 'thinking', 'answer', 'tool_use'
        } else if (reason === 'thinking') {
          subtype = 'thinking';
        }
        
        // Determine message type based on metadata level
        const messageType = metadata.level === 'info' ? 'system' : 'agent';
        
        const acpEvent: ACPEvent = {
          type: 'message',
          data: {
            content,
            blockType: messageType,
            subtype,
            isStreaming,
            streamEnd,
            streamStartId, // 🆕 Pass streamStartId to event data
          },
          timestamp: new Date().toISOString(),
        };
        
        this.emit('message', acpEvent);
        break;
        
      case 'tool_call':
        // Tool call notification
        const toolEvent: ACPEvent = {
          type: 'toolUse',
          data: {
            name: metadata.toolName || 'unknown',
            toolCallId: params.toolCallId,
            content,
          },
          timestamp: new Date().toISOString(),
        };
        
        this.emit('message', toolEvent);
        break;
        
      case 'completed':
        // Session completed
        logger.info('✓ Session completed', {
          component: 'Adapter',
          finalAnswer: content,
        });
        break;
      
      case 'lifecycle_event':
        // Handle lifecycle events (task_start, task_complete, message_start, etc.)
        // For lifecycle_event, metadata fields are merged directly into params (see message_builder.py line 214-220)
        this.handleLifecycleEvent(params);
        break;
      
      case 'cache_status':
        // Handle cache status update — emit as typed event for useACP
        logger.info('📊 Cache status received', {
          component: 'Adapter',
          operation: 'handleACPSessionUpdate',
          contentLength: content.length,
        });

        try {
          const cacheData = JSON.parse(content);
          this.emit('cacheStatus', cacheData);
        } catch (e) {
          logger.warn('Failed to parse cache_status content', {
            component: 'Adapter',
            error: e,
          });
        }
        break;

      case 'banner_info':
        // Handle banner info - emit as message event for useACP to process
        logger.info('📋 Banner info received', {
          component: 'Adapter',
          operation: 'handleACPSessionUpdate',
          contentLength: content.length,
        });
        
        // Parse banner info to extract slash commands
        try {
          const bannerData = JSON.parse(content);
          if (bannerData.slash_commands && Array.isArray(bannerData.slash_commands)) {
            logger.info('📝 Received slash commands from backend', {
              component: 'Adapter',
              commandCount: bannerData.slash_commands.length,
            });
            
            // Emit slash commands update event
            this.emit('slashCommands:update', bannerData.slash_commands);
          }
          
          // Handle checkpoints list
          if (bannerData.checkpoints && Array.isArray(bannerData.checkpoints)) {
            logger.info('📦 Received checkpoints from backend', {
              component: 'Adapter',
              checkpointCount: bannerData.checkpoints.length,
            });
            
            // Emit checkpoints update event
            this.emit('checkpoints:update', bannerData.checkpoints);
          }
          
          // Handle session ID
          if (bannerData.session_id) {
            logger.info('🔑 Received session ID from backend', {
              component: 'Adapter',
              sessionId: bannerData.session_id,
            });
            
            // Emit session ID event
            this.emit('session:id', bannerData.session_id);
          }
          
          // Handle project hash
          if (bannerData.project_hash) {
            logger.info('🔑 Received project hash from backend', {
              component: 'Adapter',
              projectHash: bannerData.project_hash,
            });
            
            // Emit project hash event
            this.emit('project:hash', bannerData.project_hash);
          }
        } catch (e) {
          logger.warn('Failed to parse banner info', {
            component: 'Adapter',
            error: e,
          });
        }
        
        const bannerEvent: ACPEvent = {
          type: 'message',
          data: {
            content,
            blockType: 'system',
            metadata: {
              reason: 'banner_info',
              type: metadata.type || 'banner',
            },
          },
          timestamp: new Date().toISOString(),
        };
        
        this.emit('message', bannerEvent);

        // banner_info is the last thing Python sends before entering the input loop —
        // treat it as the definitive "backend ready" signal.
        if (!this.isReady && this.readyResolver) {
          logger.info('[Adapter] [waitForReady] siada-cli ready signal received (banner_info)', {
            component: 'Adapter',
            operation: 'waitForReady',
          });
          this.isReady = true;
          const resolver = this.readyResolver;
          this.readyResolver = null;
          resolver();
        }
        break;
      
      case 'session_title': {
        // Backend generated a short session title via the fast LLM
        // (see siada/services/session_title.py). Forward it so the
        // frontend can set the terminal tab/window title.
        this.emit('session:title', content);
        break;
      }

      case 'quota_update': {
        // Forward quota update as a message event for streaming layer to pick up
        const quotaEvent: ACPEvent = {
          type: 'message',
          data: {
            content,
            blockType: 'system',
            metadata: { reason: 'quota_update' },
          },
          timestamp: new Date().toISOString(),
        };
        this.emit('message', quotaEvent);
        break;
      }

      case 'input_ready':
        // Handle input_ready - stop all animations
        if (metadata.animation_control === 'stop') {
          logger.info('🛑 Animation control: STOP (input ready)', {
            component: 'Adapter',
            operation: 'handleACPSessionUpdate',
          });
          this.emit('animation:stop');
        }
        break;
      
      case 'interactive_input_request':
        // Handle interactive input request from backend (e.g., password prompts)
        // This is used when running commands that require user input
        logger.info('🔐 Interactive input request received', {
          component: 'Adapter',
          operation: 'handleACPSessionUpdate',
          prompt: content,
          inputType: metadata.inputType,
          isPassword: metadata.isPassword,
        });
        
        // Stop animations while waiting for user input
        this.emit('animation:stop');
        
        // Emit interactive input request event
        // The UI should display the prompt and wait for user input
        this.emit('interactive:input', {
          prompt: content,
          inputType: metadata.inputType || 'text',
          isPassword: metadata.isPassword || false,
        });
        break;
      
      case 'interactive_input_cancel':
        // Handle interactive input cancel from backend (e.g., command timeout while waiting for password)
        // This dismisses any active interactive input prompt on the frontend
        logger.info('🚫 Interactive input cancel received', {
          component: 'Adapter',
          operation: 'handleACPSessionUpdate',
          cancelReason: metadata.cancelReason,
        });
        
        // Emit interactive input cancel event
        // The UI should dismiss the input prompt and return to normal state
        this.emit('interactive:cancel', {
          reason: metadata.cancelReason || 'unknown',
        });
        break;
      
      case 'processing_started':
        // Handle processing_started - start all animations
        if (metadata.animation_control === 'start') {
          logger.info('▶️ Animation control: START (processing)', {
            component: 'Adapter',
            operation: 'handleACPSessionUpdate',
          });
          this.emit('animation:start');
        }
        break;

      case 'queue_item_consumed':
        // A queued prompt was consumed by the backend — tell the frontend to remove it.
        // The notification also carries the original prompt text (metadata.content)
        // so the events layer can render the user bubble even if the local preview
        // queue entry was already cleared, eliminating the turn-boundary race.
        logger.info('🗑️ Queue item consumed', {
          component: 'Adapter',
          operation: 'handleACPSessionUpdate',
          queueId: metadata.id,
        });
        this.emit('queue:itemConsumed', { id: metadata.id, content: metadata.content });
        break;
        
      default:
        logger.warn('Unknown session update reason', {
          component: 'Adapter',
          reason,
        });
    }
  }


  /**
   * Convert ACP message to siada-cli stdin input
   */
  private convertACPToSiada(message: ACPMessage): string {
    const startTime = Date.now();
    let input = '';
    switch (message.method) {
      case 'agent/execute': {
        const { prompt, image_paths, queue_id } = message.params as {
          prompt: string;
          image_paths?: string[];
          queue_id?: string;
        };
        // ALWAYS JSON-encode the payload. JSON.stringify escapes real newlines
        // into the literal "\n" sequence, so the prompt body can never contain
        // a standalone "<<<SIADA_MSG_END>>>" line that would prematurely close
        // the stdin frame (frame-injection). The backend already parses both the
        // JSON envelope and raw-text shapes, so this is fully backward compatible.
        input = JSON.stringify({
          prompt,
          ...(image_paths && image_paths.length > 0 ? { image_paths } : {}),
          ...(queue_id ? { queue_id } : {}),
        });
        break;

      }
      case 'agent/stop':
        input = '\x03'; // ETX (Ctrl+C equivalent)
        break;
      default:
        logger.warn('Unsupported ACP method', {
          component: 'Adapter',
          operation: 'convertACPToSiada',
          method: message.method,
          messageId: String(message.id),
        });
        if (message.params?.prompt) {
          input = message.params.prompt;
        }
        return '';
    }
    logger.logConversion('ACP', 'siada-cli', message, input, {
      method: message.method,
      messageId: String(message.id),
      inputLength: input.length,
      duration: Date.now() - startTime,
    });
    return input;
  }

  /**
   * Send message to siada-cli
   */
  async sendMessage(message: ACPMessage): Promise<void> {
    if (!this.process || !this.isReady) {
      const error = new Error('Adapter not ready');
      logger.error('Cannot send message: adapter not ready', error, {
        component: 'Adapter',
        operation: 'sendMessage',
        isReady: this.isReady,
        hasProcess: !!this.process,
      });
      throw error;
    }

    // Print the original message being sent from adapter
    // console.log('\n========== ADAPTER SENDING MESSAGE ==========');
    // console.log(JSON.stringify(message, null, 2));
    // console.log('=============================================\n');

    const startTime = Date.now();
    const command = this.convertACPToSiada(message);
    
    if (command) {
      logger.logACPMessage('send', message, {
        component: 'Adapter',
        operation: 'sendMessage',
        command,
      });
      
      logger.info('Writing to siada-cli stdin', {
        component: 'Adapter',
        operation: 'sendMessage',
        messageId: String(message.id),
        command,
        commandLength: command.length,
        hasStdin: !!this.process.stdin,
      });
      await this.writeInputToStdin(command, {
        messageId: String(message.id),
        operation: 'sendMessage',
        method: message.method,
      });

      // Explicitly end the stream to flush pending data
      // Note: This will close stdin after writing
      // For continuous interaction, we should NOT do this
      // this.process.stdin?.end();

      logger.debug('Message sent to siada-cli', {
        component: 'Adapter',
        operation: 'sendMessage',
        messageId: String(message.id),
        method: message.method,
        commandLength: command.length,
        duration: Date.now() - startTime,
      });
    } else {
      logger.warn('Empty command generated, message not sent', {
        component: 'Adapter',
        operation: 'sendMessage',
        messageId: String(message.id),
        method: message.method,
      });
    }
  }

  async sendRawInput(input: string, meta?: { operation?: string; method?: string; messageId?: string }): Promise<void> {
    // Allow sending as long as the process is running, even if isReady (waitForReady) has not
    // resolved yet. This is required for the login-choice window: Python sends
    // ui/showLoginSelector before banner_info, so isReady is still false when the
    // user picks a login option.
    if (!this.isProcessRunning()) {
      const error = new Error('Adapter not ready');
      logger.error('Cannot send raw input: adapter not ready', error, {
        component: 'Adapter',
        operation: meta?.operation ?? 'sendRawInput',
        isReady: this.isReady,
        hasProcess: !!this.process,
      });
      throw error;
    }

    await this.writeInputToStdin(input, {
      messageId: meta?.messageId,
      operation: meta?.operation ?? 'sendRawInput',
      method: meta?.method ?? 'raw-input',
    });
  }

  /**
   * Wait for siada-cli to be ready
   * Waits for ready signal from stdout or times out
   */
  private async waitForReady(timeout: number = 30000): Promise<void> {
    return new Promise((resolve, reject) => {
      logger.info('Waiting for siada-cli to be ready', {
        component: 'Adapter',
        operation: 'waitForReady',
        timeout,
      });

      const startTime = Date.now();

      // Hard timeout: if banner_info never arrives (crash / unexpected output),
      // proceed anyway so the UI doesn't hang forever.
      const timer = setTimeout(() => {
        logger.warn('Timeout waiting for siada-cli ready signal, proceeding anyway', {
          component: 'Adapter',
          operation: 'waitForReady',
          timeout,
        });
        this.readyResolver = null;
        resolve();
      }, timeout);

      // Primary signal: readyResolver is called by handleACPSessionUpdate when
      // banner_info arrives (the last thing Python sends before the input loop).
      this.readyResolver = () => {
        logger.info('siada-cli ready signal received', {
          component: 'Adapter',
          operation: 'waitForReady',
          elapsedTime: Date.now() - startTime,
        });
        clearTimeout(timer);
        resolve();
      };
    });
  }

  /**
   * Handle process crash and attempt restart
   */
  private async handleCrash(exitCode: number): Promise<void> {
    logger.error('siada-cli process crashed', undefined, {
      component: 'Adapter',
      operation: 'handleCrash',
      exitCode,
      restartAttempts: this.restartAttempts,
      maxAttempts: MAX_RESTART_ATTEMPTS,
    });
    
    if (this.restartAttempts < MAX_RESTART_ATTEMPTS) {
      this.restartAttempts++;
      
      logger.info(`Attempting to restart siada-cli`, {
        component: 'Adapter',
        operation: 'handleCrash',
        attempt: this.restartAttempts,
        maxAttempts: MAX_RESTART_ATTEMPTS,
        delayMs: RESTART_DELAY,
      });
      
      await new Promise(resolve => setTimeout(resolve, RESTART_DELAY));
      
      try {
        // Would need to store config for restart
        this.emit('restarting', this.restartAttempts);
        logger.info('Restart signal emitted', {
          component: 'Adapter',
          operation: 'handleCrash',
          attempt: this.restartAttempts,
        });
      } catch (error) {
        logger.error('Failed to restart siada-cli', error, {
          component: 'Adapter',
          operation: 'handleCrash',
          attempt: this.restartAttempts,
        });
      }
    } else {
      logger.error('Max restart attempts reached, giving up', undefined, {
        component: 'Adapter',
        operation: 'handleCrash',
        totalAttempts: this.restartAttempts,
        exitCode,
      });
      this.emit('fatal', new Error('Max restart attempts reached'));
    }
  }

  /**
   * Stop the adapter and cleanup
   */
  /**
   * Send interrupt signal (SIGINT) to siada-cli process
   * This allows siada-agenthub to handle the interrupt gracefully
   */
  async interrupt(): Promise<void> {
    logger.info('Sending interrupt signal to siada-cli', {
      component: 'Adapter',
      operation: 'interrupt',
      pid: this.process?.pid,
    });
    
    if (this.process && this.process.pid) {
      try {
        // Primary mechanism (all platforms): write ETX byte + newline to stdin.
        // The Python StdinInterruptMonitor reads stdin byte-by-byte and
        // converts \x03 into a KeyboardInterrupt in the main thread.
        // The trailing \n ensures the byte is flushed through any pipe buffer.
        if (this.process.stdin && !this.process.stdin.destroyed) {
          this.process.stdin.write('\x03\n');
          logger.debug('Wrote ETX (\\x03\\n) to child stdin', {
            component: 'Adapter',
            operation: 'interrupt',
            pid: this.process.pid,
          });
        } else {
          logger.warn('Cannot write ETX to stdin (stdin unavailable or destroyed)', {
            component: 'Adapter',
            operation: 'interrupt',
            pid: this.process.pid,
          });
        }

        // On Unix/macOS, also send SIGINT as a fallback in case the monitor
        // is not active.  On Windows, kill('SIGINT') unconditionally
        // terminates the process (like SIGKILL), so we must NOT call it.
        if (process.platform !== 'win32') {
          this.process.kill('SIGINT');
          logger.debug('SIGINT sent as fallback (non-Windows)', {
            component: 'Adapter',
            operation: 'interrupt',
            pid: this.process.pid,
          });
        }
      } catch (error) {
        logger.error('Failed to send interrupt', error, {
          component: 'Adapter',
          operation: 'interrupt',
          pid: this.process.pid,
        });
      }
    } else {
      logger.warn('No process to interrupt', {
        component: 'Adapter',
        operation: 'interrupt',
      });
    }
  }

  async stop(): Promise<void> {
    const startTime = Date.now();
    
    logger.info('Stopping siada-cli adapter', {
      component: 'Adapter',
      operation: 'stop',
      pid: this.process?.pid,
      isReady: this.isReady,
    });
    
    if (this.process) {
      const pid = this.process.pid;
      
      logger.debug('Sending SIGTERM to siada-cli process', {
        component: 'Adapter',
        operation: 'stop',
        pid,
      });
      
      this.process.kill('SIGTERM');
      
      // Wait for graceful shutdown
      await new Promise<void>((resolve) => {
        const timeout = setTimeout(() => {
          logger.warn('Graceful shutdown timeout, forcing termination', {
            component: 'Adapter',
            operation: 'stop',
            pid,
            timeoutMs: 5000,
          });
          
          if (this.process) {
            this.process.kill('SIGKILL');
          }
          resolve();
        }, 5000);

        this.process?.once('exit', () => {
          clearTimeout(timeout);
          logger.debug('Process exited gracefully', {
            component: 'Adapter',
            operation: 'stop',
            pid,
          });
          resolve();
        });
      });

      this.process = null;
      this.isReady = false;
      
      logger.logStateChange('Adapter', 'running', 'stopped', {
        pid,
        duration: Date.now() - startTime,
      });
    } else {
      logger.debug('No process to stop', {
        component: 'Adapter',
        operation: 'stop',
      });
    }
  }

  /**
   * Send a JSON-RPC notification to the backend (no id, no response expected).
   * Used for lightweight frontend→backend signals like session/pullHistory.
   */
  sendNotification(method: string, params?: Record<string, unknown>): void {
    if (!this.process || !this.process.stdin) {
      logger.warn('Cannot send notification: process or stdin not available', {
        component: 'Adapter',
        operation: 'sendNotification',
        method,
      });
      return;
    }

    const notification = JSON.stringify({
      jsonrpc: '2.0',
      method,
      params: params || {},
    });

    const writeData = `<<<SIADA_MSG_START>>>\n${notification}\n<<<SIADA_MSG_END>>>\n`;

    logger.info('Sending JSON-RPC notification to backend', {
      component: 'Adapter',
      operation: 'sendNotification',
      method,
      params,
    });

    this.process.stdin.write(writeData);
  }

  /**
   * Check if connected
   */
  isAdapterReady(): boolean {
    return this.isReady && !!this.process && this.process.exitCode === null;
  }

  /**
   * Check if the child process is running (even before it is fully "ready").
   * Used by sendLoginChoice to allow sending during the startup login window.
   */
  isProcessRunning(): boolean {
    return !!this.process && !this.process.killed && this.process.exitCode === null;
  }

  // ============================================================================
  // Lifecycle Event Handlers
  // ============================================================================
  
  /**
   * Handle lifecycle events from backend
   */
  private handleLifecycleEvent(params: any): void {
    // In message_builder.py line 214-220, for lifecycle_event reason,
    // metadata fields are merged directly into params (not wrapped in _meta)
    // So we extract eventType directly from params.type
    const eventType = params.type;
    
    logger.info('🔄 Lifecycle event received', {
      component: 'Adapter',
      operation: 'handleLifecycleEvent',
      eventType,
      params,
    });
    
    switch (eventType) {
      case 'task_start':
        this.handleTaskStart(params);
        break;
      case 'task_complete':
        this.handleTaskComplete(params);
        break;
      case 'task_error':
        this.handleTaskError(params);
        break;
      case 'message_start':
        this.handleMessageStart(params);
        break;
      case 'message_end':
        this.handleMessageEnd(params);
        break;
      case 'content_delta':
        this.handleContentDelta(params);
        break;
      case 'tool_use':
        // Handle tool_use lifecycle event (tool call delta)
        this.handleToolUseDelta(params);
        break;
      case 'tool_call_stage_advance':
        // Handle stage advancement (optional, for future use)
        logger.debug('Tool call stage advanced', { component: 'Adapter', params });
        break;
      case 'tool_result':
        // Handle tool result - emit as process message
        this.handleToolResult(params);
        break;
      case 'error':
        // Handle error - emit as process message
        this.handleError(params);
        break;
      case 'warning':
        // Handle warning - emit as process message
        this.handleWarning(params);
        break;
      case 'tool_call':
        // Handle tool_call - emit as process message
        this.handleToolCall(params);
        break;
      case 'info':
        // Handle info - emit as process message
        this.handleInfo(params);
        break;
      case 'token_usage':
        // Handle token usage - emit event for UI to display
        this.handleTokenUsage(params);
        break;
      case 'banner_info':
        // Handle banner_info lifecycle event - emit for UI to process
        this.handleBannerInfo(params);
        break;
      case 'processing_started':
        // Handle processing_started - start all animations
        if (params.animation_control === 'start') {
          logger.info('▶️ Animation control: START (processing) via lifecycle', {
            component: 'Adapter',
            operation: 'handleLifecycleEvent',
          });
          this.emit('animation:start');
        }
        break;
      case 'input_ready':
        // Handle input_ready - stop all animations
        if (params.animation_control === 'stop') {
          logger.info('🛑 Animation control: STOP (input ready) via lifecycle', {
            component: 'Adapter',
            operation: 'handleLifecycleEvent',
          });
          this.emit('animation:stop');
        }
        break;
      case 'thinking':
        // Handle thinking message from backend
        this.handleThinkingMessage(params);
        break;
      case 'answer':
        // Handle answer message from backend
        this.handleAnswerMessage(params);
        break;
      case 'tool_output':
        // Handle tool output message from backend
        this.handleToolOutputMessage(params);
        break;
      case 'completed':
        // Handle completion notification from backend
        this.handleCompletedMessage(params);
        break;
      case 'failed':
        // Handle failure notification from backend
        this.handleFailedMessage(params);
        break;
      case 'cancelled':
        // Handle cancellation notification from backend
        this.handleCancelledMessage(params);
        break;
      default:
        logger.warn('Unknown lifecycle event type', {
          component: 'Adapter',
          eventType,
        });
    }
  }
  
  /**
   * Handle task_start event (Slash commands)
   */
  private handleTaskStart(data: any): void {
    const { command, task_id, args, category } = data;
    
    if (category === 'slash_command') {
      logger.info('🚀 Task started', {
        component: 'Adapter',
        command,
        taskId: task_id,
        args,
      });
      
      // Start new slash command buffer
      this.slashCommandBuffer = {
        command,
        taskId: task_id,
        content: [],
        startTime: Date.now(),
        isActive: true,
      };
      
      // Emit task start event for UI
      this.emit('task:start', {
        command,
        taskId: task_id,
        args,
      });
    }
  }
  
  /**
   * Handle task_complete event (Slash commands)
   */
  private handleTaskComplete(data: any): void {
    const { command, result } = data;
    
    if (this.slashCommandBuffer && this.slashCommandBuffer.isActive) {
      logger.info('✅ Task completed', {
        component: 'Adapter',
        command,
        taskId: this.slashCommandBuffer.taskId,
        duration: Date.now() - this.slashCommandBuffer.startTime,
      });
      
      // Add result to content if available
      if (result) {
        this.slashCommandBuffer.content.push(result);
      }
      
      // Send complete message block only if there's content to display
      const completeContent = this.slashCommandBuffer.content.join('\n').trim();
      if (completeContent) {
        const completeMessage: ACPEvent = {
          type: 'message',
          data: {
            content: completeContent,
            blockType: 'agent',
            subtype: 'slash_command_result' as any,
            isStreaming: false,
            streamEnd: true,
            metadata: {
              command: this.slashCommandBuffer.command,
              taskId: this.slashCommandBuffer.taskId,
              duration: Date.now() - this.slashCommandBuffer.startTime,
            },
          },
          timestamp: new Date().toISOString(),
        };

        this.emit('message', completeMessage);
      }
      
      // Emit task complete event for UI (to stop loading animation)
      this.emit('task:complete', {
        command,
        taskId: this.slashCommandBuffer.taskId,
      });
      
      // Clear buffer
      this.slashCommandBuffer = null;
    }
  }
  
  /**
   * Handle task_error event (Slash commands)
   */
  private handleTaskError(data: any): void {
    const { command, error, error_type } = data;
    
    if (this.slashCommandBuffer && this.slashCommandBuffer.isActive) {
      logger.error('❌ Task error', new Error(error), {
        component: 'Adapter',
        command,
        taskId: this.slashCommandBuffer.taskId,
        errorType: error_type,
      });
      
      // Send error message block
      const errorMessage: ACPEvent = {
        type: 'error',
        data: {
          content: error,
          blockType: 'agent',
          subtype: 'slash_command_error' as any,
          metadata: {
            command: this.slashCommandBuffer.command,
            taskId: this.slashCommandBuffer.taskId,
            errorType: error_type,
          },
        },
        timestamp: new Date().toISOString(),
      };
      
      this.emit('message', errorMessage);
      
      // Emit task error event for UI (to stop loading animation)
      this.emit('task:error', {
        command,
        taskId: this.slashCommandBuffer.taskId,
        error,
      });
      
      // Clear buffer
      this.slashCommandBuffer = null;
    }
  }
  
  /**
   * Handle message_start event (Conversations)
   */
  private handleMessageStart(data: any): void {
    const { message_type, message_id } = data;
    
    logger.info('📨 Message started', {
      component: 'Adapter',
      messageType: message_type,
      messageId: message_id,
    });
    
    // Start new streaming buffer
    this.streamingBuffer = {
      messageId: message_id,
      messageType: message_type,
      content: [],
      isActive: true,
    };
    
    // Emit stream start event for UI
    this.emit('stream:start', {
      messageId: message_id,
      messageType: message_type,
    });
  }
  
  /**
   * Handle content_delta event (Conversations)
   */
  private handleContentDelta(data: any): void {
    const { delta, is_final, stream_end, stream_start_id } = data;
    
    // 🔍 Debug: Log all conditions for handleContentDelta
    logger.info('🔍 [DEBUG] handleContentDelta called', {
      component: 'Adapter',
      operation: 'handleContentDelta',
      hasStreamingBuffer: !!this.streamingBuffer,
      isActive: this.streamingBuffer?.isActive,
      hasDelta: !!delta,
      deltaLength: delta?.length,
      streamingBufferState: this.streamingBuffer ? {
        messageId: this.streamingBuffer.messageId,
        messageType: this.streamingBuffer.messageType,
        contentLength: this.streamingBuffer.content.length,
        isActive: this.streamingBuffer.isActive,
      } : null,
      eventData: {
        delta: delta?.substring(0, 100),
        is_final,
        stream_end,
        stream_start_id,
      },
    });
    
    if (this.streamingBuffer && this.streamingBuffer.isActive && delta) {
      logger.debug('📝 Content delta', {
        component: 'Adapter',
        messageId: this.streamingBuffer.messageId,
        deltaLength: delta.length,
        isFinal: is_final,
        streamEnd: stream_end,
        streamStartId: stream_start_id,
      });
      
      // Add delta to buffer
      this.streamingBuffer.content.push(delta);
      
      // Send streaming update
      const streamEvent: ACPEvent = {
        type: 'message',
        data: {
          content: delta,
          blockType: 'agent',
          subtype: this.streamingBuffer.messageType as any,
          isStreaming: !is_final,
          streamEnd: stream_end || false,
          metadata: {
            messageId: this.streamingBuffer.messageId,
            messageType: this.streamingBuffer.messageType,
            streamStartId: stream_start_id,
          },
        },
        timestamp: new Date().toISOString(),
      };
      
      this.emit('message', streamEvent);
    } else {
      // 🔍 Debug: Log why handleContentDelta was skipped
      logger.warn('⚠️ [DEBUG] handleContentDelta skipped', {
        component: 'Adapter',
        operation: 'handleContentDelta',
        reason: !this.streamingBuffer ? 'no streamingBuffer' :
                !this.streamingBuffer.isActive ? 'streamingBuffer not active' :
                !delta ? 'no delta' : 'unknown',
      });
    }
  }
  
  /**
   * Handle message_end event (Conversations)
   */
  private handleMessageEnd(data: any): void {
    const { message_type, message_id } = data;
    
    if (this.streamingBuffer && 
        this.streamingBuffer.messageId === message_id) {
      
      logger.info('✓ Message ended', {
        component: 'Adapter',
        messageType: message_type,
        messageId: message_id,
        totalLength: this.streamingBuffer.content.join('').length,
      });
      
      // Emit stream end event for UI
      this.emit('stream:end', {
        messageId: message_id,
        messageType: message_type,
        totalContent: this.streamingBuffer.content.join(''),
      });
      
      // Clear buffer
      this.streamingBuffer = null;
    }
  }
  
  /**
   * Handle tool_use lifecycle event (tool call delta)
   * Accumulates tool call content and emits as streaming message
   */
  private handleToolUseDelta(data: any): void {
    const { delta, chunk_index, is_final, timestamp } = data;
    
    logger.debug('🔧 Tool use delta', {
      component: 'Adapter',
      operation: 'handleToolUseDelta',
      deltaLength: delta?.length || 0,
      chunkIndex: chunk_index,
      isFinal: is_final,
    });
    
    if (!delta) {
      return;
    }
    
    // Initialize tool use buffer if not exists
    if (!this.toolUseBuffer) {
      this.toolUseBuffer = {
        content: [],
        chunkCount: 0,
      };
    }
    
    // Add delta to buffer
    this.toolUseBuffer.content.push(delta);
    this.toolUseBuffer.chunkCount++;
    
    // Send streaming update as tool_use message
    const streamEvent: ACPEvent = {
      type: 'message',
      data: {
        content: delta,
        blockType: 'agent',
        subtype: 'tool_use',
        isStreaming: !is_final,
        streamEnd: is_final || false,
        metadata: {
          chunkIndex: chunk_index,
          timestamp,
        },
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', streamEvent);
    
    // Clear buffer on final
    if (is_final) {
      logger.info('✓ Tool use completed', {
        component: 'Adapter',
        totalChunks: this.toolUseBuffer.chunkCount,
        totalLength: this.toolUseBuffer.content.join('').length,
      });
      this.toolUseBuffer = null;
    }
  }
  
  /**
   * Handle tool_result lifecycle event
   * Emits as process message similar to tool_use
   */
  private handleToolResult(data: any): void {
    const { content, timestamp } = data;
    
    logger.debug('🔧 Tool result received', {
      component: 'Adapter',
      operation: 'handleToolResult',
      contentLength: content?.length || 0,
    });
    
    if (!content) {
      return;
    }
    
    // Emit as process message
    const resultEvent: ACPEvent = {
      type: 'message',
      data: {
        content,
        blockType: 'agent',
        subtype: 'tool_use',  // Same rendering as tool_use
        isStreaming: false,
        streamEnd: true,
        metadata: {
          timestamp,
          eventType: 'tool_result',
        },
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', resultEvent);
  }
  
  /**
   * Handle error lifecycle event
   * Emits as process message similar to tool_use
   */
  private handleError(data: any): void {
    const { content, timestamp } = data;
    
    logger.debug('❌ Error received', {
      component: 'Adapter',
      operation: 'handleError',
      contentLength: content?.length || 0,
    });
    
    if (!content) {
      return;
    }
    
    // Truncate error content to prevent terminal overflow
    // Calculate dynamic max lines based on terminal height (same logic as Message.tsx and ShellOutput.tsx)
    const terminalHeight = (typeof globalThis.process !== 'undefined' && globalThis.process.stdout?.rows) || 24;
    const dynamicMaxLines = Math.max(terminalHeight / 2, 5);
    
    // Split into lines and truncate if needed
    const errorLines = content.split('\n');
    let truncatedContent = content;
    let hiddenLinesCount = 0;
    
    if (errorLines.length > dynamicMaxLines) {
      // Keep first 4 lines + last (dynamicMaxLines - 4) lines
      const firstLines = 4;
      const lastLines = Math.max(dynamicMaxLines - firstLines, 0);
      const firstPart = errorLines.slice(0, firstLines);
      const lastPart = lastLines > 0 ? errorLines.slice(-lastLines) : [];
      hiddenLinesCount = errorLines.length - dynamicMaxLines;
      
      const truncatedLines = [...firstPart, `... ${hiddenLinesCount} lines hidden ...`, ...lastPart];
      truncatedContent = truncatedLines.join('\n');
      
      logger.info('❌ Error content truncated', {
        component: 'Adapter',
        operation: 'handleError',
        originalLines: errorLines.length,
        truncatedLines: truncatedLines.length,
        hiddenLines: hiddenLinesCount,
      });
    }
    
    // Emit as process message
    const errorEvent: ACPEvent = {
      type: 'message',
      data: {
        content: truncatedContent,
        blockType: 'agent',
        subtype: 'tool_use',  // Same rendering as tool_use
        isStreaming: false,
        streamEnd: true,
        metadata: {
          timestamp,
          eventType: 'error',
        },
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', errorEvent);
  }
  
  /**
   * Handle warning lifecycle event
   * Emits as process message similar to tool_use
   */
  private handleWarning(data: any): void {
    const { content, timestamp } = data;
    
    logger.debug('⚠️ Warning received', {
      component: 'Adapter',
      operation: 'handleWarning',
      contentLength: content?.length || 0,
    });
    
    if (!content) {
      return;
    }
    
    // Emit as process message
    const warningEvent: ACPEvent = {
      type: 'message',
      data: {
        content,
        blockType: 'agent',
        subtype: 'tool_use',  // Same rendering as tool_use
        isStreaming: false,
        streamEnd: true,
        metadata: {
          timestamp,
          eventType: 'warning',
        },
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', warningEvent);
  }
  
  /**
   * Handle tool_call lifecycle event
   * Emits as process message similar to tool_use
   */
  private handleToolCall(data: any): void {
    const { content, timestamp } = data;
    
    logger.debug('🔧 Tool call received', {
      component: 'Adapter',
      operation: 'handleToolCall',
      contentLength: content?.length || 0,
    });
    
    if (!content) {
      return;
    }
    
    // Emit as process message
    const toolCallEvent: ACPEvent = {
      type: 'message',
      data: {
        content,
        blockType: 'agent',
        subtype: 'tool_use',  // Same rendering as tool_use
        isStreaming: false,
        streamEnd: true,
        metadata: {
          timestamp,
          eventType: 'tool_call',
        },
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', toolCallEvent);
  }
  
  /**
   * Handle info lifecycle event
   * Emits as process message similar to tool_use
   */
  private handleInfo(data: any): void {
    const { content, timestamp, bold } = data;
    
    logger.debug('ℹ️ Info received', {
      component: 'Adapter',
      operation: 'handleInfo',
      contentLength: content?.length || 0,
      bold,
    });
    
    if (!content) {
      return;
    }
    
    // Emit as process message
    const infoEvent: ACPEvent = {
      type: 'message',
      data: {
        content,
        blockType: 'agent',
        subtype: 'tool_use',  // Same rendering as tool_use
        isStreaming: false,
        streamEnd: true,
        metadata: {
          timestamp,
          eventType: 'info',
          bold,
        },
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', infoEvent);
  }
  
  /**
   * Handle token_usage event
   */
  private handleTokenUsage(data: any): void {
    const { context_size, context_max, message, timestamp } = data;
    
    logger.debug('📊 Token usage received', {
      component: 'Adapter',
      operation: 'handleTokenUsage',
      contextSize: context_size,
      contextMax: context_max,
      message,
    });
    
    // Emit token usage event for UI components to consume
    this.emit('tokenUsage', {
      contextSize: context_size,
      contextMax: context_max,
      message,
      timestamp,
    });
  }
  
  /**
   * Handle banner_info lifecycle event
   * Processes banner info from backend and emits relevant events
   */
  private handleBannerInfo(data: any): void {
    const { banner } = data;
    
    logger.info('📋 Banner info received via lifecycle event', {
      component: 'Adapter',
      operation: 'handleBannerInfo',
      hasVersion: !!banner?.version,
      hasSlashCommands: !!banner?.slash_commands,
      hasCheckpoints: !!banner?.checkpoints,
    });
    
    if (!banner) {
      logger.warn('Banner info missing banner data', {
        component: 'Adapter',
        operation: 'handleBannerInfo',
        data,
      });
      return;
    }
    
    // Handle slash commands
    if (banner.slash_commands && Array.isArray(banner.slash_commands)) {
      logger.info('📝 Received slash commands from backend', {
        component: 'Adapter',
        commandCount: banner.slash_commands.length,
      });
      this.emit('slashCommands:update', banner.slash_commands);
    }
    
    // Handle checkpoints
    if (banner.checkpoints && Array.isArray(banner.checkpoints)) {
      logger.info('📦 Received checkpoints from backend', {
        component: 'Adapter',
        checkpointCount: banner.checkpoints.length,
      });
      this.emit('checkpoints:update', banner.checkpoints);
    }
    
    // Handle session ID
    if (banner.session_id) {
      logger.info('🔑 Received session ID from backend', {
        component: 'Adapter',
        sessionId: banner.session_id,
      });
      this.emit('session:id', banner.session_id);
    }
    
    // Handle project hash
    if (banner.project_hash) {
      logger.info('🔑 Received project hash from backend', {
        component: 'Adapter',
        projectHash: banner.project_hash,
      });
      this.emit('project:hash', banner.project_hash);
    }
    
    // Emit banner info as message event for useACP to process
    const bannerEvent: ACPEvent = {
      type: 'message',
      data: {
        content: JSON.stringify(banner),
        blockType: 'system',
        metadata: {
          reason: 'banner_info',
          type: 'banner',
          version: banner.version,
        },
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', bannerEvent);
  }
  
  /**
   * Handle thinking message from backend (via lifecycle event)
   */
  private handleThinkingMessage(data: any): void {
    const { content, chunk_type, is_streaming } = data;
    
    logger.debug('💭 Thinking message received', {
      component: 'Adapter',
      operation: 'handleThinkingMessage',
      contentLength: content?.length,
    });
    
    const thinkingEvent: ACPEvent = {
      type: 'message',
      data: {
        content: content || '',
        blockType: 'agent',
        subtype: 'thinking',
        isStreaming: is_streaming !== false,
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', thinkingEvent);
  }
  
  /**
   * Handle answer message from backend (via lifecycle event)
   */
  private handleAnswerMessage(data: any): void {
    const { content, chunk_type, is_streaming, stream_end, stream_start_id } = data;
    
    logger.debug('💬 Answer message received', {
      component: 'Adapter',
      operation: 'handleAnswerMessage',
      contentLength: content?.length,
      streamEnd: stream_end,
    });
    
    const answerEvent: ACPEvent = {
      type: 'message',
      data: {
        content: content || '',
        blockType: 'agent',
        subtype: 'answer',
        isStreaming: is_streaming !== false,
        streamEnd: stream_end || false,
        streamStartId: stream_start_id,
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', answerEvent);
  }
  
  /**
   * Handle tool output message from backend (via lifecycle event)
   */
  private handleToolOutputMessage(data: any): void {
    const { content, chunk_type } = data;
    
    logger.debug('🔧 Tool output message received', {
      component: 'Adapter',
      operation: 'handleToolOutputMessage',
      contentLength: content?.length,
    });
    
    const toolOutputEvent: ACPEvent = {
      type: 'message',
      data: {
        content: content || '',
        blockType: 'agent',
        subtype: 'tool_use',
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', toolOutputEvent);
  }
  
  /**
   * Handle completion notification from backend (via lifecycle event)
   */
  private handleCompletedMessage(data: any): void {
    const { content } = data;
    
    logger.info('✅ Completed message received', {
      component: 'Adapter',
      operation: 'handleCompletedMessage',
      content,
    });
    
    // Emit completion event
    this.emit('completed', { content });
  }
  
  /**
   * Handle failure notification from backend (via lifecycle event)
   */
  private handleFailedMessage(data: any): void {
    const { content, metadata } = data;
    
    // Check if this is a startup error (fatal error during initialization)
    const isStartupError = metadata?.type === 'startup_error';
    const isFatal = metadata?.fatal === true;
    
    logger.error('❌ Failed message received', new Error(content), {
      component: 'Adapter',
      operation: 'handleFailedMessage',
      isStartupError,
      isFatal,
    });
    
    const errorEvent: ACPEvent = {
      type: 'error',
      data: {
        content: content || 'Unknown error',
        blockType: 'agent',
        metadata: {
          type: isStartupError ? 'startup_error' : 'error',
          fatal: isFatal,
        },
      },
      timestamp: new Date().toISOString(),
    };
    
    this.emit('message', errorEvent);
    
    // If this is a fatal startup error, also emit a special event
    if (isStartupError && isFatal) {
      logger.error('🚨 Fatal startup error - backend initialization failed', new Error(content), {
        component: 'Adapter',
        operation: 'handleFailedMessage',
      });
      this.emit('startup:error', { content, fatal: true });
    }
  }
  
  /**
   * Handle cancellation notification from backend (via lifecycle event)
   */
  private handleCancelledMessage(data: any): void {
    const { content } = data;
    
    logger.info('🚫 Cancelled message received', {
      component: 'Adapter',
      operation: 'handleCancelledMessage',
      reason: content,
    });
    
    // Emit cancellation event
    this.emit('cancelled', { reason: content });
  }
}
