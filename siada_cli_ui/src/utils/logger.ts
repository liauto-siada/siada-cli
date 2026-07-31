/**
 * Enhanced Logger utility for debugging and error tracking
 * Features: Message tracking, performance monitoring, sensitive data filtering
 */

import chalk from 'chalk';
import { writeFileSync, appendFileSync, existsSync, mkdirSync, statSync, renameSync, readdirSync, unlinkSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';

export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
}

export interface LogContext {
  messageId?: string;
  sessionId?: string;
  component?: string;
  operation?: string;
  duration?: number;
  [key: string]: any;
}

export interface LoggerOptions {
  level?: LogLevel;
  enableConsole?: boolean;
  enableFile?: boolean;
  maxFileSize?: number; // in bytes
  maxContentLength?: number;
  filterSensitive?: boolean;
}

export class Logger {
  // 🔥 GLOBAL KILL SWITCH: Disable ALL logging to test if logging causes crashes
  private static LOGGING_ENABLED = true;  // Set to false to disable all logs
  
  private logLevel: LogLevel;
  private logFile?: string;
  private enableConsole: boolean;
  private enableFile: boolean;
  private maxFileSize: number;
  private maxContentLength: number;
  private filterSensitive: boolean;
  private sessionId: string;
  private messageCounter: number = 0;

  // Sensitive patterns to filter
  private sensitivePatterns = [
    /api[_-]?key["\s:=]+["']?([a-zA-Z0-9_-]+)/gi,
    /token["\s:=]+["']?([a-zA-Z0-9_.-]+)/gi,
    /password["\s:=]+["']?([^\s"']+)/gi,
    /secret["\s:=]+["']?([^\s"']+)/gi,
  ];

  constructor(options: LoggerOptions = {}) {
    this.logLevel = options.level ?? LogLevel.INFO;
    this.enableConsole = options.enableConsole ?? true;
    this.enableFile = options.enableFile ?? true;
    this.maxFileSize = options.maxFileSize ?? 10 * 1024 * 1024; // 10MB default
    this.maxContentLength = options.maxContentLength ?? 1000; // 1000 chars default
    this.filterSensitive = options.filterSensitive ?? true;
    this.sessionId = this.generateSessionId();
    
    // Setup log file in home directory
    if (this.enableFile) {
      const logDir = join(homedir(), '.siada-cli', 'ui-logs');
      if (!existsSync(logDir)) {
        mkdirSync(logDir, { recursive: true });
      }
      this.logFile = join(logDir, 'siada-ui.log');
      this.cleanOldLogs(logDir);
      this.checkAndRotateLog();
    }
  }

  private generateSessionId(): string {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  private generateMessageId(): string {
    return `msg_${this.sessionId}_${this.messageCounter++}`;
  }

  private shouldLog(level: LogLevel): boolean {
    return level >= this.logLevel;
  }

  /**
   * Filter sensitive information from data
   */
  private filterSensitiveData(data: any): any {
    if (!this.filterSensitive) return data;
    if (typeof data !== 'object' || data === null) return data;

    const filtered = JSON.parse(JSON.stringify(data));
    
    const filterRecursive = (obj: any) => {
      for (const key in obj) {
        if (typeof obj[key] === 'string') {
          // Filter sensitive patterns
          this.sensitivePatterns.forEach(pattern => {
            obj[key] = obj[key].replace(pattern, (match: string, group: string) => {
              return match.replace(group, '***FILTERED***');
            });
          });
          
          // Filter specific sensitive keys
          if (['apiKey', 'token', 'password', 'secret', 'authorization'].includes(key)) {
            obj[key] = '***FILTERED***';
          }
        } else if (typeof obj[key] === 'object' && obj[key] !== null) {
          filterRecursive(obj[key]);
        }
      }
    };

    filterRecursive(filtered);
    return filtered;
  }

  /**
   * Truncate long content
   */
  private truncateContent(content: string, maxLength: number = this.maxContentLength): string {
    if (content.length <= maxLength) return content;
    return content.substring(0, maxLength) + `... (truncated ${content.length - maxLength} chars)`;
  }

  /**
   * Format message with enhanced context
   */
  private formatMessage(level: string, message: string, context?: LogContext): string {
    // Use local time instead of UTC to match Python logger timezone
    const now = new Date();
    const timestamp = now.getFullYear() + '-' +
      String(now.getMonth() + 1).padStart(2, '0') + '-' +
      String(now.getDate()).padStart(2, '0') + 'T' +
      String(now.getHours()).padStart(2, '0') + ':' +
      String(now.getMinutes()).padStart(2, '0') + ':' +
      String(now.getSeconds()).padStart(2, '0') + '.' +
      String(now.getMilliseconds()).padStart(3, '0') + '+08:00';
    const messageId = context?.messageId || this.generateMessageId();
    
    const contextInfo = {
      timestamp,
      level,
      messageId,
      sessionId: this.sessionId,
      component: context?.component,
      operation: context?.operation,
      duration: context?.duration,
    };

    // Remove undefined fields
    Object.keys(contextInfo).forEach(key => 
      contextInfo[key as keyof typeof contextInfo] === undefined && delete contextInfo[key as keyof typeof contextInfo]
    );

    // Build structured log
    let logLine = `[${timestamp}] [${level}]`;
    
    if (context?.component) {
      logLine += ` [${context.component}]`;
    }
    
    if (context?.operation) {
      logLine += ` [${context.operation}]`;
    }
    
    if (context?.messageId) {
      logLine += ` [${context.messageId}]`;
    }
    
    logLine += ` ${message}`;

    // Add additional context
    if (context) {
      const { messageId, component, operation, duration, ...rest } = context;
      if (Object.keys(rest).length > 0) {
        const filtered = this.filterSensitiveData(rest);
        const contextStr = JSON.stringify(filtered, null, 2);
        logLine += `\n${this.truncateContent(contextStr)}`;
      }
    }

    if (context?.duration !== undefined) {
      logLine += `\n⏱️  Duration: ${context.duration}ms`;
    }

    return logLine;
  }

  /**
   * Clean old log files (keep only last 7 days)
   */
  private cleanOldLogs(logDir: string): void {
    try {
      const files = readdirSync(logDir);
      const now = Date.now();
      const sevenDaysInMs = 7 * 24 * 60 * 60 * 1000; // 7 days in milliseconds

      files.forEach(file => {
        // Only process log files (*.log)
        if (!file.endsWith('.log')) return;
        
        const filePath = join(logDir, file);
        try {
          const stats = statSync(filePath);
          const fileAge = now - stats.mtimeMs;
          
          // Delete files older than 7 days
          if (fileAge > sevenDaysInMs) {
            unlinkSync(filePath);
          }
        } catch (error) {
          // Silently fail for individual files
        }
      });
    } catch (error) {
      // Silently fail if unable to clean logs
    }
  }

  /**
   * Check and rotate log file if needed
   */
  private checkAndRotateLog(): void {
    if (!this.logFile || !existsSync(this.logFile)) return;

    try {
      const stats = statSync(this.logFile);
      if (stats.size > this.maxFileSize) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const rotatedFile = this.logFile.replace('.log', `.${timestamp}.log`);
        renameSync(this.logFile, rotatedFile);
      }
    } catch (error) {
      // Silently fail
    }
  }

  /**
   * Write to log file
   */
  private writeToFile(message: string): void {
    if (!this.enableFile || !this.logFile) return;

    try {
      this.checkAndRotateLog();
      appendFileSync(this.logFile, message + '\n');
    } catch (error) {
      // Silently fail if unable to write to log file
    }
  }

  /**
   * Log debug message
   */
  debug(message: string, context?: LogContext): void {
    if (!Logger.LOGGING_ENABLED) return;  // 🔥 Kill switch
    if (this.shouldLog(LogLevel.DEBUG)) {
      const formatted = this.formatMessage('DEBUG', message, context);
      // Console output disabled - only write to file
      this.writeToFile(formatted);
    }
  }

  /**
   * Log info message
   */
  info(message: string, context?: LogContext): void {
    if (!Logger.LOGGING_ENABLED) return;  // 🔥 Kill switch
    if (this.shouldLog(LogLevel.INFO)) {
      const formatted = this.formatMessage('INFO', message, context);
      // Console output disabled - only write to file
      this.writeToFile(formatted);
    }
  }

  /**
   * Log warning message
   */
  warn(message: string, context?: LogContext): void {
    if (!Logger.LOGGING_ENABLED) return;  // 🔥 Kill switch
    if (this.shouldLog(LogLevel.WARN)) {
      const formatted = this.formatMessage('WARN', message, context);
      // Console output disabled - only write to file
      this.writeToFile(formatted);
    }
  }

  /**
   * Log error message
   */
  error(message: string, error?: Error | any, context?: LogContext): void {
    if (!Logger.LOGGING_ENABLED) return;  // 🔥 Kill switch
    if (this.shouldLog(LogLevel.ERROR)) {
      const errorData = error instanceof Error ? {
        message: error.message,
        stack: error.stack,
        name: error.name,
      } : error;
      
      const fullContext = { ...context, error: errorData };
      const formatted = this.formatMessage('ERROR', message, fullContext);
      
      // Console output disabled - only write to file
      this.writeToFile(formatted);
    }
  }

  /**
   * Log message with performance tracking
   */
  logWithTiming(level: LogLevel, message: string, startTime: number, context?: LogContext): void {
    const duration = Date.now() - startTime;
    const fullContext = { ...context, duration };
    
    switch (level) {
      case LogLevel.DEBUG:
        this.debug(message, fullContext);
        break;
      case LogLevel.INFO:
        this.info(message, fullContext);
        break;
      case LogLevel.WARN:
        this.warn(message, fullContext);
        break;
      case LogLevel.ERROR:
        this.error(message, undefined, fullContext);
        break;
    }
  }

  /**
   * Log ACP message
   */
  logACPMessage(direction: 'send' | 'receive', message: any, context?: LogContext): void {
    const arrow = direction === 'send' ? '→' : '←';
    const messageStr = typeof message === 'string' 
      ? this.truncateContent(message)
      : this.truncateContent(JSON.stringify(message, null, 2));
    
    this.debug(`${arrow} ACP Message [${direction}]`, {
      ...context,
      component: 'ACP',
      messageContent: messageStr,
      messageType: message?.method || message?.type || 'unknown',
    });
  }

  /**
   * Log protocol conversion
   */
  logConversion(from: string, to: string, input: any, output: any, context?: LogContext): void {
    this.debug(`Protocol conversion: ${from} → ${to}`, {
      ...context,
      component: 'Converter',
      input: this.truncateContent(typeof input === 'string' ? input : JSON.stringify(input)),
      output: this.truncateContent(typeof output === 'string' ? output : JSON.stringify(output)),
    });
  }

  /**
   * Log state change
   */
  logStateChange(component: string, from: string, to: string, context?: LogContext): void {
    this.info(`State change: ${from} → ${to}`, {
      ...context,
      component,
      operation: 'state_change',
      fromState: from,
      toState: to,
    });
  }

  /**
   * Set log level
   */
  setLevel(level: LogLevel): void {
    this.logLevel = level;
  }

  /**
   * Get current session ID
   */
  getSessionId(): string {
    return this.sessionId;
  }

  /**
   * Get log file path
   */
  getLogFile(): string | undefined {
    return this.logFile;
  }

  /**
   * Log memory usage
   */
  // logMemoryUsage(component: string, context?: LogContext): void {
  //   if (!Logger.LOGGING_ENABLED) return;  // 🔥 Kill switch
  //   const usage = process.memoryUsage();
  //   const formatBytes = (bytes: number) => {
  //     return (bytes / 1024 / 1024).toFixed(2) + ' MB';
  //   };

  //   this.info(`Memory usage snapshot`, {
  //     ...context,
  //     component,
  //     operation: 'memory_check',
  //     heapUsed: formatBytes(usage.heapUsed),
  //     heapTotal: formatBytes(usage.heapTotal),
  //     rss: formatBytes(usage.rss),
  //     external: formatBytes(usage.external),
  //     arrayBuffers: formatBytes(usage.arrayBuffers || 0),
  //   });
  // }

  /**
   * Log message array statistics
   */
  // logMessageStats(messageCount: number, context?: LogContext): void {
  //   if (!Logger.LOGGING_ENABLED) return;  // 🔥 Kill switch
  //   this.info(`Message array statistics`, {
  //     ...context,
  //     component: 'MessageStore',
  //     operation: 'stats',
  //     messageCount,
  //     memoryEstimate: ((messageCount * 5) / 1024).toFixed(2) + ' KB (estimated)',
  //   });
  // }
}

// Export singleton instance
export const logger = new Logger({
  level: process.env.SIADA_DEBUG ? LogLevel.DEBUG : LogLevel.INFO,
  enableConsole: false, // Disabled to prevent terminal crashes
  enableFile: true,
  maxFileSize: 10 * 1024 * 1024, // 10MB
  maxContentLength: 1000,
  filterSensitive: true,
}
);
