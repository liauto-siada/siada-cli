/**
 * Keypress Context - Custom Input Processing
 * 
 * This module implements a custom keyboard input processing system
 * that bypasses macOS input method framework (HIToolbox/IMKInputSession).
 * 
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
} from 'react';
import { useStdin } from '@jrichman/ink';
import { logger } from '../utils/logger.js';

// Timeouts for buffering sequences
export const ESC_TIMEOUT = 50;           // ESC key disambiguation timeout
export const PASTE_TIMEOUT = 5_000;      // Paste operation timeout (reduced from 30s to 5s)
export const BACKSLASH_ENTER_TIMEOUT = 5; // Backslash + Enter timeout
export const FAST_RETURN_TIMEOUT = 30;   // Fast return key timeout

// Special characters
const ESC = '\x1b'; // Escape character

// Focus reporting sequences
const FOCUS_IN = '\x1b[I';
const FOCUS_OUT = '\x1b[O';

// Mouse event detection
const SGR_MOUSE_REGEX = /^\x1b\[<(\d+);(\d+);(\d+)([mM])/;
const X11_MOUSE_REGEX = /^\x1b\[M([\s\S]{3})/;

/**
 * Key information structure
 * 
 * Key interface for keyboard input events
 */
export interface Key {
  /** Key name (e.g., 'a', 'return', 'up', 'backspace') */
  name: string;
  /** Shift key pressed */
  shift: boolean;
  /** Alt/Option key pressed (Meta key on macOS) */
  alt: boolean;
  /** Ctrl key pressed */
  ctrl: boolean;
  /** Command/Windows/Super key pressed */
  cmd: boolean;
  /** Can this key be inserted as text */
  insertable: boolean;
  /** Raw sequence received */
  sequence: string;
}

export type KeypressHandler = (key: Key) => void;

/**
 * ANSI escape sequence to key info mapping
 */
const KEY_INFO_MAP: Record<
  string,
  { name: string; shift?: boolean; ctrl?: boolean; alt?: boolean }
> = {
  '[200~': { name: 'paste-start' },
  '[201~': { name: 'paste-end' },
  '[[A': { name: 'f1' },
  '[[B': { name: 'f2' },
  '[[C': { name: 'f3' },
  '[[D': { name: 'f4' },
  '[[E': { name: 'f5' },
  '[11~': { name: 'f1' },
  '[12~': { name: 'f2' },
  '[13~': { name: 'f3' },
  '[14~': { name: 'f4' },
  '[15~': { name: 'f5' },
  '[17~': { name: 'f6' },
  '[18~': { name: 'f7' },
  '[19~': { name: 'f8' },
  '[20~': { name: 'f9' },
  '[21~': { name: 'f10' },
  '[23~': { name: 'f11' },
  '[24~': { name: 'f12' },
  '[1~': { name: 'home' },
  '[2~': { name: 'insert' },
  '[3~': { name: 'delete' },
  '[4~': { name: 'end' },
  '[5~': { name: 'pageup' },
  '[6~': { name: 'pagedown' },
  '[7~': { name: 'home' },
  '[8~': { name: 'end' },
  '[A': { name: 'up' },
  '[B': { name: 'down' },
  '[C': { name: 'right' },
  '[D': { name: 'left' },
  '[E': { name: 'clear' },
  '[F': { name: 'end' },
  '[H': { name: 'home' },
  'OA': { name: 'up' },
  'OB': { name: 'down' },
  'OC': { name: 'right' },
  'OD': { name: 'left' },
  'OE': { name: 'clear' },
  'OF': { name: 'end' },
  'OH': { name: 'home' },
  'OP': { name: 'f1' },
  'OQ': { name: 'f2' },
  'OR': { name: 'f3' },
  'OS': { name: 'f4' },
  '[9u': { name: 'tab' },
  '[13u': { name: 'return' },
  '[27u': { name: 'escape' },
  '[127u': { name: 'backspace' },
  '[57414u': { name: 'return' },
  // CSI u mode with modifiers (for Shift+Enter and Alt+Enter support)
  '[13;2u': { name: 'return', shift: true },  // Shift+Enter
  '[13;3u': { name: 'return', alt: true },    // Alt+Enter (Option+Enter on Mac)
  '[13;5u': { name: 'return', ctrl: true },   // Ctrl+Enter
  '[a': { name: 'up', shift: true },
  '[b': { name: 'down', shift: true },
  '[c': { name: 'right', shift: true },
  '[d': { name: 'left', shift: true },
  '[e': { name: 'clear', shift: true },
  '[2$': { name: 'insert', shift: true },
  '[3$': { name: 'delete', shift: true },
  '[5$': { name: 'pageup', shift: true },
  '[6$': { name: 'pagedown', shift: true },
  '[7$': { name: 'home', shift: true },
  '[8$': { name: 'end', shift: true },
  '[Z': { name: 'tab', shift: true },
  'Oa': { name: 'up', ctrl: true },
  'Ob': { name: 'down', ctrl: true },
  'Oc': { name: 'right', ctrl: true },
  'Od': { name: 'left', ctrl: true },
  'Oe': { name: 'clear', ctrl: true },
  '[2^': { name: 'insert', ctrl: true },
  '[3^': { name: 'delete', ctrl: true },
  '[5^': { name: 'pageup', ctrl: true },
  '[6^': { name: 'pagedown', ctrl: true },
  '[7^': { name: 'home', ctrl: true },
  '[8^': { name: 'end', ctrl: true },
};

/**
 * Mac Option key character mapping
 */
const MAC_ALT_KEY_CHARACTER_MAP: Record<string, string> = {
  '\u222B': 'b',
  '\u0192': 'f',
  '\u00B5': 'm',
};

const kUTF16SurrogateThreshold = 0x10000;
function charLengthAt(str: string, i: number): number {
  if (str.length <= i) return 1;
  const code = str.codePointAt(i);
  return code !== undefined && code >= kUTF16SurrogateThreshold ? 2 : 1;
}

/**
 * Check if Kitty keyboard protocol is enabled
 * Kitty protocol provides enhanced keyboard handling in modern terminals
 */
function isKittyProtocolEnabled(): boolean {
  // Check if running in Kitty terminal
  const term = process.env.TERM;
  const termProgram = process.env.TERM_PROGRAM;
  
  // Kitty terminal sets TERM to xterm-kitty
  if (term && term.includes('kitty')) {
    return true;
  }
  
  // Some terminals may set TERM_PROGRAM
  if (termProgram && termProgram.toLowerCase().includes('kitty')) {
    return true;
  }
  
  // Default to false for safety (enable bufferFastReturn for most terminals)
  return false;
}

/**
 * Parse mouse event from sequence
 * Returns true if the sequence is a mouse event (to be filtered out)
 */
function parseMouseEvent(sequence: string): boolean {
  // Check for SGR mouse mode: ESC[<Cb;Cx;CyM or ESC[<Cb;Cx;Cym
  if (SGR_MOUSE_REGEX.test(sequence)) {
    return true;
  }
  
  // Check for X11 mouse mode: ESC[Mcxy (3 bytes after M)
  if (X11_MOUSE_REGEX.test(sequence)) {
    return true;
  }
  
  return false;
}

/**
 * Filter out non-keyboard events (mouse and focus events)
 */
function nonKeyboardEventFilter(
  keypressHandler: KeypressHandler,
): KeypressHandler {
  return (key: Key) => {
    if (
      !parseMouseEvent(key.sequence) &&
      key.sequence !== FOCUS_IN &&
      key.sequence !== FOCUS_OUT
    ) {
      keypressHandler(key);
    }
  };
}

/**
 * Converts return keys pressed quickly after other keys into plain
 * insertable return characters.
 *
 * This is to accommodate older terminals that paste text without bracketing.
 */
function bufferFastReturn(keypressHandler: KeypressHandler): KeypressHandler {
  let lastKeyTime = 0;
  return (key: Key) => {
    const now = Date.now();
    if (key.name === 'return' && now - lastKeyTime <= FAST_RETURN_TIMEOUT) {
      keypressHandler({
        ...key,
        name: 'return',
        shift: true, // to make it a newline, not a submission
        alt: false,
        ctrl: false,
        cmd: false,
        sequence: '\r',
        insertable: true,
      });
    } else {
      keypressHandler(key);
    }
    lastKeyTime = now;
  };
}

/**
 * Core ANSI parser generator
 */
function* emitKeys(
  keypressHandler: KeypressHandler,
): Generator<void, void, string> {
  while (true) {
    let ch = yield;
    let sequence = ch;
    let escaped = false;
    let name: string | undefined = undefined;
    let ctrl = false;
    let alt = false;
    let cmd = false;
    let shift = false;
    let code: string | undefined = undefined;
    let insertable = false;

    if (ch === ESC) {
      escaped = true;
      ch = yield;
      sequence += ch;
      if (ch === ESC) {
        ch = yield;
        sequence += ch;
      }
    }

    if (escaped && (ch === 'O' || ch === '[' || ch === ']')) {
      // ANSI escape sequence
      code = ch;
      let modifier = 0;

      if (ch === ']') {
        // OSC sequence
        // ESC ] <params> ; <data> BEL
        // ESC ] <params> ; <data> ESC \
        let buffer = '';

        // Read until BEL, `ESC \`, or timeout (empty string)
        while (true) {
          const next = yield;
          if (next === '' || next === '\u0007') {
            break;
          } else if (next === ESC) {
            const afterEsc = yield;
            if (afterEsc === '' || afterEsc === '\\') {
              break;
            }
            buffer += next + afterEsc;
            continue;
          }
          buffer += next;
        }

        // Check for OSC 52 (Clipboard) response
        // Format: 52;c;<base64> or 52;p;<base64>
        const match = /^52;[cp];(.*)$/.exec(buffer);
        if (match) {
          try {
            const base64Data = match[1];
            const decoded = Buffer.from(base64Data, 'base64').toString('utf-8');
            keypressHandler({
              name: 'paste',
              shift: false,
              alt: false,
              ctrl: false,
              cmd: false,
              insertable: true,
              sequence: decoded,
            });
          } catch (_e) {
            logger.warn('Failed to decode OSC 52 clipboard data', {
              component: 'KeypressContext',
              operation: 'osc52_decode_error',
            });
          }
        }

        continue; // resume main loop
      } else if (ch === 'O') {
        ch = yield;
        sequence += ch;
        if (ch >= '0' && ch <= '9') {
          modifier = parseInt(ch, 10) - 1;
          ch = yield;
          sequence += ch;
        }
        code += ch;
      } else if (ch === '[') {
        ch = yield;
        sequence += ch;
        if (ch === '[') {
          code += ch;
          ch = yield;
          sequence += ch;
        }

        const cmdStart = sequence.length - 1;
        while (ch >= '0' && ch <= '9') {
          ch = yield;
          sequence += ch;
        }

        if (ch === ';') {
          while (ch === ';') {
            ch = yield;
            sequence += ch;
            while (ch >= '0' && ch <= '9') {
              ch = yield;
              sequence += ch;
            }
          }
        } else if (ch === '<') {
          // SGR mouse mode
          ch = yield;
          sequence += ch;
          // Don't skip on empty string here to avoid timeouts on slow events.
          while (ch === '' || ch === ';' || (ch >= '0' && ch <= '9')) {
            ch = yield;
            sequence += ch;
          }
        } else if (ch === 'M') {
          // X11 mouse mode
          // three characters after 'M'
          ch = yield;
          sequence += ch;
          ch = yield;
          sequence += ch;
          ch = yield;
          sequence += ch;
        }

        const cmd = sequence.slice(cmdStart);
        let match;

        if ((match = /^(\d+)(?:;(\d+))?(?:;(\d+))?([~^$u])$/.exec(cmd))) {
          if (match[1] === '27' && match[3] && match[4] === '~') {
            code += match[3] + 'u';
            modifier = parseInt(match[2] ?? '1', 10) - 1;
          } else {
            code += match[1] + match[4];
            modifier = parseInt(match[2] ?? '1', 10) - 1;
          }
        } else if ((match = /^(\d+)?(?:;(\d+))?([A-Za-z])$/.exec(cmd))) {
          code += match[3];
          modifier = parseInt(match[2] ?? match[1] ?? '1', 10) - 1;
        } else {
          code += cmd;
        }
      }

      ctrl = !!(modifier & 4);
      alt = !!(modifier & 2);
      cmd = !!(modifier & 8);
      shift = !!(modifier & 1);

      const keyInfo = KEY_INFO_MAP[code];
      if (keyInfo) {
        name = keyInfo.name;
        if (keyInfo.shift) shift = true;
        if (keyInfo.ctrl) ctrl = true;
        if (keyInfo.alt) alt = true;
      } else {
        name = 'undefined';
        if ((ctrl || alt) && (code.endsWith('u') || code.endsWith('~'))) {
          const codeNumber = parseInt(code.slice(1, -1), 10);
          if (
            codeNumber >= 'a'.charCodeAt(0) &&
            codeNumber <= 'z'.charCodeAt(0)
          ) {
            name = String.fromCharCode(codeNumber);
          }
        }
      }
    } else if (ch === '\r') {
      name = 'return';
      alt = escaped;
    } else if (ch === '\n') {
      // Ctrl+J sends \x0a (line feed), which should be treated as ctrl+j for newline insertion
      // Regular Enter key sends \r or \r\n, not just \n
      // So if we receive just \n without escape, it's likely Ctrl+J
      if (!escaped) {
        name = 'j';
        ctrl = true;
        logger.info('🔥 Ctrl+J detected (line feed)', {
          component: 'KeypressContext',
          operation: 'parse_ctrl_j',
          charCode: ch.charCodeAt(0),
          hexCode: '\\x0a',
          parsedName: 'j',
          ctrl: true,
        });
      } else {
        name = 'enter';
        alt = escaped;
      }
    } else if (ch === '\t') {
      name = 'tab';
      alt = escaped;
    } else if (ch === '\b' || ch === '\x7f') {
      name = 'backspace';
      alt = escaped;
    } else if (ch === ESC) {
      name = 'escape';
      alt = escaped;
    } else if (ch === ' ') {
      name = 'space';
      alt = escaped;
      insertable = true;
    } else if (!escaped && ch <= '\x1a') {
      name = String.fromCharCode(ch.charCodeAt(0) + 'a'.charCodeAt(0) - 1);
      ctrl = true;
      
      // 🔥 INFO: Log control character parsing (especially Ctrl+C which is \x03)
      logger.info('🔥 Control character parsed', {
        component: 'KeypressContext',
        operation: 'parse_control_char',
        charCode: ch.charCodeAt(0),
        hexCode: '\\x' + ch.charCodeAt(0).toString(16).padStart(2, '0'),
        parsedName: name,
        ctrl: true,
      });
    } else if (/^[0-9A-Za-z]$/.exec(ch) !== null) {
      name = ch.toLowerCase();
      shift = /^[A-Z]$/.exec(ch) !== null;
      alt = escaped;
      insertable = true;
    } else if (MAC_ALT_KEY_CHARACTER_MAP[ch] && process.platform === 'darwin') {
      name = MAC_ALT_KEY_CHARACTER_MAP[ch];
      alt = true;
    } else if (sequence === `${ESC}${ESC}`) {
      name = 'escape';
      alt = true;
      keypressHandler({
        name: 'escape',
        ctrl,
        alt,
        cmd,
        shift,
        insertable: false,
        sequence: ESC,
      });
    } else if (escaped) {
      name = ch.length ? undefined : 'escape';
      alt = true;
    } else {
      insertable = true;
    }

    if (
      (sequence.length !== 0 && (name !== undefined || escaped)) ||
      charLengthAt(sequence, 0) === sequence.length
    ) {
      keypressHandler({
        name: name || '',
        ctrl,
        alt,
        cmd,
        shift,
        insertable,
        sequence,
      });
    }
  }
}

function createDataListener(keypressHandler: KeypressHandler) {
  const parser = emitKeys(keypressHandler);
  parser.next();

  let timeoutId: NodeJS.Timeout;
  return (data: string) => {
    clearTimeout(timeoutId);
    for (const char of data) {
      parser.next(char);
    }
    if (data.length !== 0) {
      timeoutId = setTimeout(() => parser.next(''), ESC_TIMEOUT);
    }
  };
}

/**
 * Buffers paste events between paste-start and paste-end sequences.
 * Will flush the buffer if no data is received for PASTE_TIMEOUT ms or
 * when a null key is received.
 */
function bufferPaste(keypressHandler: KeypressHandler): KeypressHandler {
  const bufferer = (function* (): Generator<void, void, Key | null> {
    while (true) {
      let key = yield;

      if (key === null) {
        continue;
      } else if (key.name !== 'paste-start') {
        keypressHandler(key);
        continue;
      }

      let buffer = '';
      while (true) {
        const timeoutId = setTimeout(() => bufferer.next(null), PASTE_TIMEOUT);
        key = yield;
        clearTimeout(timeoutId);

        if (key === null) {
          // Paste timeout occurred
          logger.warn('Paste operation timed out', {
            component: 'KeypressContext',
            operation: 'paste_timeout',
            timeout: PASTE_TIMEOUT,
            bufferLength: buffer.length,
          });
          break;
        }

        if (key.name === 'paste-end') {
          break;
        }
        buffer += key.sequence;
      }

      if (buffer.length > 0) {
        // Remove trailing newlines to prevent accidental submission
        const cleanedBuffer = buffer.replace(/[\r\n]+$/, '');
        
        if (cleanedBuffer.length > 0) {
          keypressHandler({
            name: 'paste',
            shift: false,
            alt: false,
            ctrl: false,
            cmd: false,
            insertable: true,
            sequence: cleanedBuffer,
          });
        }
      }
    }
  })();
  bufferer.next(); // prime the generator so it starts listening.

  return (key: Key) => bufferer.next(key);
}

/**
 * Buffers "/" keys to see if they are followed return.
 * Will flush the buffer if no data is received for BACKSLASH_ENTER_TIMEOUT ms
 * or when a null key is received.
 */
function bufferBackslashEnter(
  keypressHandler: KeypressHandler,
): KeypressHandler {
  const bufferer = (function* (): Generator<void, void, Key | null> {
    while (true) {
      const key = yield;

      if (key == null) {
        continue;
      } else if (key.sequence !== '\\') {
        keypressHandler(key);
        continue;
      }

      const timeoutId = setTimeout(
        () => bufferer.next(null),
        BACKSLASH_ENTER_TIMEOUT,
      );
      const nextKey = yield;
      clearTimeout(timeoutId);

      if (nextKey === null) {
        keypressHandler(key);
      } else if (nextKey.name === 'return') {
        keypressHandler({
          ...nextKey,
          shift: true,
          sequence: '\r', // Corrected escaping for newline
        });
      } else {
        keypressHandler(key);
        keypressHandler(nextKey);
      }
    }
  })();
  bufferer.next(); // prime the generator so it starts listening.

  return (key: Key) => bufferer.next(key);
}

interface KeypressContextValue {
  subscribe: (handler: KeypressHandler) => void;
  unsubscribe: (handler: KeypressHandler) => void;
}

const KeypressContext = createContext<KeypressContextValue | undefined>(
  undefined,
);

export function useKeypressContext() {
  const context = useContext(KeypressContext);
  if (!context) {
    throw new Error(
      'useKeypressContext must be used within a KeypressProvider',
    );
  }
  return context;
}

/**
 * useKeypress - Subscribe to keypress events (enhanced version)
 * 
 * A React Hook-idiomatic interface that handles subscribe/unsubscribe automatically.
 * 
 * @example
 * ```typescript
 * useKeypress((key) => {
 *   if (key.insertable && key.sequence) {
 *     buffer.insert(key.sequence);
 *   }
 * }, { isActive: focus && !disabled });
 * ```
 * 
 * @param handler - Keypress event handler function
 * @param options - Configuration options
 * @param options.isActive - Whether the subscription is active (default: true)
 */
export function useKeypress(
  handler: KeypressHandler,
  options: { isActive?: boolean } = {}
): void {
  const context = useContext(KeypressContext);
  const { isActive = true } = options;
  
  // Use ref to hold the latest handler, avoiding repeated subscribe/unsubscribe
  const handlerRef = useRef(handler);
  
  // Update handler ref without re-subscribing
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);
  
  useEffect(() => {
    if (!context) {
      console.warn('[useKeypress] KeypressProvider not found in component tree');
      return;
    }
    
    if (!isActive) {
      return;
    }
    
    // Wrapper always calls the latest handler ref
    const wrappedHandler = (key: Key) => {
      handlerRef.current(key);
    };
    
    // Subscribe to keypress events
    context.subscribe(wrappedHandler);
    
    // Unsubscribe on unmount or when isActive becomes false
    return () => {
      context.unsubscribe(wrappedHandler);
    };
  }, [context, isActive]);
}

export function KeypressProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { stdin, setRawMode } = useStdin();

  const subscribers = useRef<Set<KeypressHandler>>(new Set()).current;
  
  const subscribe = useCallback(
    (handler: KeypressHandler) => subscribers.add(handler),
    [subscribers],
  );
  
  const unsubscribe = useCallback(
    (handler: KeypressHandler) => subscribers.delete(handler),
    [subscribers],
  );
  
  const broadcast = useCallback(
    (key: Key) => {
      // 🔥 INFO: Log all broadcast events (especially Ctrl+C)
      logger.info('🔥 Broadcasting key event', {
        component: 'KeypressContext',
        operation: 'broadcast',
        key: {
          name: key.name,
          ctrl: key.ctrl,
          alt: key.alt,
          cmd: key.cmd,
          shift: key.shift,
          sequence: JSON.stringify(key.sequence),
        },
        subscriberCount: subscribers.size,
      });
      
      subscribers.forEach((handler) => handler(key));
    },
    [subscribers],
  );

  useEffect(() => {
    const wasRaw = stdin.isRaw;
    
    if (wasRaw === false) {
      setRawMode(true);
    }

    // Build the processing chain (order matters!)
    // 1. First filter out non-keyboard events (mouse, focus)
    let processor = nonKeyboardEventFilter(broadcast);
    
    // 2. Then handle fast return keys (for terminals without paste bracketing)
    // Skip this for Kitty terminal which has better paste support
    if (!isKittyProtocolEnabled()) {
      processor = bufferFastReturn(processor);
    }
    
    // 3. Then handle backslash+enter sequences
    processor = bufferBackslashEnter(processor);
    
    // 4. Then handle paste bracketing
    processor = bufferPaste(processor);
    
    // 5. Finally create the data listener that feeds the chain
    const dataListener = createDataListener(processor);

    /**
     * Use process.stdin directly instead of Ink's stdin
     * 
     * Reason: Ink's stdin may be locked in paused mode on Ubuntu/Linux,
     * preventing reliable input handling. Using process.stdin directly
     * ensures consistent behavior across all platforms.
     */
    
    logger.info('🔥 Using process.stdin directly', {
      component: 'KeypressContext',
      operation: 'use_process_stdin',
      reason: 'Bypass Ink stdin paused mode issue on Ubuntu/Linux',
      inkStdinFlowing: stdin.readableFlowing,
      processStdinFlowing: process.stdin.readableFlowing,
    });
    
    // Configure process.stdin for raw mode input when available.
    // In some non-interactive/dev environments process.stdin exists but does not
    // expose setRawMode(), which would otherwise crash the whole UI on mount.
    const canSetProcessRawMode = typeof (process.stdin as NodeJS.ReadStream).setRawMode === 'function';
    if (!process.stdin.isRaw && canSetProcessRawMode) {
      process.stdin.setRawMode(true);
      logger.info('🔥 Set process.stdin to raw mode', {
        component: 'KeypressContext',
        operation: 'set_raw_mode',
      });
    } else if (!canSetProcessRawMode) {
      logger.warn('process.stdin.setRawMode is unavailable; using existing stdin mode', {
        component: 'KeypressContext',
        operation: 'set_raw_mode_unavailable',
        inkStdinIsRaw: stdin.isRaw,
        processStdinIsTTY: process.stdin.isTTY,
      });
    }
    
    // Set encoding and ensure flowing mode
    process.stdin.setEncoding('utf8');
    process.stdin.resume();
    
    // Enable Bracketed Paste Mode
    // When enabled, the terminal wraps pasted text with ESC[200~ ... ESC[201~
    // This allows bufferPaste() to detect and batch the entire paste as one event
    // instead of processing each character individually (which causes freeze on large pastes)
    if (process.stdout.isTTY) {
      process.stdout.write('\x1b[?2004h'); // Enable bracketed paste mode
      logger.info('Bracketed paste mode enabled', {
        component: 'KeypressContext',
        operation: 'enable_bracketed_paste',
      });
    }
    
    logger.info('🔥 Process.stdin configured', {
      component: 'KeypressContext',
      operation: 'configure_process_stdin',
      encoding: 'utf8',
      flowingAfter: process.stdin.readableFlowing,
      isRaw: process.stdin.isRaw,
    });
    
    // Register data event listener
    process.stdin.on('data', (chunk: Buffer | string) => {
      const data = typeof chunk === 'string' ? chunk : chunk.toString('utf8');
      
      // Log every input received for debugging
      logger.info('🔥 Process.stdin data received', {
        component: 'KeypressContext',
        operation: 'process_stdin_data',
        chunk: JSON.stringify(data),
        chunkLength: data.length,
        hexDump: Array.from(data).map(c => '\\x' + c.charCodeAt(0).toString(16).padStart(2, '0')).join(''),
        containsCtrlC: data.includes('\x03'),
      });
      
      dataListener(data);
    });
    
    logger.info('✅ Process.stdin listener registered', {
      component: 'KeypressContext',
      operation: 'listener_registration',
      listenerCount: process.stdin.listenerCount('data'),
    });

    return () => {
      // Disable Bracketed Paste Mode on cleanup
      if (process.stdout.isTTY) {
        process.stdout.write('\x1b[?2004l'); // Disable bracketed paste mode
      }
      process.stdin.removeListener('data', dataListener);
      if (wasRaw === false) {
        setRawMode(false);
      }
    };
  }, [stdin, setRawMode, broadcast]);

  return (
    <KeypressContext.Provider value={{ subscribe, unsubscribe }}>
      {children}
    </KeypressContext.Provider>
  );
}
