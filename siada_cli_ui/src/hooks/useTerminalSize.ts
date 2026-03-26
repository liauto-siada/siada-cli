/**
 * useTerminalSize Hook
 * 
 * Provides reactive terminal dimensions that update on resize events.
 * Unlike useStdout() which returns static values, this hook actively listens
 * to terminal resize events and updates state accordingly.
 * 
 * This ensures components can properly respond to terminal size changes
 * for adaptive layouts and re-rendering.
 */

import { useState, useEffect } from 'react';
import { useStdout } from 'ink';
import { logger } from '../utils/logger.js';

export interface TerminalSize {
  columns: number;
  rows: number;
}

/**
 * Hook that provides reactive terminal dimensions
 * 
 * @returns {TerminalSize} Current terminal dimensions that update on resize
 * 
 * @example
 * ```tsx
 * const { columns, rows } = useTerminalSize();
 * 
 * return (
 *   <Box width={columns}>
 *     <Text>Terminal width: {columns}</Text>
 *   </Box>
 * );
 * ```
 */
export function useTerminalSize(): TerminalSize {
  const { stdout } = useStdout();
  
  // Initialize with current terminal size
  const [size, setSize] = useState<TerminalSize>({
    columns: stdout?.columns ?? 80,
    rows: stdout?.rows ?? 24,
  });

  useEffect(() => {
    if (!stdout) {
      logger.warn('No stdout available in useTerminalSize', {
        hook: 'useTerminalSize',
        operation: 'init',
      });
      return;
    }

    // Handler for resize events
    const handleResize = () => {
      const newSize = {
        columns: stdout.columns ?? 80,
        rows: stdout.rows ?? 24,
      };

      logger.info('Terminal resized', {
        hook: 'useTerminalSize',
        operation: 'resize',
        oldSize: size,
        newSize,
      });

      setSize(newSize);
    };

    // Listen to resize events
    // stdout is a Node.js WriteStream which emits 'resize' events
    stdout.on('resize', handleResize);

    // Log initial size
    logger.info('useTerminalSize initialized', {
      hook: 'useTerminalSize',
      operation: 'init',
      size,
    });

    // Cleanup listener on unmount
    return () => {
      stdout.off('resize', handleResize);
      logger.info('useTerminalSize cleanup', {
        hook: 'useTerminalSize',
        operation: 'cleanup',
      });
    };
  }, [stdout]); // Only re-run if stdout changes

  return size;
}
