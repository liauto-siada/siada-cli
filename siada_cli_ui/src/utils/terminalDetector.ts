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
 * Whether the terminal supports DEC mode 2026 (synchronized output).
 *
 * When supported, wrapping a frame's writes in BSU (`\x1b[?2026h`) / ESU
 * (`\x1b[?2026l`) makes erase+repaint atomic: the terminal keeps showing the
 * old frame until ESU arrives, so no intermediate blank/partial frame is ever
 * painted. This is the same anti-flicker mechanism used by claude-code's ink
 * fork (src/ink/terminal.ts `isSynchronizedOutputSupported`).
 */
export function isSynchronizedOutputSupported(): boolean {
  // Explicit escape hatch / debug override
  if (process.env.SIADA_SYNC_OUTPUT === '0') return false;
  if (process.env.SIADA_SYNC_OUTPUT === '1') return true;

  // Only meaningful on a TTY; never inject into piped/redirected output
  if (!process.stdout.isTTY) return false;

  // tmux parses and chunks every byte but doesn't implement DEC 2026;
  // BSU/ESU pass through with atomicity already broken. Skip.
  if (process.env.TMUX) return false;

  const termProgram = process.env.TERM_PROGRAM;
  const term = process.env.TERM;

  // Terminals with known DEC 2026 support
  if (
    termProgram === 'iTerm.app' ||
    termProgram === 'WezTerm' ||
    termProgram === 'WarpTerminal' ||
    termProgram === 'ghostty' ||
    termProgram === 'vscode' ||
    termProgram === 'alacritty'
  ) {
    return true;
  }

  // kitty sets TERM=xterm-kitty or KITTY_WINDOW_ID
  if (term?.includes('kitty') || process.env.KITTY_WINDOW_ID) return true;

  // Ghostty may set TERM=xterm-ghostty without TERM_PROGRAM
  if (term === 'xterm-ghostty') return true;

  // foot sets TERM=foot or TERM=foot-extra
  if (term?.startsWith('foot')) return true;

  // Alacritty may set TERM containing 'alacritty'
  if (term?.includes('alacritty')) return true;

  // Zed uses the alacritty_terminal crate which supports DEC 2026
  if (process.env.ZED_TERM) return true;

  // Windows Terminal
  if (process.env.WT_SESSION) return true;

  // VTE-based terminals (GNOME Terminal, Tilix, etc.) since VTE 0.68
  const vteVersion = parseInt(process.env.VTE_VERSION ?? '', 10);
  if (!Number.isNaN(vteVersion) && vteVersion >= 6800) return true;

  return false;
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
