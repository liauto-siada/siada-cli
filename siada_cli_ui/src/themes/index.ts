/**
 * Theme registry
 *
 * Single entry point for switching the UI color theme at runtime. The theme
 * singletons (colors, githubTheme, markdownTheme) are mutated in place so
 * components that read them at render time pick up the new palette, and
 * subscribed components re-render via useThemeVersion().
 *
 * The active theme is pushed by the backend (banner_info at startup and the
 * ui/themeChanged notification after /theme); the UI never writes conf.yaml
 * itself.
 */

import { useSyncExternalStore } from 'react';
import { applyColorsTheme } from '../utils/colors.js';
import { applyInputTheme } from '../components/Input/theme.js';
import { applyMarkdownTheme } from '../components/markdown/theme.js';

export type ThemeName = 'dark' | 'light';

export function isThemeName(value: unknown): value is ThemeName {
  return value === 'dark' || value === 'light';
}

let activeTheme: ThemeName = 'dark';
let version = 0;
const listeners = new Set<() => void>();

export function getActiveTheme(): ThemeName {
  return activeTheme;
}

/**
 * Switch the active theme. No-op when the theme is already active.
 */
export function setActiveTheme(name: ThemeName): void {
  if (name === activeTheme) {
    return;
  }
  activeTheme = name;
  applyColorsTheme(name);
  applyInputTheme(name);
  applyMarkdownTheme(name);
  version += 1;
  for (const listener of listeners) {
    listener();
  }
}

export function subscribeTheme(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * React hook that re-renders the calling component on every theme change.
 * Needed because most components read theme singletons at render time and
 * React.memo blocks prop-driven re-renders.
 */
export function useThemeVersion(): number {
  return useSyncExternalStore(subscribeTheme, () => version, () => version);
}
