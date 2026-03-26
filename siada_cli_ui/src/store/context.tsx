/**
 * React Context for Global State Management
 * Provides app-wide state using React Context API
 */

import React, { createContext, useContext, useReducer, ReactNode, Dispatch } from 'react';
import { AppState } from '../types/index.js';
import { appReducer, AppAction } from './reducers.js';

/**
 * Initial application state
 */
const initialState: AppState = {
  messages: [],
  connectionStatus: {
    connected: false,
    connecting: false,
    ready: false,
  },
  loading: false,
  shellModeActive: false,
  shellExecution: undefined,
};

/**
 * App Context Type
 */
interface AppContextType {
  state: AppState;
  dispatch: Dispatch<AppAction>;
}

/**
 * Create Context
 */
const AppContext = createContext<AppContextType | undefined>(undefined);

/**
 * App Provider Props
 */
interface AppProviderProps {
  children: ReactNode;
  initialState?: Partial<AppState>;
}

/**
 * App Provider Component
 */
export const AppProvider: React.FC<AppProviderProps> = ({ children, initialState: customInitialState }) => {
  const [state, dispatch] = useReducer(
    appReducer,
    customInitialState ? { ...initialState, ...customInitialState } : initialState
  );

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
};

/**
 * Hook to use App Context
 */
export const useAppContext = (): AppContextType => {
  const context = useContext(AppContext);
  
  if (!context) {
    throw new Error('useAppContext must be used within AppProvider');
  }
  
  return context;
};

/**
 * Hook to use App State
 */
export const useAppState = (): AppState => {
  const { state } = useAppContext();
  return state;
};

/**
 * Hook to use App Dispatch
 */
export const useAppDispatch = (): Dispatch<AppAction> => {
  const { dispatch } = useAppContext();
  return dispatch;
};
