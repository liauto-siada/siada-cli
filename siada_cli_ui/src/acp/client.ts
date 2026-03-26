/**
 * ACP Client wrapper
 * High-level interface for interacting with siada-cli via ACP
 */

import { EventEmitter } from 'events';
import { SiadaACPAdapter } from './adapter.js';
import { ClientConfig, ACPMessage, ACPEvent, Message } from '../types/index.js';
import { logger, LogLevel } from '../utils/logger.js';

export class SiadaACPClient extends EventEmitter {
  public adapter: SiadaACPAdapter; // Changed to public for exit event listening
  private connected: boolean = false;
  private messageIdCounter: number = 0;

  private redactSensitiveContent(content: string): string {
    if (!content) return content;

    if (content.startsWith('__LOGIN_CHOICE__:3:')) {
      return '__LOGIN_CHOICE__:3:[REDACTED_LOGIN_PAYLOAD]';
    }

    return content
      .replace(/("api_key"\s*:\s*")([^"]+)(")/gi, '$1***FILTERED***$3')
      .replace(/("token"\s*:\s*")([^"]+)(")/gi, '$1***FILTERED***$3')
      .replace(/("authorization"\s*:\s*")([^"]+)(")/gi, '$1***FILTERED***$3');
  }

  constructor(private config: ClientConfig) {
    super();
    this.adapter = new SiadaACPAdapter();
    this.setupAdapterHandlers();
  }

  /**
   * Setup adapter event handlers
   */
  private setupAdapterHandlers(): void {
    this.adapter.on('ready', () => {
      logger.info('Adapter ready', {
        component: 'Client',
        operation: 'adapter_ready',
      });
      this.emit('ready');
    });

    this.adapter.on('message', (acpEvent: ACPEvent) => {
      logger.logACPMessage('receive', acpEvent, {
        component: 'Client',
        operation: 'adapter_message',
        eventType: acpEvent.type,
      });
      this.handleACPEvent(acpEvent);
    });

    this.adapter.on('error', (error: Error) => {
      logger.error('Adapter error', error, {
        component: 'Client',
        operation: 'adapter_error',
      });
      this.emit('error', error);
    });

    this.adapter.on('exit', (code: number | null) => {
      logger.logStateChange('Client', 'connected', 'disconnected', {
        exitCode: code,
      });
      this.connected = false;
      this.emit('disconnected', code);
    });

    this.adapter.on('stderr', (message: string) => {
      logger.debug('Adapter stderr', {
        component: 'Client',
        operation: 'adapter_stderr',
        message: message.substring(0, 200),
      });
      this.emit('stderr', message);
    });

    // Animation control events
    this.adapter.on('animation:stop', () => {
      logger.info('Animation control: STOP', {
        component: 'Client',
        operation: 'animation_control',
      });
      this.emit('animation:stop');
    });

    this.adapter.on('animation:start', () => {
      logger.info('Animation control: START', {
        component: 'Client',
        operation: 'animation_control',
      });
      this.emit('animation:start');
    });

    // Slash commands update event
    this.adapter.on('slashCommands:update', (commands: Array<{name: string, description: string}>) => {
      logger.info('Slash commands update received', {
        component: 'Client',
        operation: 'slashCommands_update',
        commandCount: commands.length,
      });
      this.emit('slashCommands:update', commands);
    });

    // Checkpoints update event
    this.adapter.on('checkpoints:update', (checkpoints: Array<{file_name: string, timestamp: string, tool: string, modified_files: string}>) => {
      logger.info('Checkpoints update received', {
        component: 'Client',
        operation: 'checkpoints_update',
        checkpointCount: checkpoints.length,
      });
      this.emit('checkpoints:update', checkpoints);
    });

    // Session ID event
    this.adapter.on('session:id', (sessionId: string) => {
      logger.info('Session ID received', {
        component: 'Client',
        operation: 'session_id',
        sessionId,
      });
      this.emit('session:id', sessionId);
    });

    // Project hash event
    this.adapter.on('project:hash', (projectHash: string) => {
      logger.info('Project hash received', {
        component: 'Client',
        operation: 'project_hash',
        projectHash,
      });
      this.emit('project:hash', projectHash);
    });

    // Token usage event
    this.adapter.on('tokenUsage', (data: any) => {
      logger.info('Token usage received', {
        component: 'Client',
        operation: 'token_usage',
        contextSize: data.contextSize,
        contextMax: data.contextMax,
      });
      this.emit('tokenUsage', data);
    });

    // Interactive input request event (for commands that need user input like passwords)
    this.adapter.on('interactive:input', (data: { prompt: string; inputType: string; isPassword: boolean }) => {
      logger.info('Interactive input request received', {
        component: 'Client',
        operation: 'interactive_input',
        prompt: data.prompt.substring(0, 100),
        inputType: data.inputType,
        isPassword: data.isPassword,
      });
      this.emit('interactive:input', data);
    });

    // Interactive input cancel event (e.g., command timeout while waiting for password)
    this.adapter.on('interactive:cancel', (data: { reason: string }) => {
      logger.info('Interactive input cancel received', {
        component: 'Client',
        operation: 'interactive_cancel',
        reason: data.reason,
      });
      this.emit('interactive:cancel', data);
    });
  }

  /**
   * Handle ACP events from adapter
   */
  private handleACPEvent(event: ACPEvent): void {
    logger.debug('Handling ACP event', {
      component: 'Client',
      operation: 'handleACPEvent',
      eventType: event.type,
      timestamp: event.timestamp,
    });

    switch (event.type) {
      case 'message':
        const message = {
          id: this.generateMessageId(),
          type: 'agent',
          content: event.data.content,
          timestamp: event.timestamp,
          author: 'Siada',
          metadata: {
            blockType: event.data.blockType,
            subtype: event.data.subtype || event.data.metadata?.subtype, // Read subtype from both locations for compatibility
            isStreaming: event.data.isStreaming, // Include isStreaming flag
            streamEnd: event.data.streamEnd,
            streamStartId: event.data.metadata?.streamStartId, // Read from correct path
            chunkIndex: event.data.metadata?.chunkIndex,
            // Add banner_info fields
            reason: event.data.metadata?.reason,
            type: event.data.metadata?.type,
          },
        } as Message;
        
        logger.debug('Processing message event', {
          component: 'Client',
          operation: 'handleACPEvent',
          messageId: message.id,
          contentLength: event.data.content?.length || 0,
          subtype: event.data.subtype,
          isStreaming: event.data.isStreaming,
          streamEnd: event.data.streamEnd,
          streamStartId: event.data.metadata?.streamStartId,
        });
        
        // Emit different events based on subtype
        const subtype = event.data.subtype;
        if (subtype === 'tool_use') {
          // Tool use messages - emit as agentMessage for ProcessBox rendering
          logger.debug('Emitting tool_use message as agentMessage', {
            component: 'Client',
            messageId: message.id,
          });
          this.emit('toolUse', message);
        } else if (subtype === 'thinking') {
          // Thinking messages
          logger.debug('Emitting thinking message as agentMessage', {
            component: 'Client',
            messageId: message.id,
          });
          this.emit('agentMessage', message);
        } else if (subtype === 'answer') {
          // Answer messages
          logger.debug('Emitting answer message as agentMessage', {
            component: 'Client',
            messageId: message.id,
          });
          this.emit('agentMessage', message);
        } else {
          // Default: emit as agentMessage for backward compatibility
          logger.debug('Emitting message as agentMessage (default)', {
            component: 'Client',
            messageId: message.id,
            subtype: subtype || 'none',
          });
          this.emit('agentMessage', message);
        }
        break;

      case 'toolUse':
        logger.debug('Emitting tool use event', {
          component: 'Client',
          operation: 'handleACPEvent',
          toolName: event.data.name || 'unknown',
        });
        this.emit('toolUse', event.data);
        break;

      case 'fileEdit':
        logger.debug('Emitting file edit event', {
          component: 'Client',
          operation: 'handleACPEvent',
          filePath: event.data.path || 'unknown',
          action: event.data.action || 'unknown',
        });
        this.emit('fileEdit', event.data);
        break;

      case 'thinking':
        logger.debug('Emitting thinking event', {
          component: 'Client',
          operation: 'handleACPEvent',
          contentLength: event.data.content?.length || 0,
        });
        this.emit('thinking', event.data);
        break;

      case 'error':
        // Handle error events (including startup errors)
        const errorMessage = {
          id: this.generateMessageId(),
          type: 'error',
          content: event.data.content,
          timestamp: event.timestamp,
          author: 'System',
          metadata: {
            type: event.data.metadata?.type,
            fatal: event.data.metadata?.fatal,
          },
        } as Message;
        
        logger.error('Error event received', new Error(event.data.content), {
          component: 'Client',
          operation: 'handleACPEvent',
          isStartupError: event.data.metadata?.type === 'startup_error',
          isFatal: event.data.metadata?.fatal,
        });
        
        this.emit('agentMessage', errorMessage);
        break;

      default:
        logger.warn('Unknown ACP event type', {
          component: 'Client',
          operation: 'handleACPEvent',
          eventType: event.type,
        });
    }
  }

  /**
   * Connect to siada-cli
   */
  async connect(): Promise<void> {
    const startTime = Date.now();
    
    logger.info('Connecting to siada-cli', {
      component: 'Client',
      operation: 'connect',
      config: {
        workingDir: this.config.workingDir,
        model: this.config.model,
      },
    });

    try {
      await this.adapter.start(this.config);
      this.connected = true;
      this.emit('connected');
      
      logger.logWithTiming(
        LogLevel.INFO,
        'Successfully connected to siada-cli',
        startTime,
        {
          component: 'Client',
          operation: 'connect',
        }
      );
    } catch (error) {
      logger.error('Failed to connect to siada-cli', error, {
        component: 'Client',
        operation: 'connect',
        duration: Date.now() - startTime,
      });
      throw error;
    }
  }

  /**
   * Send a message to siada-cli
   */
  async sendMessage(content: string): Promise<void> {
    if (!this.connected) {
      const error = new Error('Not connected to siada-cli');
      logger.error('Cannot send message: not connected', error, {
        component: 'Client',
        operation: 'sendMessage',
      });
      throw error;
    }

    const startTime = Date.now();
    const messageId = this.generateMessageId();
    const safePreview = this.redactSensitiveContent(content).substring(0, 100);
    
    logger.info('Sending message to siada-cli', {
      component: 'Client',
      operation: 'sendMessage',
      messageId,
      contentLength: content.length,
      contentPreview: safePreview,
    });

    const message: ACPMessage = {
      method: 'agent/execute',
      params: { prompt: content },
      id: messageId,
    };

    try {
      await this.adapter.sendMessage(message);
      
      logger.debug('Message sent successfully', {
        component: 'Client',
        operation: 'sendMessage',
        messageId,
        duration: Date.now() - startTime,
      });
    } catch (error) {
      logger.error('Failed to send message', error, {
        component: 'Client',
        operation: 'sendMessage',
        messageId,
        duration: Date.now() - startTime,
      });
      throw error;
    }
  }

  async sendLoginChoice(choice: string, payload?: string): Promise<void> {
    if (!this.connected) {
      const error = new Error('Not connected to siada-cli');
      logger.error('Cannot send login choice: not connected', error, {
        component: 'Client',
        operation: 'sendLoginChoice',
      });
      throw error;
    }

    const startTime = Date.now();
    const messageId = this.generateMessageId();
    const rawInput = payload
      ? `__LOGIN_CHOICE__:${choice}:${payload}`
      : `__LOGIN_CHOICE__:${choice}`;

    logger.info('Sending login choice to siada-cli', {
      component: 'Client',
      operation: 'sendLoginChoice',
      messageId,
      choice,
      payloadLength: payload?.length ?? 0,
      payloadPreview: payload ? this.redactSensitiveContent(payload).substring(0, 100) : '',
    });

    try {
      await this.adapter.sendRawInput(rawInput, {
        operation: 'sendLoginChoice',
        method: 'login/choice',
        messageId,
      });

      logger.debug('Login choice sent successfully', {
        component: 'Client',
        operation: 'sendLoginChoice',
        messageId,
        duration: Date.now() - startTime,
      });
    } catch (error) {
      logger.error('Failed to send login choice', error, {
        component: 'Client',
        operation: 'sendLoginChoice',
        messageId,
        duration: Date.now() - startTime,
      });
      throw error;
    }
  }

  /**
   * Send interrupt signal to agent (Ctrl+C)
   */
  async interrupt(): Promise<void> {
    if (!this.connected) {
      logger.warn('Cannot interrupt: not connected', {
        component: 'Client',
        operation: 'interrupt',
      });
      return;
    }

    logger.info('Sending interrupt signal to agent', {
      component: 'Client',
      operation: 'interrupt',
    });

    // Send SIGINT to the siada-cli process
    await this.adapter.interrupt();
  }

  /**
   * Stop current agent execution
   */
  async stop(): Promise<void> {
    if (!this.connected) {
      return;
    }

    logger.info('Stopping agent execution');

    const message: ACPMessage = {
      method: 'agent/stop',
      id: this.generateMessageId(),
    };

    await this.adapter.sendMessage(message);
  }

  /**
   * Read file content
   */
  async readFile(path: string): Promise<string> {
    if (!this.connected) {
      throw new Error('Not connected to siada-cli');
    }

    const message: ACPMessage = {
      method: 'files/read',
      params: { path },
      id: this.generateMessageId(),
    };

    await this.adapter.sendMessage(message);
    
    // TODO: Implement response handling
    return '';
  }

  /**
   * Disconnect from siada-cli
   */
  async disconnect(): Promise<void> {
    const startTime = Date.now();
    
    logger.info('Disconnecting from siada-cli', {
      component: 'Client',
      operation: 'disconnect',
      wasConnected: this.connected,
    });

    try {
      await this.adapter.stop();
      this.connected = false;
      this.emit('disconnected');
      
      logger.logWithTiming(
        LogLevel.INFO,
        'Disconnected from siada-cli',
        startTime,
        {
          component: 'Client',
          operation: 'disconnect',
        }
      );
    } catch (error) {
      logger.error('Error during disconnect', error, {
        component: 'Client',
        operation: 'disconnect',
        duration: Date.now() - startTime,
      });
      throw error;
    }
  }

  /**
   * Check if connected
   */
  isConnected(): boolean {
    return this.connected && this.adapter.isAdapterReady();
  }

  /**
   * Generate unique message ID
   */
  private generateMessageId(): string {
    return `msg_${Date.now()}_${this.messageIdCounter++}`;
  }
}
