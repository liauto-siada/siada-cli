import { useEffect, useRef } from 'react';
import { logger } from '../utils/logger.js';

export function useBackendExit(client: any, exit: () => void): void {
  const exitCalledRef = useRef(false);

  useEffect(() => {
    if (!client) return;

    const handleExit = (code: number | null) => {
      if (exitCalledRef.current) return;
      exitCalledRef.current = true;
      logger.info('Backend process exited, shutting down frontend', { exitCode: code });
      setTimeout(() => exit(), 500);
    };

    client.adapter.on('exit', handleExit);
    return () => { client.adapter.off('exit', handleExit); };
  }, [client, exit]);
}
