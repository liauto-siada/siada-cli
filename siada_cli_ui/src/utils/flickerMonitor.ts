/**
 * Flicker Monitor — Tracks screen-clearing events to help diagnose flickering.
 *
 * The siada-cli UI relies on Ink's <Static> component plus occasional
 * `clearTerminal` writes to achieve "dynamic rendering".  Each clear+redraw
 * cycle can cause a visible flicker.  This module instruments every known
 * clear path, records the cause, and emits a consolidated alert when
 * multiple clears happen in rapid succession (the actual "flicker" the user
 * sees).
 *
 * Enable:  set SIADA_DEBUG=1 (siada debug mode), or SIADA_FLICKER_MONITOR=1
 * Default: disabled (to avoid impacting normal users)
 *
 * All events are written to the existing logger (~/​.siada-cli/​ui-logs/​siada-ui.log).
 * Rapid-clear alerts are additionally printed to stderr (visible in the
 * terminal's scrollback) so they can be spotted during live usage.
 */

import { logger } from './logger.js';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type FlickerSource =
  | 'refreshStatic'        // MessageList.refreshStatic() — clearTerminal + remount
  | 'ctrl_o_collapse'      // App.tsx Ctrl+O — \x1b[2J\x1b[H + toggle isCollapsed
  | 'ctrl_c_interrupt'     // App.tsx Ctrl+C — stopExecution + system message
  | 'clearMessages'        // useACP.clearMessages / useAdapterEvents loadHistory
  | 'group_signature_remount' // MessageList — needsRemount triggered refreshStatic
  | 'resize_debounced'     // MessageList — terminal resize debounced timeout
  | 'model_change'         // MessageList — headerProps.model changed
  | 'manual_clear'         // Any other direct stdout clear
  | 'unknown';

export interface FlickerEvent {
  timestamp: number;
  source: FlickerSource;
  reason: string;
  stackTrace?: string;
  messageCount?: number;
  remountKey?: number;
  metadata?: Record<string, any>;
}

export interface FlickerAlert {
  timestamp: number;
  events: FlickerEvent[];
  intervalMs: number;   // time between first and last event in the burst
  eventCount: number;
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const ENV = (typeof globalThis.process !== 'undefined' && globalThis.process.env) || {};
// Disabled by default; enabled when SIADA_DEBUG=1 or SIADA_FLICKER_MONITOR=1
const ENABLED =
  ENV.SIADA_FLICKER_MONITOR === '1' ||
  !!ENV.SIADA_DEBUG;
const FLICKER_WINDOW_MS = parseInt(ENV.SIADA_FLICKER_WINDOW_MS ?? '800', 10);
const FLICKER_MIN_EVENTS = parseInt(ENV.SIADA_FLICKER_MIN_EVENTS ?? '2', 10);

// ---------------------------------------------------------------------------
// State (module-level singleton)
// ---------------------------------------------------------------------------

const events: FlickerEvent[] = [];
const MAX_EVENTS = 500;
let lastAlertTime = 0;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function captureStack(): string | undefined {
  if (!ENABLED) return undefined;
  const oldLimit = Error.stackTraceLimit;
  Error.stackTraceLimit = 12;
  const err = new Error();
  Error.stackTraceLimit = oldLimit;
  const stack = err.stack ?? '';
  // Remove the first 3 lines (Error, captureStack, recordEvent) to point at the caller
  const lines = stack.split('\n');
  return lines.slice(3).join('\n');
}

function emitAlert(alert: FlickerAlert): void {
  logger.warn('⚡ Flicker detected — multiple screen clears in rapid succession', {
    component: 'FlickerMonitor',
    operation: 'flicker_alert',
    eventCount: alert.eventCount,
    intervalMs: alert.intervalMs,
    sources: alert.events.map(e => e.source),
    reasons: alert.events.map(e => e.reason),
    messageCounts: alert.events.map(e => e.messageCount),
    timestamp: new Date(alert.timestamp).toISOString(),
  });

  // Also print to stderr so it's visible in the terminal scrollback.
  // Uses a distinctive prefix for easy grepping.
  const summary = alert.events
    .map((e, i) => `  [${i}] ${e.source}: ${e.reason}`)
    .join('\n');
  const msg =
    `\n\x1b[33m⚡ [FlickerMonitor] ${alert.eventCount} screen clears in ${alert.intervalMs}ms:\x1b[0m\n${summary}\n`;
  try {
    process.stderr.write(msg);
  } catch {
    // ignore write errors
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Record a single screen-clearing event.
 * If this event falls within `FLICKER_WINDOW_MS` of previous events,
 * a flicker alert may be emitted.
 */
export function recordFlicker(
  source: FlickerSource,
  reason: string,
  options?: {
    messageCount?: number;
    remountKey?: number;
    metadata?: Record<string, any>;
    captureStack?: boolean; // default true; set false for hot paths
  },
): void {
  if (!ENABLED) return;

  const now = Date.now();
  const evt: FlickerEvent = {
    timestamp: now,
    source,
    reason,
    messageCount: options?.messageCount,
    remountKey: options?.remountKey,
    metadata: options?.metadata,
    stackTrace: options?.captureStack === false ? undefined : captureStack(),
  };

  // Append and cap
  events.push(evt);
  if (events.length > MAX_EVENTS) {
    events.splice(0, events.length - MAX_EVENTS);
  }

  // Log individual event
  logger.info('Screen clear event recorded', {
    component: 'FlickerMonitor',
    operation: 'clear_event',
    source,
    reason,
    messageCount: evt.messageCount,
    remountKey: evt.remountKey,
    timestamp: new Date(now).toISOString(),
  });

  // --- Flicker burst detection ---
  // Collect all events within the flicker window ending at `now`
  const windowStart = now - FLICKER_WINDOW_MS;
  const recent = events.filter(e => e.timestamp >= windowStart);

  if (recent.length >= FLICKER_MIN_EVENTS) {
    // Avoid spamming: only emit if we haven't alerted in the last FLICKER_WINDOW_MS
    if (now - lastAlertTime >= FLICKER_WINDOW_MS) {
      lastAlertTime = now;
      const alert: FlickerAlert = {
        timestamp: now,
        events: [...recent],
        intervalMs: now - recent[0].timestamp,
        eventCount: recent.length,
      };
      emitAlert(alert);
    }
  }
}

/**
 * Get all recorded flicker events (for debugging / export).
 */
export function getFlickerEvents(): readonly FlickerEvent[] {
  return events;
}

/**
 * Clear all recorded events (useful for tests or after analysis).
 */
export function resetFlickerMonitor(): void {
  events.length = 0;
  lastAlertTime = 0;
}

/**
 * Whether the monitor is currently enabled.
 */
export function isFlickerMonitorEnabled(): boolean {
  return ENABLED;
}
