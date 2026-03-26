/**
 * Editor Utilities
 * Handles external editor detection, configuration, and launching
 */

import { execSync, spawnSync } from 'child_process';

/**
 * Supported editor types
 */
export type EditorType = 'vim' | 'vscode' | 'not_set';

/**
 * GUI editors that need --wait parameter
 */
export const GUI_EDITORS = ['vscode'] as const;
export type GuiEditorType = typeof GUI_EDITORS[number];

/**
 * Terminal editors that run synchronously
 */
export const TERMINAL_EDITORS = ['vim'] as const;
export type TerminalEditorType = typeof TERMINAL_EDITORS[number];

/**
 * GUI editors set for quick lookup
 */
const GUI_EDITORS_SET = new Set<EditorType>(GUI_EDITORS);

/**
 * Display names for editors
 */
export const EDITOR_DISPLAY_NAMES: Record<Exclude<EditorType, 'not_set'>, string> = {
  vscode: 'VS Code',
  vim: 'Vim',
};

/**
 * Editor command configuration per platform
 */
interface EditorCommands {
  win32: string[];
  default: string[];
}

/**
 * Command mappings for each editor
 */
const editorCommands: Record<Exclude<EditorType, 'not_set'>, EditorCommands> = {
  vscode: { win32: ['code.cmd'], default: ['code'] },
  vim: { win32: ['vim'], default: ['vim'] },
};

/**
 * Check if a command exists on the system
 */
function commandExists(cmd: string): boolean {
  try {
    execSync(
      process.platform === 'win32'
        ? `where.exe ${cmd}`
        : `command -v ${cmd}`,
      { stdio: 'ignore' }
    );
    return true;
  } catch {
    return false;
  }
}

/**
 * Check if an editor type is installed on the system
 */
export function checkHasEditorType(editor: Exclude<EditorType, 'not_set'>): boolean {
  const commandConfig = editorCommands[editor];
  const commands =
    process.platform === 'win32'
      ? commandConfig.win32
      : commandConfig.default;
  return commands.some((cmd) => commandExists(cmd));
}

/**
 * Get the command to launch an editor
 * Returns the first available command or the last one as fallback
 */
export function getEditorCommand(editor: Exclude<EditorType, 'not_set'>): string {
  const commandConfig = editorCommands[editor];
  const commands =
    process.platform === 'win32'
      ? commandConfig.win32
      : commandConfig.default;

  // Try to find an existing command
  const existingCommand = commands.slice(0, -1).find((cmd) => commandExists(cmd));
  
  // Return existing command or the last one as fallback
  return existingCommand || commands[commands.length - 1];
}

/**
 * Check if an editor is a GUI editor (needs --wait parameter)
 */
export function isGuiEditor(editor: EditorType): editor is GuiEditorType {
  return GUI_EDITORS_SET.has(editor);
}

/**
 * Get display name for an editor
 */
export function getEditorDisplayName(editor: EditorType): string {
  if (editor === 'not_set') {
    return 'None';
  }
  return EDITOR_DISPLAY_NAMES[editor];
}

/**
 * Launch an external editor with a file
 * @param editor - The editor type to use
 * @param filePath - Path to the file to edit
 * @param options - Launch options
 * @returns Object with status and error (if any)
 */
export function launchEditor(
  editor: Exclude<EditorType, 'not_set'>,
  filePath: string,
  options: {
    onExit?: () => void;
  } = {}
): { status: number | null; error?: Error } {
  const command = getEditorCommand(editor);
  const args = [filePath];

  // GUI editors need --wait to block until window closes
  if (isGuiEditor(editor)) {
    args.unshift('--wait');
  }

  try {
    const result = spawnSync(command, args, {
      stdio: 'inherit', // Inherit stdin/stdout/stderr for terminal editors
      shell: process.platform === 'win32',
    });

    if (options.onExit) {
      options.onExit();
    }

    if (result.error) {
      return { status: null, error: result.error };
    }

    return { status: result.status };
  } catch (error) {
    return { status: null, error: error as Error };
  }
}

/**
 * Get editor from environment variables
 * Follows Unix convention: $VISUAL > $EDITOR
 */
export function getEditorFromEnv(): string | undefined {
  return process.env['VISUAL'] || process.env['EDITOR'];
}

/**
 * Get default editor for the platform
 */
export function getDefaultEditor(): string {
  return process.platform === 'win32' ? 'notepad' : 'vi';
}

/**
 * Resolve the editor command with fallback chain
 * Priority: preferredEditor > $VISUAL > $EDITOR > platform default
 */
export function resolveEditorCommand(preferredEditor?: EditorType): {
  command: string;
  args: string[];
  source: 'preferred' | 'env' | 'default';
} {
  // 1. Try preferred editor
  if (preferredEditor && preferredEditor !== 'not_set') {
    if (checkHasEditorType(preferredEditor)) {
      const command = getEditorCommand(preferredEditor);
      const args: string[] = [];
      
      if (isGuiEditor(preferredEditor)) {
        args.push('--wait');
      }
      
      return { command, args, source: 'preferred' };
    }
  }

  // 2. Try environment variables
  const envEditor = getEditorFromEnv();
  if (envEditor) {
    return { command: envEditor, args: [], source: 'env' };
  }

  // 3. Fall back to platform default
  return { command: getDefaultEditor(), args: [], source: 'default' };
}
