/**
 * Slash Command Service
 * Fetches and manages slash commands from siada-agenthub backend
 */

import type { CommandDefinition, CommandKind } from '../types/autocomplete.js';

export interface SlashCommandInfo {
  name: string;
  description: string;
  requiresSession?: boolean;
  kind?: CommandKind;
}

/**
 * Service for fetching slash commands from siada-agenthub
 */
export class SlashCommandService {
  private static instance: SlashCommandService | null = null;
  private commands: Map<string, CommandDefinition> = new Map();
  private initialized: boolean = false;

  private constructor() {}

  static getInstance(): SlashCommandService {
    if (!SlashCommandService.instance) {
      SlashCommandService.instance = new SlashCommandService();
    }
    return SlashCommandService.instance;
  }

  /**
   * Initialize and fetch available commands
   * Falls back to built-in commands if backend hasn't provided them yet
   */
  async initialize(): Promise<void> {
    if (this.initialized) {
      return;
    }

    // Initialize with fallback commands immediately so autocomplete works
    // even before backend sends the command list via ACP
    // this.initialized = true;
    await this.initializeWithFallback();
  }

  /**
   * Update commands from backend (called when receiving slash commands via ACP)
   */
  updateCommandsFromBackend(backendCommands: Array<{name: string, description: string}>): void {
    // Clear existing commands
    this.commands.clear();
    
    // Add commands from backend
    backendCommands.forEach(cmd => {
      this.commands.set(cmd.name, {
        name: cmd.name,
        description: cmd.description,
        requiresSession: false,  // Backend will handle session requirements
        kind: 'BUILTIN' as CommandKind,
        autoExecute: false,
      });
    });
    
    this.initialized = true;
  }

  /**
   * Initialize with fallback built-in commands (for backward compatibility)
   */
  async initializeWithFallback(): Promise<void> {
    if (this.initialized) {
      return;
    }

    // Fallback: define the built-in commands based on slash_commands.py
    const builtinCommands: SlashCommandInfo[] = [
      { name: 'status', description: 'Show the current status', requiresSession: true },
      { name: 'model', description: 'Switch to a different model (opens UI picker)', requiresSession: true },
      // { name: 'models', description: 'Search the list of available models', requiresSession: false }, // Removed: /model already provides this functionality
      { name: 'run', description: 'Run a shell command (alias: !)', requiresSession: true },
      { name: 'logout', description: 'Sign out and clear stored credentials', requiresSession: false },
      { name: 'exit', description: 'Exit the application', requiresSession: false },
      { name: 'quit', description: 'Exit the application', requiresSession: false },
      // { name: 'multiline-mode', description: 'Toggle multiline mode', requiresSession: false },
      { name: 'editor', description: 'Open an editor to write a prompt', requiresSession: false },
      { name: 'edit', description: 'Alias for /editor', requiresSession: false },
      { name: 'statusbar', description: 'Toggle status bar items visibility', requiresSession: false },
      { name: 'init', description: 'Analyze the project and create a tailored SIADA.md file', requiresSession: true },
      { name: 'context-file-refresh', description: 'Refresh SIADA.md and AGENTS.md context files and show content overview', requiresSession: true },
      { name: 'rule-init', description: 'Create an empty siada_rule.md file', requiresSession: true },
      { name: 'rule-show', description: 'Display combined hierarchical context content', requiresSession: true },
      { name: 'rule-refresh', description: 'Refresh hierarchical context content', requiresSession: true },
      { name: 'rule-list', description: 'List all loaded hierarchical context files', requiresSession: true },
      { name: 'rule-global-add', description: 'Add memory entry to global context file', requiresSession: true },
      { name: 'rule-status', description: 'Display current hierarchical context status', requiresSession: true },
      { name: 'mcp-server', description: 'List all MCP servers and their connection status', requiresSession: true },
      { name: 'mcp-list', description: 'List all MCP servers and their available tools', requiresSession: true },
      { name: 'compare', description: 'Compare files between working directory and checkpoint', requiresSession: true },
      { name: 'undo', description: 'Undo the target checkpoint', requiresSession: true },
      { name: 'restore', description: 'Restore files from a checkpoint', requiresSession: true },
      { name: 'clear', description: 'Start a new task session without previous conversation history', requiresSession: true },
      { name: 'lang', description: 'Switch language preference between English and Chinese', requiresSession: true },
      { name: 'pre-plan-mode', description: 'Toggle plan mode for tool execution', requiresSession: true },
      { name: 'issue-fix', description: 'Fix an issue from Siada Patch Review by issue ID', requiresSession: true },
      { name: 'help', description: 'Show help about commands', requiresSession: false },
      { name: 'plugin', description: 'Open plugin/skill manager (discover, install, disable skills)', requiresSession: true },
      { name: 'skill-list', description: 'List all available skills', requiresSession: true },
      { name: 'skill-reload', description: 'Reload skills (clear cache and rediscover)', requiresSession: true },
      { name: 'task-list', description: 'Show discovered pending tasks and select one to execute', requiresSession: true },
      { name: 'lark-auth', description: 'Authenticate with Lark MCP server using OAuth 2.0', requiresSession: true },
      { name: 'lark-status', description: 'Show Lark OAuth authentication status', requiresSession: true },
      { name: 'lark-refresh', description: 'Refresh Lark OAuth token', requiresSession: true },
      { name: 'memory', description: 'Enable or disable the memory subsystem (usage: /memory [enable|disable])', requiresSession: true },
    ];

    builtinCommands.forEach(cmd => {
      this.commands.set(cmd.name, {
        name: cmd.name,
        description: cmd.description,
        requiresSession: cmd.requiresSession,
        kind: cmd.kind || 'BUILTIN' as CommandKind,
        autoExecute: false,
      });
    });

    this.initialized = true;
  }

  /**
   * Get all available commands
   */
  async getCommands(): Promise<CommandDefinition[]> {
    if (!this.initialized) {
      await this.initialize();
    }
    return Array.from(this.commands.values());
  }

  /**
   * Get a specific command by name
   */
  async getCommand(name: string): Promise<CommandDefinition | undefined> {
    if (!this.initialized) {
      await this.initialize();
    }
    return this.commands.get(name);
  }

  /**
   * Search commands by pattern
   */
  async searchCommands(pattern: string): Promise<CommandDefinition[]> {
    if (!this.initialized) {
      await this.initialize();
    }
    
    const normalizedPattern = pattern.toLowerCase().replace(/^\//, '');
    if (!normalizedPattern) {
      return Array.from(this.commands.values());
    }

    return Array.from(this.commands.values()).filter(cmd => 
      cmd.name.toLowerCase().includes(normalizedPattern) ||
      cmd.aliases?.some(alias => alias.toLowerCase().includes(normalizedPattern))
    );
  }

  /**
   * Add custom command (from backend or MCP)
   */
  addCommand(command: CommandDefinition): void {
    this.commands.set(command.name, command);
  }

  /**
   * Clear all commands (for testing or reset)
   */
  clear(): void {
    this.commands.clear();
    this.initialized = false;
  }
}

// Export singleton instance
export const slashCommandService = SlashCommandService.getInstance();
