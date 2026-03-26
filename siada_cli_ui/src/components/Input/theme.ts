/**
 * GitHub Theme for Input Components
 * Based on GitHub Dark (dimmed) color scheme
 */

export const githubTheme = {
  // Text colors
  text: {
    primary: '#c9d1d9',     // Main text color
    secondary: '#8b949e',   // Secondary text (placeholder, dimmed)
    muted: '#484f58',       // More muted text
    inverse: '#ffffff',     // Inverse text (for selections)
  },
  
  // UI colors
  ui: {
    background: '#0d1117',  // Page background
    surface: '#161b22',     // Surface/card background
    border: '#30363d',      // Border color
    borderActive: '#58a6ff', // Active border (blue)
  },
  
  // Border colors
  border: {
    default: '#30363d',     // Default border color
    focused: '#58a6ff',     // Focused border color (blue)
    disabled: '#484f58',    // Disabled border color (gray) - for not ready state
  },
  
  // Semantic colors
  primary: '#58a6ff',       // Primary action (blue)
  success: '#3fb950',       // Success state (green)
  warning: '#d29922',       // Warning (yellow)
  danger: '#f85149',        // Error/danger (red)
  accent: '#f778ba',        // Accent color (pink)
  purple: '#a371f7',        // Purple accent
  
  // Input specific
  input: {
    prompt: '#58a6ff',      // > prompt symbol (blue)
    cursor: '#c9d1d9',      // Cursor color (use with inverse)
    placeholder: '#484f58', // Placeholder text (muted)
    text: '#c9d1d9',        // Input text
    selection: '#264f78',   // Selection background (blue dim)
    multilineIndent: '#30363d', // Indent guide for multi-line
  },
  
  // Suggestions/Autocomplete
  suggestions: {
    background: '#161b22',   // Suggestions panel background
    border: '#30363d',       // Suggestions panel border
    activeBg: '#1f6feb',     // Active item background (blue)
    activeText: '#ffffff',   // Active item text
    text: '#c9d1d9',         // Normal item text
    secondaryText: '#8b949e', // Secondary text in items
    match: '#58a6ff',        // Matched text highlight
    icon: '#8b949e',         // Icon color
  },
  
  // Status indicators
  status: {
    info: '#58a6ff',    // Info (blue)
    success: '#3fb950', // Success (green)
    warning: '#d29922', // Warning (yellow)
    error: '#f85149',   // Error (red)
  },
  
  // Global text settings
  textSettings: {
    useDimColor: true,  // Global switch for dimColor
  },
} as const;

export type GithubTheme = typeof githubTheme;

// Convenience function to get color with fallback
export const getThemeColor = (path: string, fallback: string = '#c9d1d9'): string => {
  const keys = path.split('.');
  let value: any = githubTheme;
  
  for (const key of keys) {
    if (value && typeof value === 'object' && key in value) {
      value = value[key];
    } else {
      return fallback;
    }
  }
  
  return typeof value === 'string' ? value : fallback;
};
