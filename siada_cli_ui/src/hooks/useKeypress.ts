/**
 * useKeypress Hook
 * 
 * Hook for subscribing to keyboard events from the custom input system.
 * 
 * This replaces Ink's useInput hook to avoid triggering macOS input method framework.
 */

import { useCallback, useEffect, useRef } from 'react';
import type { KeypressHandler, Key } from '../contexts/KeypressContext.js';
import { useKeypressContext } from '../contexts/KeypressContext.js';

export type { Key };

/**
 * Subscribe to keypress events
 * 
 * @param onKeypress - Callback function for each keypress
 * @param options - Configuration options
 * @param options.isActive - Whether the hook should actively listen (default: true)
 * 
 * @example
 * ```tsx
 * useKeypress((key) => {
 *   if (key.name === 'return') {
 *     handleSubmit();
 *   } else if (key.name === 'escape') {
 *     handleCancel();
 *   } else if (key.insertable) {
 *     handleInput(key.sequence);
 *   }
 * });
 * ```
 */
export function useKeypress(
  onKeypress: KeypressHandler,
  options: { isActive?: boolean } = {},
) {
  const { isActive = true } = options;
  const { subscribe, unsubscribe } = useKeypressContext();

  // Avoid re-subscribing on every render:
  // 1) hold latest handler in a ref
  // 2) use a stable wrapper that subscribes only once
  const handlerRef = useRef<KeypressHandler>(onKeypress);

  useEffect(() => {
    handlerRef.current = onKeypress;
  }, [onKeypress]);

  const stableHandler = useCallback<KeypressHandler>((key: Key) => {
    handlerRef.current(key);
  }, []);

  useEffect(() => {
    if (!isActive) return;

    subscribe(stableHandler);
    return () => {
      unsubscribe(stableHandler);
    };
  }, [isActive, subscribe, unsubscribe, stableHandler]);
}
