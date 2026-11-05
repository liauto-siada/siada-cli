import { useSyncExternalStore } from 'react';
import { configManager } from '../utils/config.js';

export type UiLanguage = 'en' | 'zh-CN';
let language: UiLanguage = configManager.get('language') === 'zh-CN' ? 'zh-CN' : 'en';
const listeners = new Set<() => void>();
const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};
export const getUiLanguage = () => language;

/** Non-persistent updates support embedded UIs and deterministic tests. */
export function setUiLanguage(value: UiLanguage): void {
  if (language === value) return;
  language = value;
  for (const listener of listeners) listener();
}

export function saveUiLanguage(value: UiLanguage): void {
  configManager.setLanguage(value);
  setUiLanguage(value);
}

export function useUiLanguage(): UiLanguage {
  return useSyncExternalStore(subscribe, getUiLanguage, () => 'en');
}

/** Translate application-owned text; user and external content stays untouched. */
export function t(zh: string, en: string): string {
  return language === 'zh-CN' ? zh : en;
}

/** Read localized constants lazily, so module initialization never freezes a locale. */
export function bilingual<T extends object>(zh: T, en: T): T {
  return new Proxy(zh, {
    get(_target, key, receiver) {
      return Reflect.get(language === 'zh-CN' ? zh : en, key, receiver);
    },
  });
}