/**
 * Configuration management
 */

import { readFileSync, existsSync, writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { homedir } from 'os';
import { ClientConfig } from '../types/index.js';
import type { EditorType } from './editor.js';

export interface UserConfig {
  model?: string;
  temperature?: number;
  maxTokens?: number;
  thinking?: boolean;
  parallelToolCalls?: boolean;
  theme?: 'dark' | 'light';
  shortcuts?: Record<string, string>;
  preferredEditor?: EditorType;
  siada?: {
    path?: string;
    pythonPath?: string;
    modulePath?: string;
    useModuleMode?: boolean;
    acpMode?: boolean;
    args?: string[];
  };
}

export class ConfigManager {
  private config: UserConfig = {};
  private configPaths = [
    join(homedir(), '.siadauirc'),
    join(homedir(), '.config', 'siada-ui', 'config.json'),
    join(process.cwd(), '.siadauirc'),
  ];

  constructor() {
    this.loadConfig();
  }

  private loadConfig(): void {
    for (const configPath of this.configPaths) {
      if (existsSync(configPath)) {
        try {
          const content = readFileSync(configPath, 'utf-8');
          this.config = { ...this.config, ...JSON.parse(content) };
        } catch (error) {
          // Configuration loading is not critical, use logger instead of console
          // console.warn(`Failed to load config from ${configPath}:`, error);
        }
      }
    }
  }

  get<K extends keyof UserConfig>(key: K): UserConfig[K] {
    return this.config[key];
  }

  getAll(): UserConfig {
    return { ...this.config };
  }

  /**
   * Set a configuration value
   */
  set<K extends keyof UserConfig>(key: K, value: UserConfig[K]): void {
    this.config[key] = value;
  }

  /**
   * Get preferred editor
   */
  getPreferredEditor(): EditorType | undefined {
    return this.config.preferredEditor;
  }

  /**
   * Set preferred editor and persist to config file
   */
  setPreferredEditor(editor: EditorType | undefined): void {
    this.config.preferredEditor = editor;
    this.persistConfig();
  }

  /**
   * Persist current configuration to file
   */
  private persistConfig(): void {
    // Use the first config path as primary (user home directory)
    const configPath = join(homedir(), '.config', 'siada-ui', 'config.json');
    
    try {
      // Ensure directory exists
      const configDir = dirname(configPath);
      if (!existsSync(configDir)) {
        mkdirSync(configDir, { recursive: true });
      }

      // Write config
      writeFileSync(configPath, JSON.stringify(this.config, null, 2), 'utf-8');
    } catch (error) {
      // Configuration persistence is not critical
      console.warn(`Failed to persist config to ${configPath}:`, error);
    }
  }

  buildClientConfig(overrides: Partial<ClientConfig> = {}): ClientConfig {
    // Defaults to module mode (siada-agenthub in repo), not dependent on ~/.local/bin/siada-cli.
    // Can be overridden via ~/.config/siada-ui/config.json or CLI args.
    const defaultAgenthubPath = join(process.cwd(), '..', 'siada-agenthub');
    const defaultPythonPath = join(
      '/opt/homebrew/Caskroom/miniconda/base/envs/siada-agenthub',
      'bin',
      'python',
    );

    return {
      workingDir: overrides.workingDir || process.cwd(),
      // Only set model if explicitly provided, otherwise leave undefined to use agent_config.yaml
      model: overrides.model || this.config.model || undefined,
      // Only set temperature if explicitly provided, otherwise leave undefined to use agent_config.yaml
      temperature: overrides.temperature ?? this.config.temperature ?? undefined,
      // Only set maxTokens if explicitly provided, otherwise leave undefined to use agent_config.yaml
      maxTokens: overrides.maxTokens ?? this.config.maxTokens ?? undefined,
      // Only set thinking if explicitly provided, otherwise leave undefined to use agent_config.yaml
      thinking: overrides.thinking ?? this.config.thinking ?? undefined,
      // Only set reasoningEffort if explicitly provided, otherwise leave undefined to use agent_config.yaml
      reasoningEffort: overrides.reasoningEffort ?? undefined,
      // Only set parallelToolCalls if explicitly provided, otherwise leave undefined to use agent_config.yaml
      parallelToolCalls: overrides.parallelToolCalls ?? this.config.parallelToolCalls ?? undefined,
      // executable mode (fallback): only used when siadaPath is explicitly provided
      siadaPath: overrides.siadaPath || this.config.siada?.path,
      // module mode (default): python -m siada.entrypoint.siadahub
      pythonPath: overrides.pythonPath || this.config.siada?.pythonPath || defaultPythonPath,
      siadaModule: overrides.siadaModule || this.config.siada?.modulePath || defaultAgenthubPath,
      useModuleMode: overrides.useModuleMode ?? this.config.siada?.useModuleMode ?? true,
      acpMode: overrides.acpMode ?? this.config.siada?.acpMode ?? true,
      siadaArgs: overrides.siadaArgs || this.config.siada?.args || [],
      env: overrides.env || {},
    };
  }
}

export const configManager = new ConfigManager();
