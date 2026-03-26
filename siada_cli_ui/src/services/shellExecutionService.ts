/**
 * Shell Execution Service
 * Handles shell command execution with streaming output
 */

import { spawn, ChildProcess } from 'child_process';
import * as os from 'os';
import * as path from 'path';
import * as fs from 'fs';
import * as crypto from 'crypto';
import {
  ShellExecutionResult,
  ShellExecutionOptions,
  ShellExecutionEvent,
  ShellExecutionCallback,
} from '../types/shell.js';
import { logger } from '../utils/logger.js';

/**
 * Default shell execution options
 */
const DEFAULT_OPTIONS: Partial<ShellExecutionOptions> = {
  timeout: 0, // No timeout by default
  maxBuffer: 10 * 1024 * 1024, // 10MB
  interactive: false,
};

/**
 * Binary data detection threshold (bytes)
 * If we see this many non-text bytes, consider it binary
 */
const BINARY_DETECTION_THRESHOLD = 1024;

/**
 * Check if buffer contains binary data
 */
function isBinaryData(buffer: Buffer): boolean {
  let nonTextCount = 0;
  const sampleSize = Math.min(buffer.length, BINARY_DETECTION_THRESHOLD);
  
  for (let i = 0; i < sampleSize; i++) {
    const byte = buffer[i];
    // Check for null bytes or other non-printable characters
    if (byte === 0 || (byte < 32 && byte !== 9 && byte !== 10 && byte !== 13)) {
      nonTextCount++;
    }
  }
  
  // If more than 10% are non-text bytes, consider it binary
  return nonTextCount > sampleSize * 0.1;
}

/**
 * Get default shell for the platform
 */
function getDefaultShell(): string {
  if (process.platform === 'win32') {
    return process.env.COMSPEC || 'cmd.exe';
  }
  return process.env.SHELL || '/bin/sh';
}

/**
 * Shell Execution Service
 * Singleton service for executing shell commands
 */
export class ShellExecutionService {
  /**
   * Execute a shell command
   * 
   * @param command - Command to execute
   * @param options - Execution options
   * @param callback - Callback for streaming events
   * @returns Promise with execution result and PID
   */
  static async execute(
    command: string,
    options: ShellExecutionOptions,
    callback?: ShellExecutionCallback,
  ): Promise<{ pid: number; result: ShellExecutionResult }> {
    const startTime = Date.now();
    const opts = { ...DEFAULT_OPTIONS, ...options };
    
    logger.info('Executing shell command', {
      component: 'ShellExecutionService',
      operation: 'execute',
      command: command.substring(0, 100), // Log first 100 chars
      cwd: opts.cwd,
      timeout: opts.timeout,
    });

    // Track pwd changes on non-Windows systems
    let pwdFilePath: string | undefined;
    let commandToExecute = command;
    
    if (process.platform !== 'win32') {
      const pwdFileName = `shell_pwd_${crypto.randomBytes(6).toString('hex')}.tmp`;
      pwdFilePath = path.join(os.tmpdir(), pwdFileName);
      
      // Wrap command to capture final working directory
      let cmd = command.trim();
      if (!cmd.endsWith(';') && !cmd.endsWith('&')) {
        cmd += ';';
      }
      commandToExecute = `{ ${cmd} }; __code=$?; pwd > "${pwdFilePath}"; exit $__code`;
    }

    return new Promise((resolve, reject) => {
      const shell = opts.shell || getDefaultShell();
      const shellArgs = process.platform === 'win32' ? ['/c', commandToExecute] : ['-c', commandToExecute];
      
      const proc: ChildProcess = spawn(shell, shellArgs, {
        cwd: opts.cwd,
        env: {
          ...process.env,
          ...opts.env,
          SIADA_CLI: '1', // Mark as running in Siada CLI
        },
        stdio: opts.interactive ? 'inherit' : 'pipe',
      });

      const pid = proc.pid!;
      let stdout = '';
      let stderr = '';
      let killed = false;
      let isBinary = false;
      let binaryBytesReceived = 0;

      // Emit start event
      callback?.({ type: 'start', pid });

      // Setup timeout
      let timeoutId: NodeJS.Timeout | undefined;
      if (opts.timeout && opts.timeout > 0) {
        timeoutId = setTimeout(() => {
          killed = true;
          proc.kill('SIGTERM');
          logger.warn('Command timeout, killing process', {
            component: 'ShellExecutionService',
            operation: 'timeout',
            pid,
            timeout: opts.timeout,
          });
        }, opts.timeout);
      }

      // Setup abort signal
      if (opts.signal) {
        opts.signal.addEventListener('abort', () => {
          killed = true;
          proc.kill('SIGTERM');
          logger.info('Command aborted by signal', {
            component: 'ShellExecutionService',
            operation: 'abort',
            pid,
          });
        });
      }

      // Handle stdout
      if (proc.stdout) {
        proc.stdout.on('data', (chunk: Buffer) => {
          // Check for binary data
          if (!isBinary && isBinaryData(chunk)) {
            isBinary = true;
            callback?.({
              type: 'binary_detected',
              bytesReceived: chunk.length,
            });
            logger.warn('Binary output detected', {
              component: 'ShellExecutionService',
              operation: 'binary_detected',
              pid,
            });
          }

          if (isBinary) {
            binaryBytesReceived += chunk.length;
            callback?.({
              type: 'binary_progress',
              bytesReceived: binaryBytesReceived,
            });
          } else {
            const text = chunk.toString('utf8');
            stdout += text;
            callback?.({
              type: 'data',
              chunk: text,
              stream: 'stdout',
            });
          }
        });
      }

      // Handle stderr
      if (proc.stderr) {
        proc.stderr.on('data', (chunk: Buffer) => {
          const text = chunk.toString('utf8');
          stderr += text;
          callback?.({
            type: 'data',
            chunk: text,
            stream: 'stderr',
          });
        });
      }

      // Handle exit
      proc.on('exit', (exitCode) => {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }

        const duration = Date.now() - startTime;
        
        // Read final working directory
        let finalCwd: string | undefined;
        if (pwdFilePath && fs.existsSync(pwdFilePath)) {
          try {
            finalCwd = fs.readFileSync(pwdFilePath, 'utf8').trim();
            fs.unlinkSync(pwdFilePath); // Clean up temp file
          } catch (err) {
            logger.warn('Failed to read pwd file', {
              component: 'ShellExecutionService',
              operation: 'read_pwd',
              error: err,
            });
          }
        }

        const result: ShellExecutionResult = {
          exitCode,
          stdout: isBinary ? `[Binary output, ${binaryBytesReceived} bytes received]` : stdout,
          stderr,
          killed,
          pid,
          duration,
          isBinary,
          finalCwd,
        };

        callback?.({
          type: 'exit',
          exitCode,
          killed,
        });

        logger.info('Command execution completed', {
          component: 'ShellExecutionService',
          operation: 'complete',
          pid,
          exitCode,
          duration,
          stdoutLength: stdout.length,
          stderrLength: stderr.length,
          killed,
          isBinary,
        });

        resolve({ pid, result });
      });

      // Handle errors
      proc.on('error', (error) => {
        if (timeoutId) {
          clearTimeout(timeoutId);
        }

        const duration = Date.now() - startTime;
        
        callback?.({
          type: 'error',
          error,
        });

        logger.error('Command execution error', {
          component: 'ShellExecutionService',
          operation: 'error',
          error: error.message,
          pid,
          duration,
        });

        const result: ShellExecutionResult = {
          exitCode: null,
          stdout,
          stderr,
          killed,
          error: error.message,
          pid,
          duration,
        };

        resolve({ pid, result });
      });
    });
  }

  /**
   * Format memory/bytes for display
   */
  static formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  /**
   * Escape shell argument
   */
  static escapeArg(arg: string): string {
    if (process.platform === 'win32') {
      // Windows escaping
      return `"${arg.replace(/"/g, '""')}"`;
    }
    // Unix escaping
    return `'${arg.replace(/'/g, "'\\''")}'`;
  }

  /**
   * Check if command is dangerous
   */
  static isDangerousCommand(command: string): boolean {
    const dangerousPatterns = [
      /\brm\s+-rf\s+\//,
      /\bformat\b/,
      /\bmkfs\b/,
      /\bdd\s+if=/,
      /\bshutdown\b/,
      /\breboot\b/,
      /\binit\s+0/,
      /:\(\)\{.*:\|:.*\};:/,  // Fork bomb
    ];

    return dangerousPatterns.some(pattern => pattern.test(command));
  }
}
