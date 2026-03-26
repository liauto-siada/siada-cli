/**
 * Terminal Height Utilities
 * 
 * Provides utilities to prevent rendering content that equals or exceeds
 * terminal height, which can cause flickering and scrolling issues.
 */

import { logger } from './logger.js';

/**
 * Maximum safe height for rendering content in the terminal
 * Content should never equal or exceed process.stdout.rows to prevent
 * flickering caused by terminal scrolling.
 * 
 * @returns Maximum safe height (process.stdout.rows - 1)
 */
export function getMaxSafeHeight(): number {
  // Default to 24 rows if stdout.rows is not available (e.g., in tests)
  const terminalRows = process.stdout?.rows ?? 24;
  
  // Reserve at least 1 row to prevent full-screen issues
  return Math.max(terminalRows - 1, 1);
}

/**
 * Constrains a height value to be within safe terminal bounds
 * 
 * @param height - The desired height (can be number, string, or undefined)
 * @param componentName - Name of the component for logging purposes
 * @returns The constrained height value
 */
export function constrainHeight(
  height: number | string | undefined,
  componentName: string = 'Component'
): number | string | undefined {
  // If height is not specified or is a string (e.g., "50%"), leave it unchanged
  if (height === undefined || typeof height === 'string') {
    return height;
  }

  // If height is a number, check if it needs to be constrained
  const maxSafeHeight = getMaxSafeHeight();
  
  if (height >= (process.stdout?.rows ?? 24)) {
    logger.warn(
      `${componentName}: Height ${height} >= terminal rows (${process.stdout?.rows}). ` +
      `Constraining to ${maxSafeHeight} to prevent flickering.`
    );
    return maxSafeHeight;
  }

  return height;
}

/**
 * Checks if a height value is safe (won't cause flickering)
 * 
 * @param height - The height to check
 * @returns true if the height is safe, false otherwise
 */
export function isSafeHeight(height: number | string | undefined): boolean {
  if (height === undefined || typeof height === 'string') {
    return true; // String heights and undefined are handled by the layout engine
  }

  const terminalRows = process.stdout?.rows ?? 24;
  return height < terminalRows;
}
