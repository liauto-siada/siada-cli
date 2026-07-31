/**
 * Siada CLI Process Management
 * Manages the lifecycle of siada-cli subprocess
 */

import { spawn, ChildProcess } from 'child_process';
import { EventEmitter } from 'events';
import { logger } from '../utils/logger.js';

export interface SiadaProcessConfig {
  siadaPath: string;
  workingDir: string;
  pythonPath?: string;
  siadaModule?: string;
  useModuleMode?: boolean;
  acpMode?: boolean;
  args?: string[];
  env?: Record<string, string>;
  model?: string;
  temperature?: number;
  maxTokens?: number;
  thinking?: boolean;
  parallelToolCalls?: boolean;
}

export interface ProcessStatus {
  running: boolean;
  pid?: number;
  startTime?: Date;
  exitCode?: number;
  signal?: string;
}

/**
 * Siada CLI Process Manager
 */
export class SiadaProcessManager extends EventEmitter {
  private process: ChildProcess | null = null;
  private status: ProcessStatus = { running: false };
  private startTime?: Date;

  constructor(private config: SiadaProcessConfig) {
    super();
  }

  /**
   * Start siada-cli process
   */
  async start(): Promise<void> {
    if (this.process) {
      throw new Error('Process already running');
    }

    const { command, args } = this.buildCommand();
    const env = this.buildEnvironment();

    logger.info('Starting siada-cli process', {
      command,
      args,
      workingDir: this.config.workingDir,
      useModuleMode: this.config.useModuleMode,
    });

    try {
      this.process = spawn(command, args, {
        cwd: this.config.workingDir,
        stdio: ['pipe', 'pipe', 'pipe'],
        env,
        // On Windows, hide the console window that Node.js would otherwise
        // create for the spawned Python subprocess. Without this flag a blank
        // black cmd window pops up every time the backend process starts.
        windowsHide: true,
      });

      this.startTime = new Date();
      this.status = {
        running: true,
        pid: this.process.pid,
        startTime: this.startTime,
      };

      this.setupEventHandlers();
      await this.waitForReady();

      logger.info('Siada-cli process started', {
        pid: this.process.pid,
        command,
        args: args.join(' '),
      });

      this.emit('started', this.status);
    } catch (error) {
      logger.error('Failed to start siada-cli process', error);
      throw error;
    }
  }

  /**
   * Build command and arguments
   */
  private buildCommand(): { command: string; args: string[] } {
    if (this.config.useModuleMode && this.config.pythonPath && this.config.siadaModule) {
      // Module mode: python -m siada.entrypoint.siadahub
      logger.debug('Using Python module mode', {
        pythonPath: this.config.pythonPath,
        siadaModule: this.config.siadaModule,
      });

      const args = ['-m', 'siada.entrypoint.siadahub'];
      args.push(...this.buildArguments());

      return {
        command: this.config.pythonPath,
        args,
      };
    } else {
      // Executable mode: siada-cli
      logger.debug('Using executable mode', {
        siadaPath: this.config.siadaPath,
      });

      return {
        command: this.config.siadaPath,
        args: this.buildArguments(),
      };
    }
  }

  /**
   * Build command line arguments
   */
  private buildArguments(): string[] {
    const args: string[] = [];

    // Add custom args from config
    if (this.config.args && this.config.args.length > 0) {
      args.push(...this.config.args);
    }

    // Add model if specified
    if (this.config.model) {
      args.push('--model', this.config.model);
    }

    // Add temperature if specified
    if (this.config.temperature !== undefined) {
      args.push('--temperature', this.config.temperature.toString());
    }

    // Add max tokens if specified
    if (this.config.maxTokens !== undefined) {
      args.push('--max-tokens', this.config.maxTokens.toString());
    }

    // Add thinking if specified
    if (this.config.thinking !== undefined) {
      if (this.config.thinking) {
        args.push('--thinking');
      } else {
        args.push('--no-thinking');
      }
    }

    // Add parallel tool calls if specified
    if (this.config.parallelToolCalls !== undefined) {
      if (this.config.parallelToolCalls) {
        args.push('--parallel-tool-calls');
      } else {
        args.push('--no-parallel-tool-calls');
      }
    }

    logger.debug('Built arguments', { args });

    return args;
  }

  /**
   * Build environment variables
   */
  private buildEnvironment(): Record<string, string> {
    const env: Record<string, string> = {
      ...process.env,
      ...this.config.env,
      // Ensure UTF-8 encoding
      PYTHONIOENCODING: 'utf-8',
      // Disable Python buffering for real-time output
      PYTHONUNBUFFERED: '1',
    } as Record<string, string>;

    // Enable ACP mode for siada-agenthub (enabled by default)
    const acpMode = this.config.acpMode !== undefined ? this.config.acpMode : true;
    if (acpMode) {
      env.SIADA_ACP_MODE = '1';
      logger.info('ACP mode enabled for siada-agenthub communication');
    } else {
      logger.info('ACP mode disabled - using traditional mode');
    }

    // Add PYTHONPATH for module mode
    if (this.config.useModuleMode && this.config.siadaModule) {
      const existingPath = env.PYTHONPATH || '';
      env.PYTHONPATH = existingPath 
        ? `${this.config.siadaModule}:${existingPath}`
        : this.config.siadaModule;
      
      logger.debug('Set PYTHONPATH for module mode', {
        pythonPath: env.PYTHONPATH,
        siadaModule: this.config.siadaModule,
      });
    }

    return env;
  }

  /**
   * Setup process event handlers
   */
  private setupEventHandlers(): void {
    if (!this.process) return;

    this.process.on('exit', (code, signal) => {
      logger.info('Siada-cli process exited', { code, signal });
      
      this.status = {
        running: false,
        exitCode: code ?? undefined,
        signal: signal ?? undefined,
      };

      this.emit('exit', { code, signal });
      this.cleanup();
    });

    this.process.on('error', (error) => {
      logger.error('Siada-cli process error', error);
      this.emit('error', error);
    });

    // Handle stdout
    if (this.process.stdout) {
      this.process.stdout.on('data', (data) => {
        this.emit('stdout', data);
      });
    }

    // Handle stderr
    if (this.process.stderr) {
      this.process.stderr.on('data', (data) => {
        logger.debug('Siada-cli stderr', { data: data.toString() });
        this.emit('stderr', data);
      });
    }
  }

  /**
   * Wait for process to be ready
   */
  private async waitForReady(timeout: number = 5000): Promise<void> {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        reject(new Error('Timeout waiting for siada-cli to be ready'));
      }, timeout);

      // For now, just check if process is running
      // In the future, we could wait for a specific ready message
      if (this.process && !this.process.killed) {
        clearTimeout(timer);
        resolve();
      } else {
        clearTimeout(timer);
        reject(new Error('Process failed to start'));
      }
    });
  }

  /**
   * Stop siada-cli process
   */
  async stop(timeout: number = 5000): Promise<void> {
    if (!this.process || !this.status.running) {
      logger.warn('No process to stop');
      return;
    }

    logger.info('Stopping siada-cli process', { pid: this.process.pid });

    return new Promise((resolve, reject) => {
      if (!this.process) {
        resolve();
        return;
      }

      const timer = setTimeout(() => {
        if (this.process && !this.process.killed) {
          logger.warn('Force killing siada-cli process');
          this.process.kill('SIGKILL');
        }
      }, timeout);

      this.process.once('exit', () => {
        clearTimeout(timer);
        logger.info('Siada-cli process stopped');
        resolve();
      });

      // Try graceful shutdown first
      this.process.kill('SIGTERM');
    });
  }

  /**
   * Send data to process stdin
   */
  write(data: string): boolean {
    if (!this.process || !this.status.running || !this.process.stdin) {
      logger.error('Cannot write to process - not running or stdin not available', {
        hasProcess: !!this.process,
        isRunning: this.status.running,
        hasStdin: this.process?.stdin ? true : false,
      });
      return false;
    }

    logger.debug('Writing to process stdin', {
      dataLength: data.length,
      dataPreview: data.substring(0, 100),
      pid: this.process.pid,
    });

    try {
      const result = this.process.stdin.write(data);
      logger.debug('Write result', { success: result });
      return result;
    } catch (error) {
      logger.error('Error writing to process stdin', error);
      return false;
    }
  }

  /**
   * Get process status
   */
  getStatus(): ProcessStatus {
    return { ...this.status };
  }

  /**
   * Check if process is running
   */
  isRunning(): boolean {
    return this.status.running && this.process !== null && !this.process.killed;
  }

  /**
   * Get process streams
   */
  getStreams(): {
    stdin: NodeJS.WritableStream | null;
    stdout: NodeJS.ReadableStream | null;
    stderr: NodeJS.ReadableStream | null;
  } {
    if (!this.process) {
      return { stdin: null, stdout: null, stderr: null };
    }

    return {
      stdin: this.process.stdin,
      stdout: this.process.stdout,
      stderr: this.process.stderr,
    };
  }

  /**
   * Cleanup resources
   */
  private cleanup(): void {
    if (this.process) {
      this.process.removeAllListeners();
      this.process = null;
    }
  }

  /**
   * Restart process
   */
  async restart(): Promise<void> {
    logger.info('Restarting siada-cli process');
    
    if (this.isRunning()) {
      await this.stop();
    }
    
    // Wait a bit before restarting
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    await this.start();
  }
}

/**
 * Create and start a siada process manager
 */
export async function createSiadaProcess(config: SiadaProcessConfig): Promise<SiadaProcessManager> {
  const manager = new SiadaProcessManager(config);
  await manager.start();
  return manager;
}
