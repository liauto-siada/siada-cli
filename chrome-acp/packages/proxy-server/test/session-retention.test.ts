import { describe, expect, test } from "bun:test";
import { SessionRetention, SESSION_RETENTION_MS } from "../src/session-retention";

function harness() {
  let now = 0;
  const released: string[] = [];
  const scheduled: Array<{ callback: () => void; delay: number; cancelled: boolean }> = [];
  const cache = new SessionRetention<string>(
    value => released.push(value), SESSION_RETENTION_MS, () => now,
    (callback, delay) => {
      const timer = { callback, delay, cancelled: false };
      scheduled.push(timer);
      return timer as unknown as ReturnType<typeof setTimeout>;
    },
    timer => { (timer as unknown as typeof scheduled[number]).cancelled = true; },
  );
  return { cache, released, scheduled, advance: (value: number) => { now = value; } };
}

describe("five minute detached session ownership", () => {
  test("reattaches before expiry and cancels the pending release", () => {
    const h = harness();
    h.cache.retain("window", "agent");
    expect(h.scheduled[0]!.delay).toBe(300_000);
    h.advance(299_999);
    expect(h.cache.take("window")).toBe("agent");
    h.scheduled[0]!.callback();
    expect(h.released).toEqual([]);
    expect(h.cache.size).toBe(0);
    expect(h.scheduled[0]!.cancelled).toBe(true);
  });

  test("expires at five minutes even when the timer callback is delayed", () => {
    const h = harness();
    h.cache.retain("window", "agent");
    h.advance(300_000);
    expect(h.cache.take("window")).toBeUndefined();
    h.scheduled[0]!.callback();
    expect(h.released).toEqual(["agent"]);
  });

  test("old callbacks cannot release a replacement or another window", () => {
    const h = harness();
    h.cache.retain("first", "old");
    const oldCallback = h.scheduled[0]!.callback;
    h.cache.retain("first", "new");
    h.cache.retain("second", "other");
    oldCallback();
    expect(h.cache.take("first")).toBe("new");
    h.scheduled[2]!.callback();
    expect(h.released).toEqual(["old", "other"]);
  });

  test("bounds resident processes and releases all remaining entries on shutdown", () => {
    const h = harness();
    for (let i = 0; i < 33; i++) h.cache.retain(String(i), String(i));
    expect(h.cache.size).toBe(32);
    expect(h.released).toEqual(["0"]);
    h.cache.clear();
    expect(h.cache.size).toBe(0);
    expect(h.released.length).toBe(33);
  });
});