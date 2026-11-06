/**
 * Configuration management
 */

import { readFileSync, existsSync, writeFileSync, mkdirSync, statSync, accessSync, constants as fsConstants } from 'fs';
import { join, dirname, delimiter } from 'path';
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
  language?: 'en' | 'zh-CN';
  shortcuts?: Record<string, string>;
  preferredEditor?: EditorType;
  statusbarItems?: string[];
  siada?: {
    path?: string;
    pythonPath?: string;
    modulePath?: string;
    useModuleMode?: boolean;
    acpMode?: boolean;
    args?: string[];
  };
}

const DEFAULT_STATUSBAR_ITEMS = [
  'model', 'balance', 'total_cost',
  'hit_rate', 'git_branch', 'workspace', 'cost_time', 'token_usage',
];
const userConfigDirectory = process.env.SIADA_UI_CONFIG_DIR || join(homedir(), '.siada-cli');

/** Verify launcher defaults without executing a shell or assuming a checkout. */
function isUsableExecutable(candidate: string): boolean {
  try {
    if (!statSync(candidate).isFile()) return false;
    accessSync(candidate, fsConstants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function pathDirectories(env: NodeJS.ProcessEnv): string[] {
  return (env.PATH ?? env.Path ?? '').split(delimiter).filter(Boolean);
}

function resolveVerifiedPython(candidate: string | undefined, env = process.env): string | undefined {
  if (!candidate) return undefined;
  if (candidate.includes('/') || candidate.includes('\\')) {
    return isUsableExecutable(candidate) ? candidate : undefined;
  }
  for (const directory of pathDirectories(env)) {
    const path = join(directory, candidate);
    if (isUsableExecutable(path)) return path;
  }
  return undefined;
}

function resolveDefaultPythonPath(env = process.env): string | undefined {
  const launcher = resolveVerifiedPython(env.SIADA_PYTHON_PATH, env);
  if (launcher) return launcher;
  const names = process.platform === 'win32'
    ? ['python3.exe', 'python.exe', 'python3', 'python'] : ['python3', 'python'];
  for (const name of names) {
    for (const directory of pathDirectories(env)) {
      const path = join(directory, name);
      if (isUsableExecutable(path)) return path;
    }
  }
  return undefined;
}

export class ConfigManager {
  private config: UserConfig = {};
  private configPaths = process.env.SIADA_UI_CONFIG_DIR ? [join(userConfigDirectory, 'ui-config.json')] : [
    join(homedir(), '.siadauirc'),
    join(userConfigDirectory, 'ui-config.json'),
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
   * Get status bar visible items
   */
  getStatusbarItems(): string[] {
    return this.config.statusbarItems || DEFAULT_STATUSBAR_ITEMS;
  }

  /**
   * Set status bar visible items and persist
   */
  setStatusbarItems(items: string[]): void {
    this.config.statusbarItems = items;
    this.persistConfig();
  }

  /** Persist UI language before acknowledging the switch. */
  setLanguage(language: 'en' | 'zh-CN'): void {
    const configPath = join(userConfigDirectory, 'ui-config.json');
    const saved = existsSync(configPath) ? JSON.parse(readFileSync(configPath, 'utf-8')) : {};
    mkdirSync(dirname(configPath), { recursive: true });
    writeFileSync(configPath, JSON.stringify({ ...saved, language }, null, 2), 'utf-8');
    this.config.language = language;
  }

  /**
   * Persist current configuration to file
   */
  private persistConfig(): void {
    // Use the siada-cli config directory
    const configPath = join(userConfigDirectory, 'ui-config.json');
    
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
    // Explicit settings precede verified launcher defaults and portable PATH lookup.
    const pythonPath = overrides.pythonPath || this.config.siada?.pythonPath || resolveDefaultPythonPath();
    const siadaModule = overrides.siadaModule || this.config.siada?.modulePath ||
      process.env.SIADA_MODULE_PATH || undefined;

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
      pythonPath,
      siadaModule,
      useModuleMode: Boolean(overrides.useModuleMode ?? this.config.siada?.useModuleMode ?? true),
      acpMode: overrides.acpMode ?? this.config.siada?.acpMode ?? true,
      siadaArgs: overrides.siadaArgs || this.config.siada?.args || [],
      env: overrides.env || {},
    };
  }
}

export const configManager = new ConfigManager();
