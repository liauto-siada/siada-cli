import { useLayoutEffect, useRef, useState } from 'react';
import type { Message } from '../types/index.js';
import { NativeHistoryBuffer, type NativeHistoryChunk } from '../utils/nativeHistory.js';

export function useNativeHistory(
  active: boolean, messages: Message[], session: string, loading: boolean,
  width: number, tailRows: number, ready = true,
) {
  const buffer = useRef(new NativeHistoryBuffer());
  const [chunks, setChunks] = useState<NativeHistoryChunk[]>([]);
  const [pending, setPending] = useState(messages);
  useLayoutEffect(() => {
    if (!active || !ready) return;
    const update = buffer.current.update(messages, session, loading, width, tailRows);
    if (update.appended.length) setChunks(previous => [...previous, ...update.appended]);
    setPending(update.pending);
  }, [active, messages, session, loading, width, tailRows, ready]);
  return { chunks, pending: active ? pending : messages };
}