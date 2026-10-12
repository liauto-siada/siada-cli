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

/**
 * Environment variables injected by the installed launcher
 * (`siada.entrypoint.launch_ui_with_acp.UILauncher._setup_node_env`).  They
 * describe the interpreter / import root the launcher itself is running with,
 * so they are a better default than a path guessed from the cwd.
 */
const LAUNCHER_PYTHON_ENV = 'SIADA_PYTHON_PATH';
const LAUNCHER_MODULE_ENV = 'SIADA_MODULE_PATH';

/**
 * Portable interpreter names probed on PATH when neither CLI flags, nor user
 * config, nor the launcher provided a usable interpreter.  Machine-specific
 * paths (e.g. a developer's conda env) are never hard-coded in the public build.
 */
function portablePythonCandidates(platform: string = process.platform): string[] {
  return platform === 'win32'
    ? ['python3.exe', 'python.exe', 'python3', 'python']
    : ['python3', 'python'];
}

/** True when `candidate` exists and is an executable regular file. */
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
  // Windows exposes the variable as `Path`; Node keeps the original spelling.
  const raw = env.PATH ?? env.Path ?? '';
  return raw.split(delimiter).filter(Boolean);
}

/**
 * Verify an interpreter provided by the launcher: absolute paths must exist
 * and be executable, bare command names are resolved through PATH.  Returns
 * the resolved absolute path, or undefined when the value is unusable so the
 * caller can fall through to the next priority tier.
 */
function resolveVerifiedPython(
  candidate: string | undefined,
  env: NodeJS.ProcessEnv = process.env,
): string | undefined {
  if (!candidate) return undefined;
  if (candidate.includes('/') || candidate.includes('\\')) {
    return isUsableExecutable(candidate) ? candidate : undefined;
  }
  for (const dir of pathDirectories(env)) {
    const resolved = join(dir, candidate);
    if (isUsableExecutable(resolved)) return resolved;
  }
  return undefined;
}

/**
 * Find a portable interpreter on PATH.  Filesystem probing only — no shelling
 * out — so this stays cheap and side-effect free during CLI startup.
 */
function findPortablePython(env: NodeJS.ProcessEnv = process.env): string | undefined {
  const directories = pathDirectories(env);
  for (const name of portablePythonCandidates()) {
    for (const dir of directories) {
      const candidate = join(dir, name);
      if (isUsableExecutable(candidate)) return candidate;
    }
  }
  return undefined;
}

/**
 * Resolve the backend interpreter when nothing explicit (CLI flag or user
 * config) was provided: the verified launcher env first, then a portable
 * `python3` / `python` found on PATH.  Returns undefined when no interpreter
 * is available; the adapter then falls back to the `siada-cli` executable.
 */
function resolveDefaultPythonPath(env: NodeJS.ProcessEnv = process.env): string | undefined {
  return resolveVerifiedPython(env[LAUNCHER_PYTHON_ENV], env) ?? findPortablePython(env);
}

export class ConfigManager {
  private config: UserConfig = {};
  private configPaths = [
    join(homedir(), '.siadauirc'),
    join(homedir(), '.siada-cli', 'ui-config.json'),
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

  /**
   * Persist current configuration to file
   */
  private persistConfig(): void {
    // Use the siada-cli config directory
    const configPath = join(homedir(), '.siada-cli', 'ui-config.json');
    
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

  /**
   * Build the config used to spawn the Python backend.
   *
   * Python resolution priority (public/installed build):
   *   1. explicit overrides — CLI flags (`--python-path`) / programmatic callers
   *   2. user file config — ~/.siadauirc, ~/.siada-cli/ui-config.json
   *   3. verified launcher env — SIADA_PYTHON_PATH (must be executable)
   *   4. portable PATH lookup — python3 / python
   *
   * The installed bundle receives its interpreter, module/import root and mode
   * flags from siada.entrypoint.launch_ui_with_acp; nothing here is derived from
   * a source checkout.
   */
  buildClientConfig(overrides: Partial<ClientConfig> = {}): ClientConfig {
    const pythonPath =
      overrides.pythonPath ||
      this.config.siada?.pythonPath ||
      resolveDefaultPythonPath();

    // Import root for module mode. The installed launcher passes
    // `--siada-module` (the directory holding the installed `siada` package).
    // There is deliberately no cwd-relative default: `python -m
    // siada.entrypoint.siadahub` runs with cwd = workingDir (the user's
    // workspace) and an installed module needs no source checkout on PYTHONPATH.
    const siadaModule =
      overrides.siadaModule ||
      this.config.siada?.modulePath ||
      process.env[LAUNCHER_MODULE_ENV] ||
      undefined;

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
      // module mode: <pythonPath> -m siada.entrypoint.siadahub
      pythonPath,
      siadaModule,
      // Module mode stays the default; the adapter only takes it when both
      // pythonPath and siadaModule are present, otherwise it falls back to the
      // `siada-cli` executable.
      useModuleMode: Boolean(overrides.useModuleMode ?? this.config.siada?.useModuleMode ?? true),
      acpMode: overrides.acpMode ?? this.config.siada?.acpMode ?? true,
      siadaArgs: overrides.siadaArgs || this.config.siada?.args || [],
      env: overrides.env || {},
    };
  }
}

export const configManager = new ConfigManager();
