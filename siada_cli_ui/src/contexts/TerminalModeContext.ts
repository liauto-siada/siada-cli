import { createContext, useContext } from 'react';

/** The launcher's opt-out applies to every nested terminal view. */
export const NoAltScreenContext = createContext(false);

export function useNoAltScreen(): boolean {
  return useContext(NoAltScreenContext);
}