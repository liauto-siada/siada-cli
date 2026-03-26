/**
 * Message Handler Service
 * Processes and transforms messages between UI and ACP protocol
 */

import { EventEmitter } from 'events';
import { Message, MessageType, ToolCall, FileEdit, AgentMessageSubtype } from '../types/index.js';
import { ACPEvent, ACPEventType, ToolCallInfo, FileEditInfo } from '../acp/types.js';
import { logger } from '../utils/logger.js';

export interface MessageHandlerOptions {
  maxMessages?: number;
  enableHistory?: boolean;
}

/**
 * Message Handler - manages message processing and transformation
 */
export class MessageHandler extends EventEmitter {
  private messages: Message[] = [];
  private messageIdCounter: number = 0;
  private maxMessages: number;
  private enableHistory: boolean;
  // Track the current streaming message to accumulate chunks
  private currentStreamingMessage: Message | null = null;
  private streamingMessageType: 'thinking' | 'answer' | null = null;

  constructor(options: MessageHandlerOptions = {}) {
    super();
    this.maxMessages = options.maxMessages || 1000;
    this.enableHistory = options.enableHistory ?? true;
  }

  /**
   * Add user message
   */
  addUserMessage(content: string): Message {
    const message: Message = {
      id: this.generateMessageId(),
      type: 'user',
      content,
      timestamp: new Date().toISOString(),
      author: 'You',
    };

    this.addMessage(message);
    return message;
  }

  /**
   * Add agent message
   */
  addAgentMessage(content: string, metadata?: Record<string, any>): Message {
    const message: Message = {
      id: this.generateMessageId(),
      type: 'agent',
      content,
      timestamp: new Date().toISOString(),
      author: 'Siada',
      metadata,
    };

    this.addMessage(message);
    return message;
  }

  /**
   * Add system message
   */
  addSystemMessage(content: string): Message {
    const message: Message = {
      id: this.generateMessageId(),
      type: 'system',
      content,
      timestamp: new Date().toISOString(),
      author: 'System',
    };

    this.addMessage(message);
    return message;
  }

  /**
   * Add error message
   */
  addErrorMessage(content: string, error?: any): Message {
    const message: Message = {
      id: this.generateMessageId(),
      type: 'error',
      content,
      timestamp: new Date().toISOString(),
      author: 'System',
      metadata: error ? { error } : undefined,
    };

    this.addMessage(message);
    return message;
  }

  /**
   * Add tool call message
   */
  addToolCallMessage(toolCalls: ToolCall[]): Message {
    const message: Message = {
      id: this.generateMessageId(),
      type: 'tool',
      content: `Executing ${toolCalls.length} tool call(s)`,
      timestamp: new Date().toISOString(),
      author: 'Siada',
      toolCalls,
    };

    this.addMessage(message);
    return message;
  }

  /**
   * Add file edit message
   */
  addFileEditMessage(fileEdits: FileEdit[]): Message {
    const fileList = fileEdits.map(f => `${f.action}: ${f.path}`).join(', ');
    const message: Message = {
      id: this.generateMessageId(),
      type: 'system',
      content: `File operations: ${fileList}`,
      timestamp: new Date().toISOString(),
      author: 'Siada',
      fileEdits,
    };

    this.addMessage(message);
    return message;
  }

  /**
   * Add message to list
   */
  private addMessage(message: Message): void {
    if (this.enableHistory) {
      this.messages.push(message);

      // Trim messages if exceeding max
      if (this.messages.length > this.maxMessages) {
        this.messages = this.messages.slice(-this.maxMessages);
      }
    }

    this.emit('message', message);
    logger.debug('Message added', { id: message.id, type: message.type });
  }

  /**
   * Update existing message
   */
  updateMessage(id: string, updates: Partial<Message>): void {
    const index = this.messages.findIndex(m => m.id === id);
    
    if (index !== -1) {
      this.messages[index] = {
        ...this.messages[index],
        ...updates,
      };
      this.emit('messageUpdated', this.messages[index]);
    }
  }

  /**
   * Process ACP event and convert to message
   */
  processACPEvent(event: ACPEvent): Message | null {
    try {
      switch (event.type) {
        case 'message':
          // Check if this is a block message with metadata
          if (event.data.blockType) {
            const blockMessage = this.handleBlockMessage(event.data.content, event.data.blockType, event.data.subtype);
            // handleBlockMessage may return null for filtered blocks (e.g., banner)
            return blockMessage;
          }
          return this.addAgentMessage(event.data.content || event.data);

        case 'toolUse':
          // Finalize any streaming message before showing tool use
          this.finalizeStreamingMessage();
          return this.handleToolUseEvent(event.data);

        case 'fileEdit':
          // Finalize any streaming message before showing file edit
          this.finalizeStreamingMessage();
          return this.handleFileEditEvent(event.data);

        case 'error':
          // Finalize any streaming message before showing error
          this.finalizeStreamingMessage();
          return this.addErrorMessage(event.data.message || 'An error occurred', event.data);

        case 'thinking':
          // Finalize any streaming message before showing thinking
          this.finalizeStreamingMessage();
          return this.addSystemMessage(`💭 ${event.data.content || 'Thinking...'}`);

        case 'progress':
          return this.handleProgressEvent(event.data);

        case 'complete':
          // Finalize any streaming message when task completes
          this.finalizeStreamingMessage();
          return this.addSystemMessage('✓ Task completed');

        default:
          logger.warn('Unknown ACP event type', { type: event.type });
          return null;
      }
    } catch (error) {
      logger.error('Error processing ACP event', { error, event });
      return null;
    }
  }

  /**
   * Handle block message from siada-cli output
   */
  private handleBlockMessage(content: string, blockType: string, subtype?: string): Message | null {
    // Skip banner blocks - they should not be displayed as messages
    if (blockType === 'banner') {
      logger.info('Skipping banner block message', {
        component: 'MessageHandler',
        operation: 'handleBlockMessage',
      });
      return null;
    }
    
    // Determine if this is part of a streaming answer
    const isAnswerChunk = blockType === 'agent' && subtype === 'answer';
    const isThinkingChunk = blockType === 'agent' && subtype === 'thinking';
    
    // Handle streaming answer chunks - accumulate them into one message
    if (isAnswerChunk) {
      return this.handleStreamingChunk(content, 'answer');
    }
    
    // Handle thinking chunks - accumulate them into one message
    if (isThinkingChunk) {
      return this.handleStreamingChunk(content, 'thinking');
    }
    
    // For non-streaming messages, finalize any current streaming message first
    this.finalizeStreamingMessage();
    
    // Determine message type based on block type
    let messageType: MessageType;
    let author: string;
    
    switch (blockType) {
      case 'agent':
        messageType = 'agent';
        author = 'Siada';
        break;
      default:
        messageType = 'agent';
        author = 'Siada';
    }
    
    const message: Message = {
      id: this.generateMessageId(),
      type: messageType,
      content,
      timestamp: new Date().toISOString(),
      author,
      metadata: { 
        blockType, 
        subtype: subtype as AgentMessageSubtype | undefined
      },
    };

    this.addMessage(message);
    return message;
  }

  /**
   * Handle streaming message chunk - accumulate chunks into a single message
   */
  private handleStreamingChunk(content: string, type: 'thinking' | 'answer'): Message | null {
    // If we're starting a new streaming message or switching types
    if (!this.currentStreamingMessage || this.streamingMessageType !== type) {
      // Finalize any previous streaming message
      this.finalizeStreamingMessage();
      
      // Start a new streaming message
      const messageType: MessageType = type === 'thinking' ? 'system' : 'agent';
      const author = type === 'thinking' ? 'System' : 'Siada';
      const prefix = type === 'thinking' ? '💭 ' : '';
      
      this.currentStreamingMessage = {
        id: this.generateMessageId(),
        type: messageType,
        content: prefix + content,
        timestamp: new Date().toISOString(),
        author,
        metadata: { subtype: type, streaming: true },
      };
      this.streamingMessageType = type;
      
      // Add the initial message
      this.addMessage(this.currentStreamingMessage);
      
      logger.debug('Started streaming message', {
        id: this.currentStreamingMessage.id,
        type,
        contentLength: content.length,
      });
      
      return this.currentStreamingMessage;
    } else {
      // Append to existing streaming message
      this.currentStreamingMessage.content += content;
      
      // Update the message in the messages array
      const index = this.messages.findIndex(m => m.id === this.currentStreamingMessage!.id);
      if (index !== -1) {
        this.messages[index] = this.currentStreamingMessage;
      }
      
      // Emit update event for UI to re-render
      this.emit('messageUpdated', this.currentStreamingMessage);
      
      logger.debug('Appended to streaming message', {
        id: this.currentStreamingMessage.id,
        type,
        totalLength: this.currentStreamingMessage.content.length,
        appendedLength: content.length,
      });
      
      return this.currentStreamingMessage;
    }
  }

  /**
   * Finalize the current streaming message
   */
  private finalizeStreamingMessage(): void {
    if (this.currentStreamingMessage) {
      // Remove streaming flag from metadata
      if (this.currentStreamingMessage.metadata) {
        delete this.currentStreamingMessage.metadata.streaming;
      }
      
      // Update the message in the messages array
      const index = this.messages.findIndex(m => m.id === this.currentStreamingMessage!.id);
      if (index !== -1) {
        this.messages[index] = this.currentStreamingMessage;
      }
      
      // Emit final update
      this.emit('messageUpdated', this.currentStreamingMessage);
      
      logger.debug('Finalized streaming message', {
        id: this.currentStreamingMessage.id,
        type: this.streamingMessageType,
        finalLength: this.currentStreamingMessage.content.length,
      });
      
      this.currentStreamingMessage = null;
      this.streamingMessageType = null;
    }
  }

  /**
   * Handle tool use event
   */
  private handleToolUseEvent(data: ToolCallInfo | ToolCallInfo[]): Message {
    const toolCalls = Array.isArray(data) ? data : [data];
    
    const mappedToolCalls: ToolCall[] = toolCalls.map(tc => ({
      id: tc.id,
      name: tc.name,
      args: tc.arguments || {},
      result: tc.result,
      status: tc.status,
      timestamp: new Date().toISOString(),
    }));

    return this.addToolCallMessage(mappedToolCalls);
  }

  /**
   * Handle file edit event
   */
  private handleFileEditEvent(data: FileEditInfo | FileEditInfo[]): Message {
    const fileEdits = Array.isArray(data) ? data : [data];
    
    const mappedFileEdits: FileEdit[] = fileEdits.map(fe => ({
      path: fe.path,
      action: fe.action,
      content: fe.content,
      diff: undefined,
      timestamp: new Date().toISOString(),
    }));

    return this.addFileEditMessage(mappedFileEdits);
  }

  /**
   * Handle progress event
   */
  private handleProgressEvent(data: any): Message | null {
    if (data.kind === 'begin') {
      return this.addSystemMessage(`⏳ ${data.title || 'Processing...'}`);
    } else if (data.kind === 'report' && data.message) {
      return this.addSystemMessage(`⏳ ${data.message}`);
    } else if (data.kind === 'end') {
      return this.addSystemMessage('✓ Completed');
    }
    return null;
  }

  /**
   * Get all messages
   */
  getMessages(): Message[] {
    return [...this.messages];
  }

  /**
   * Get message by ID
   */
  getMessage(id: string): Message | undefined {
    return this.messages.find(m => m.id === id);
  }

  /**
   * Clear all messages
   */
  clearMessages(): void {
    // Finalize any streaming message before clearing
    this.finalizeStreamingMessage();
    this.messages = [];
    this.emit('messagesCleared');
  }

  /**
   * Get messages by type
   */
  getMessagesByType(type: MessageType): Message[] {
    return this.messages.filter(m => m.type === type);
  }

  /**
   * Search messages
   */
  searchMessages(query: string): Message[] {
    const lowerQuery = query.toLowerCase();
    return this.messages.filter(m =>
      m.content.toLowerCase().includes(lowerQuery) ||
      m.author.toLowerCase().includes(lowerQuery)
    );
  }

  /**
   * Generate unique message ID
   */
  private generateMessageId(): string {
    return `msg_${++this.messageIdCounter}_${Date.now()}`;
  }

  /**
   * Export messages as JSON
   */
  exportMessages(): string {
    return JSON.stringify(this.messages, null, 2);
  }

  /**
   * Import messages from JSON
   */
  importMessages(json: string): void {
    try {
      const messages = JSON.parse(json) as Message[];
      this.messages = messages;
      this.emit('messagesImported', messages.length);
    } catch (error) {
      logger.error('Failed to import messages', error);
      throw new Error('Invalid message data');
    }
  }

  /**
   * Get message count
   */
  getMessageCount(): number {
    return this.messages.length;
  }

  /**
   * Get statistics
   */
  getStats(): {
    total: number;
    byType: Record<MessageType, number>;
    withToolCalls: number;
    withFileEdits: number;
  } {
    const byType: Record<string, number> = {};
    let withToolCalls = 0;
    let withFileEdits = 0;

    for (const message of this.messages) {
      byType[message.type] = (byType[message.type] || 0) + 1;
      if (message.toolCalls && message.toolCalls.length > 0) withToolCalls++;
      if (message.fileEdits && message.fileEdits.length > 0) withFileEdits++;
    }

    return {
      total: this.messages.length,
      byType: byType as Record<MessageType, number>,
      withToolCalls,
      withFileEdits,
    };
  }
}

/**
 * Create message handler instance
 */
export function createMessageHandler(options?: MessageHandlerOptions): MessageHandler {
  return new MessageHandler(options);
}
