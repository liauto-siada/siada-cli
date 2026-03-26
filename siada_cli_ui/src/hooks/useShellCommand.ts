/**
 * Shell Command Hook
 * Handles shell command execution with streaming output
 */

import { useState, useCallback, useRef } from 'react';
import { ShellExecutionService } from '../services/shellExecutionService.js';
import {
  ShellExecutionResult,
  ShellExecutionOptions,
  ShellExecutionEvent,
} from '../types/shell.js';
import { logger } from '../utils/logger.js';

export interface ShellCommandState {
  /** Whether a command is currently executing */
  executing: boolean;
  
  /** Accumulated stdout output */
  stdout: string;
  
  /** Accumulated stderr output */
  stderr: string;
  
  /** Process ID */
  pid?: number;
  
  /** Whether command was killed */
  killed: boolean;
  
  /** Exit code */
  exitCode?: number | null;
  
  /** Error message */
  error?: string;
  
  /** Whether binary output was detected */
  isBinary: boolean;
  
  /** Bytes received for binary output */
  binaryBytesReceived: number;
  
  /** Final working directory (if changed) */
  finalCwd?: string;
}

export interface UseShellCommandOptions {
  /** Working directory */
  cwd: string;
  
  /** Callback for real-time stdout chunks */
  onStdout?: (chunk: string) => void;
  
  /** Callback for real-time stderr chunks */
  onStderr?: (chunk: string) => void;
  
  /** Callback when command starts */
  onStart?: (pid: number) => void;
  
  /** Callback when command exits */
  onExit?: (exitCode: number | null, killed: boolean) => void;
  
  /** Callback when binary output is detected */
  onBinaryDetected?: () => void;
  
  /** Callback for errors */
  onError?: (error: Error) => void;
}

const INITIAL_STATE: ShellCommandState = {
  executing: false,
  stdout: '',
  stderr: '',
  killed: false,
  isBinary: false,
  binaryBytesReceived: 0,
};

/**
 * Hook for executing shell commands
 */
export function useShellCommand(options: UseShellCommandOptions) {
  const [state, setState] = useState<ShellCommandState>(INITIAL_STATE);
  const abortControllerRef = useRef<AbortController | null>(null);

  /**
   * Execute a shell command
   */
  const execute = useCallback(async (command: string): Promise<ShellExecutionResult> => {
    logger.info('Executing shell command', {
      component: 'useShellCommand',
      operation: 'execute',
      command: command.substring(0, 100),
    });

    // Reset state
    setState({
      ...INITIAL_STATE,
      executing: true,
    });

    // Create abort controller
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const execOptions: ShellExecutionOptions = {
        cwd: options.cwd,
        signal: controller.signal,
      };

      // Event callback for streaming output
      const handleEvent = (event: ShellExecutionEvent) => {
        switch (event.type) {
          case 'start':
            setState(prev => ({ ...prev, pid: event.pid }));
            options.onStart?.(event.pid);
            break;

          case 'data':
            if (event.stream === 'stdout') {
              setState(prev => ({ ...prev, stdout: prev.stdout + event.chunk }));
              options.onStdout?.(event.chunk);
            } else {
              setState(prev => ({ ...prev, stderr: prev.stderr + event.chunk }));
              options.onStderr?.(event.chunk);
            }
            break;

          case 'binary_detected':
            setState(prev => ({
              ...prev,
              isBinary: true,
              binaryBytesReceived: event.bytesReceived,
            }));
            options.onBinaryDetected?.();
            break;

          case 'binary_progress':
            setState(prev => ({
              ...prev,
              binaryBytesReceived: event.bytesReceived,
            }));
            break;

          case 'exit':
            setState(prev => ({
              ...prev,
              executing: false,
              exitCode: event.exitCode,
              killed: event.killed,
            }));
            options.onExit?.(event.exitCode, event.killed);
            break;

          case 'error':
            setState(prev => ({
              ...prev,
              executing: false,
              error: event.error.message,
            }));
            options.onError?.(event.error);
            break;
        }
      };

      // Execute command
      const { pid, result } = await ShellExecutionService.execute(
        command,
        execOptions,
        handleEvent
      );

      // Update final state
      setState(prev => ({
        ...prev,
        executing: false,
        exitCode: result.exitCode,
        killed: result.killed,
        error: result.error,
        finalCwd: result.finalCwd,
      }));

      logger.info('Command execution completed', {
        component: 'useShellCommand',
        operation: 'complete',
        pid,
        exitCode: result.exitCode,
        duration: result.duration,
      });

      return result;
    } catch (error) {
      const err = error as Error;
      setState(prev => ({
        ...prev,
        executing: false,
        error: err.message,
      }));

      logger.error('Command execution failed', {
        component: 'useShellCommand',
        operation: 'error',
        error: err.message,
      });

      throw error;
    } finally {
      abortControllerRef.current = null;
    }
  }, [options]);

  /**
   * Cancel current command execution
   */
  const cancel = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      logger.info('Command execution cancelled', {
        component: 'useShellCommand',
        operation: 'cancel',
      });
    }
  }, []);

  /**
   * Reset state
   */
  const reset = useCallback(() => {
    setState(INITIAL_STATE);
  }, []);

  /**
   * Check if command is dangerous
   */
  const isDangerous = useCallback((command: string): boolean => {
    return ShellExecutionService.isDangerousCommand(command);
  }, []);

  return {
    ...state,
    execute,
    cancel,
    reset,
    isDangerous,
  };
}
