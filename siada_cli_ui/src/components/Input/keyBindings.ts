/**
 * Keyboard shortcuts and key bindings configuration
 */

/**
 * Command enum for all available keyboard shortcuts
 */
export enum Command {
  // Basic bindings
  RETURN = 'return',
  ESCAPE = 'escape',

  // Cursor movement
  HOME = 'home',
  END = 'end',
  LEFT = 'left',
  RIGHT = 'right',
  UP = 'up',
  DOWN = 'down',
  WORD_LEFT = 'wordLeft',
  WORD_RIGHT = 'wordRight',

  // Text deletion
  BACKSPACE = 'backspace',
  DELETE = 'delete',
  KILL_LINE_RIGHT = 'killLineRight',
  KILL_LINE_LEFT = 'killLineLeft',
  CLEAR_INPUT = 'clearInput',
  DELETE_WORD_BACKWARD = 'deleteWordBackward',

  // Screen control
  CLEAR_SCREEN = 'clearScreen',

  // History navigation
  HISTORY_UP = 'historyUp',
  HISTORY_DOWN = 'historyDown',

  // Text input
  SUBMIT = 'submit',
  NEWLINE = 'newline',

  // External tools
  OPEN_EXTERNAL_EDITOR = 'openExternalEditor',
  PASTE_CLIPBOARD = 'pasteClipboard',

  // Completion
  ACCEPT_SUGGESTION = 'acceptSuggestion',
  COMPLETION_UP = 'completionUp',
  COMPLETION_DOWN = 'completionDown',

  // Reverse search
  REVERSE_SEARCH = 'reverseSearch',
}

/**
 * Key interface matching ink's key structure
 */
export interface Key {
  name?: string;
  sequence?: string;
  ctrl?: boolean;
  shift?: boolean;
  meta?: boolean;
  paste?: boolean;
}

/**
 * Data-driven key binding structure
 */
export interface KeyBinding {
  /** The key name (e.g., 'a', 'return', 'tab', 'escape') */
  key?: string;
  /** The key sequence (e.g., '\\x18' for Ctrl+X) */
  sequence?: string;
  /** Control key requirement */
  ctrl?: boolean;
  /** Shift key requirement */
  shift?: boolean;
  /** Command/meta key requirement */
  command?: boolean;
  /** Paste operation requirement */
  paste?: boolean;
}

/**
 * Configuration type mapping commands to their key bindings
 */
export type KeyBindingConfig = {
  readonly [C in Command]: readonly KeyBinding[];
};

/**
 * Default key binding configuration
 */
export const defaultKeyBindings: KeyBindingConfig = {
  // Basic bindings
  [Command.RETURN]: [{ key: 'return' }],
  [Command.ESCAPE]: [{ key: 'escape' }],

  // Cursor movement
  [Command.HOME]: [{ key: 'a', ctrl: true }, { key: 'home' }],
  [Command.END]: [{ key: 'e', ctrl: true }, { key: 'end' }],
  [Command.LEFT]: [{ key: 'left' }],
  [Command.RIGHT]: [{ key: 'right' }],
  [Command.UP]: [{ key: 'up', shift: false }],
  [Command.DOWN]: [{ key: 'down', shift: false }],
  [Command.WORD_LEFT]: [{ key: 'left', ctrl: true }],
  [Command.WORD_RIGHT]: [{ key: 'right', ctrl: true }],

  // Text deletion
  [Command.BACKSPACE]: [{ key: 'backspace' }],
  [Command.DELETE]: [{ key: 'delete' }],
  [Command.KILL_LINE_RIGHT]: [{ key: 'k', ctrl: true }],
  [Command.KILL_LINE_LEFT]: [{ key: 'u', ctrl: true }],
  [Command.CLEAR_INPUT]: [{ key: 'c', ctrl: true }],
  [Command.DELETE_WORD_BACKWARD]: [
    { key: 'w', ctrl: true },
    { key: 'backspace', command: true },
  ],

  // Screen control
  [Command.CLEAR_SCREEN]: [{ key: 'l', ctrl: true }],

  // History navigation
  [Command.HISTORY_UP]: [{ key: 'p', ctrl: true }],
  [Command.HISTORY_DOWN]: [{ key: 'n', ctrl: true }],

  // Text input
  // Must exclude shift, ctrl, command, and paste to allow those for newline
  [Command.SUBMIT]: [
    {
      key: 'return',
      ctrl: false,
      command: false,
      paste: false,
      shift: false,
    },
  ],
  [Command.NEWLINE]: [
    { key: 'return', shift: true },
    { key: 'return', ctrl: true },
    { key: 'return', command: true },
    { key: 'return', paste: true },
    { key: 'j', ctrl: true },
  ],

  // External tools
  [Command.OPEN_EXTERNAL_EDITOR]: [{ sequence: '\x18' }], // Ctrl+X
  [Command.PASTE_CLIPBOARD]: [
    { key: 'v', ctrl: true },
    { key: 'v', command: true },
  ],

  // Completion
  [Command.ACCEPT_SUGGESTION]: [{ key: 'tab' }],
  [Command.COMPLETION_UP]: [{ key: 'up' }],
  [Command.COMPLETION_DOWN]: [{ key: 'down' }],

  // Reverse search
  [Command.REVERSE_SEARCH]: [{ key: 'r', ctrl: true }],
};

/**
 * Matches a KeyBinding against an actual Key press
 */
function matchKeyBinding(keyBinding: KeyBinding, key: Key): boolean {
  // Either key name or sequence must match
  let keyMatches = false;

  if (keyBinding.key !== undefined) {
    keyMatches = keyBinding.key === key.name;
  } else if (keyBinding.sequence !== undefined) {
    keyMatches = keyBinding.sequence === key.sequence;
  } else {
    return false;
  }

  if (!keyMatches) {
    return false;
  }

  // Check modifiers
  if (keyBinding.ctrl !== undefined && key.ctrl !== keyBinding.ctrl) {
    return false;
  }

  if (keyBinding.shift !== undefined && key.shift !== keyBinding.shift) {
    return false;
  }

  if (keyBinding.command !== undefined && key.meta !== keyBinding.command) {
    return false;
  }

  if (keyBinding.paste !== undefined && key.paste !== keyBinding.paste) {
    return false;
  }

  return true;
}

/**
 * Checks if a key matches any of the bindings for a command
 */
function matchCommand(
  command: Command,
  key: Key,
  config: KeyBindingConfig = defaultKeyBindings,
): boolean {
  const bindings = config[command];
  return bindings.some((binding) => matchKeyBinding(binding, key));
}

/**
 * Key matcher function type
 */
type KeyMatcher = (key: Key) => boolean;

/**
 * Type for key matchers mapped to Command enum
 */
export type KeyMatchers = {
  readonly [C in Command]: KeyMatcher;
};

/**
 * Creates key matchers from a key binding configuration
 */
export function createKeyMatchers(
  config: KeyBindingConfig = defaultKeyBindings,
): KeyMatchers {
  const matchers = {} as { [C in Command]: KeyMatcher };

  for (const command of Object.values(Command)) {
    matchers[command] = (key: Key) => matchCommand(command, key, config);
  }

  return matchers as KeyMatchers;
}

/**
 * Default key binding matchers
 */
export const keyMatchers: KeyMatchers = createKeyMatchers(defaultKeyBindings);
