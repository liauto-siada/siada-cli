import { useEffect, useRef, useState } from 'react';
import type { Key } from '../contexts/KeypressContext.js';
import { CLIPBOARD_TIPS, INPUT_TIPS } from '../constants/tips.js';
import {
  canPasteOnRightClick,
  copyClipboardText,
  discardClipboardContent,
  readClipboardContent,
  type ClipboardContent,
} from '../utils/clipboard.js';

/** Middle paste uses the same clipboard and ownership rules as Ctrl+V. */
export function isClipboardPasteKey(key: Key): boolean {
  return ((key.ctrl || key.cmd) && key.name === 'v') ||
    (key.name === 'mousemiddle' && !key.ctrl && !key.cmd && !key.alt && !key.shift);
}

export function isRightClickPasteKey(key: Key): boolean {
  return key.name === 'mouseright' && !key.ctrl && !key.cmd && !key.alt && !key.shift;
}

/** Keep asynchronous clipboard results attached to the unchanged, active input. */
export function useClipboard({
  active,
  owner,
  onPaste,
}: {
  active: boolean;
  owner: string;
  onPaste: (content: ClipboardContent) => void;
}) {
  const [message, setMessage] = useState('');
  const generation = useRef(0);
  const busy = useRef(false);
  const latest = useRef({ active, owner, onPaste });
  latest.current = { active, owner, onPaste };

  useEffect(() => {
    generation.current++;
    setMessage('');
    return () => { generation.current++; };
  }, [active, owner]);

  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => setMessage(''), 5000);
    return () => clearTimeout(timer);
  }, [message]);

  function onKey(key: Key): void {
    if (['mousemove', 'mouserelease', 'selectioncopy', 'selectionclear'].includes(key.name)) return;
    // Repeated clipboard shortcuts must not launch overlapping reads or copies.
    if (busy.current && (isClipboardPasteKey(key) || isRightClickPasteKey(key) ||
      (key.ctrl && key.name === 'b'))) return;
    generation.current++;
    setMessage('');
  }

  async function run(operation: 'paste' | 'copy', text = '', includeImages = true): Promise<void> {
    if (busy.current || !latest.current.active) return;
    busy.current = true;
    if (operation === 'paste') setMessage(INPUT_TIPS.pasteStarted);
    const ticket = generation.current;
    const inputOwner = latest.current.owner;
    const current = () => ticket === generation.current &&
      latest.current.active && latest.current.owner === inputOwner;
    try {
      if (operation === 'paste') {
        const content = await readClipboardContent(includeImages);
        if (current()) {
          setMessage('');
          latest.current.onPaste(content);
        } else discardClipboardContent(content);
      } else {
        const result = await copyClipboardText(text);
        if (current()) setMessage(result.message);
      }
    } catch (error) {
      if (current()) setMessage(error instanceof Error ? error.message : CLIPBOARD_TIPS.operationFailed);
    } finally {
      busy.current = false;
    }
  }

  return {
    message,
    onKey,
    paste: (includeImages = true) => { void run('paste', '', includeImages); },
    pasteOnRightClick: () => {
      if (canPasteOnRightClick()) void run('paste', '', false);
    },
    copy: (text: string) => { void run('copy', text); },
  };
}