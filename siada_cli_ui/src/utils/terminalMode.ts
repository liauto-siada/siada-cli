export interface TerminalModeOptions {
  altScreen?: boolean;
  alternateBuffer?: boolean;
}

export function resolveTerminalMode(options: TerminalModeOptions) {
  const noAltScreen = options.altScreen === false;
  return {
    noAltScreen,
    alternateBuffer: !noAltScreen && options.alternateBuffer !== false,
  };
}