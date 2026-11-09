import { createContext } from 'react';

/** Limit existing full-screen views to the composer pane without changing their actions. */
export const BottomPaneContext = createContext<{ rows: number; columns: number } | null>(null);