import { useEffect, useRef } from 'react';
import { logger } from '../utils/logger.js';
import { MEMORY_CHECK_INTERVAL, MEMORY_WARNING_THRESHOLD } from '../constants/limits.js';

export function useMemoryMonitor(
  messages: any[],
  workingDir: string,
  model: string | undefined,
): void {
  const messagesRef = useRef(messages);
  useEffect(() => { messagesRef.current = messages; }, [messages]);

  useEffect(() => {
    logger.info('App started', { workingDir, model });

    const interval = setInterval(() => {
      const heapUsedMB = process.memoryUsage().heapUsed / 1024 / 1024;
      if (heapUsedMB > MEMORY_WARNING_THRESHOLD) {
        logger.warn('High memory usage detected', {
          heapUsedMB: heapUsedMB.toFixed(2),
          messageCount: messagesRef.current.length,
        });
      }
    }, MEMORY_CHECK_INTERVAL);

    return () => {
      clearInterval(interval);
      logger.info('App shutting down');
    };
  }, [workingDir, model]);
}
