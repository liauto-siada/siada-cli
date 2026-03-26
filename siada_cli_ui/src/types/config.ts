/**
 * Configuration Type Definitions
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export type ThemeType = 'light' | 'dark' | 'auto';

export interface ClientConfig {
  workingDir: string;
  model?: string;
  temperature?: number;
  maxTokens?: number;
  thinking?: boolean;
  reasoningEffort?: string;
  parallelToolCalls?: boolean;
  siadaPath?: string;
  pythonPath?: string;
  siadaModule?: string;
  useModuleMode?: boolean;
  acpMode?: boolean;
  siadaArgs?: string[];
  env?: Record<string, string>;
}
