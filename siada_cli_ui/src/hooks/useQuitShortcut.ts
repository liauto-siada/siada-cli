import { useCallback, useEffect, useRef, useState } from 'react';
import { useKeypress } from './useKeypress.js';
import { t } from '../i18n/index.js';

export const QUIT_SHORTCUT_TIMEOUT_MS = 1000;
export type CtrlCContext = 'main' | 'draft' | 'modal';

interface QuitShortcutOptions {
  running: boolean;
  onStop: () => void;
  onExit: () => void;
  active?: boolean;
}

/** Keep local input cancellation ahead of the time-bounded stop/exit shortcut. */
export function useQuitShortcut({ running, onStop, onExit, active = true }: QuitShortcutOptions) {
  const [notice, setNotice] = useState<string | null>(null);
  const expiresAt = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const exitRequested = useRef(false);

  const reset = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    expiresAt.current = 0;
    setNotice(null);
  }, []);

  useEffect(() => {
    if (!active) reset();
  }, [active, reset]);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
    expiresAt.current = 0;
  }, []);

  useKeypress(key => {
    // Pointer movement does not break a double press; editing and other shortcuts do.
    if (['mousemove', 'mouseclick', 'mouserelease', 'wheelup', 'wheeldown'].includes(key.name)) return;
    if (!(key.ctrl && key.name === 'c')) reset();
  });

  const onCtrlC = useCallback((context: CtrlCContext = 'main') => {
    if (exitRequested.current) return;
    if (!active || context === 'modal') {
      reset();
      return;
    }
    if (performance.now() < expiresAt.current) {
      exitRequested.current = true;
      reset();
      onExit();
      return;
    }
    if (timer.current) clearTimeout(timer.current);
    expiresAt.current = performance.now() + QUIT_SHORTCUT_TIMEOUT_MS;
    timer.current = setTimeout(reset, QUIT_SHORTCUT_TIMEOUT_MS);
    setNotice(context === 'draft' ? t('已清空输入 · 再按 Ctrl+C 退出', 'Input cleared · Ctrl+C again to exit') :
      running ? t('已停止 · 再按 Ctrl+C 退出', 'Stopped · Ctrl+C again to exit') : t('再按 Ctrl+C 退出', 'Ctrl+C again to exit'));
    if (context === 'main' && running) onStop();
  }, [active, onExit, onStop, reset, running]);

  return { onCtrlC, notice, reset };
}