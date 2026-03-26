/**
 * Terminal Detection Utility
 * 
 * Detects which terminal emulator is being used and provides
 * stability recommendations.
 */

export enum TerminalType {
  ITERM2 = 'iTerm2',
  TERMINAL_APP = 'Terminal.app',
  VSCODE = 'VS Code',
  WARP = 'Warp',
  KITTY = 'Kitty',
  ALACRITTY = 'Alacritty',
  HYPER = 'Hyper',
  UNKNOWN = 'Unknown',
}

export interface TerminalInfo {
  type: TerminalType;
  version?: string;
  isStable: boolean;
  warning?: string;
  recommendation?: string;
}

/**
 * Detect the current terminal emulator
 */
export function detectTerminal(): TerminalInfo {
  // Check TERM_PROGRAM environment variable (most reliable)
  const termProgram = process.env.TERM_PROGRAM;
  const termProgramVersion = process.env.TERM_PROGRAM_VERSION;
  
  // iTerm2
  if (termProgram === 'iTerm.app') {
    return {
      type: TerminalType.ITERM2,
      version: termProgramVersion,
      isStable: true,
    };
  }
  
  // Terminal.app (macOS built-in)
  if (termProgram === 'Apple_Terminal') {
    return {
      type: TerminalType.TERMINAL_APP,
      version: termProgramVersion,
      isStable: false,
      warning: '',
      recommendation: '',
    };
  }
  
  // VS Code
  if (termProgram === 'vscode' || process.env.TERM === 'xterm-256color' && process.env.VSCODE_PID) {
    return {
      type: TerminalType.VSCODE,
      version: termProgramVersion,
      isStable: true,
    };
  }
  
  // Warp
  if (termProgram === 'WarpTerminal') {
    return {
      type: TerminalType.WARP,
      version: termProgramVersion,
      isStable: true,
    };
  }
  
  // Kitty
  if (process.env.TERM === 'xterm-kitty' || process.env.KITTY_WINDOW_ID) {
    return {
      type: TerminalType.KITTY,
      isStable: true,
    };
  }
  
  // Alacritty
  if (process.env.ALACRITTY_SOCKET || process.env.ALACRITTY_LOG) {
    return {
      type: TerminalType.ALACRITTY,
      isStable: true,
    };
  }
  
  // Hyper
  if (termProgram === 'Hyper') {
    return {
      type: TerminalType.HYPER,
      version: termProgramVersion,
      isStable: true,
    };
  }
  
  // Unknown terminal
  return {
    type: TerminalType.UNKNOWN,
    isStable: true, // Assume stable unless proven otherwise
  };
}

/**
 * Check if Terminal.app input method editing should be disabled
 */
export function shouldDisableIME(): boolean {
  const terminal = detectTerminal();
  return terminal.type === TerminalType.TERMINAL_APP;
}

/**
 * Print terminal stability warning if needed
 */
export function printTerminalWarning(): void {
  const terminal = detectTerminal();
  
  if (!terminal.isStable && terminal.warning) {
    console.warn('\n⚠️  Terminal Stability Warning:');
    console.warn(`   ${terminal.warning}`);
    
    if (terminal.recommendation) {
      console.warn(`   💡 ${terminal.recommendation}`);
    }
    
    console.warn('');
  }
}

/**
 * Get terminal info as a formatted string
 */
export function getTerminalInfoString(): string {
  const terminal = detectTerminal();
  const parts = [`Terminal: ${terminal.type}`];
  
  if (terminal.version) {
    parts.push(`v${terminal.version}`);
  }
  
  parts.push(terminal.isStable ? '✅ Stable' : '⚠️  Unstable');
  
  return parts.join(' | ');
}

/**
 * Instructions for disabling Terminal.app IME
 */
export const TERMINAL_APP_IME_FIX = `
To improve Terminal.app stability with input methods:

1. Disable Input Method Editing:
   defaults write com.apple.Terminal UseInputMethodEditing -bool NO
   killall Terminal

2. To restore default behavior:
   defaults delete com.apple.Terminal UseInputMethodEditing
   killall Terminal

3. Or switch to iTerm2 (recommended):
   brew install --cask iterm2
`;
