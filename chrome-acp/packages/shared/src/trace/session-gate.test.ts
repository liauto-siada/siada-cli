import { describe, expect, test } from "bun:test";
import { createSessionGate } from "./session-gate";

describe("createSessionGate", () => {
  test("lets updates through until a session becomes active", () => {
    const gate = createSessionGate();

    expect(gate.accepts("s1")).toBe(true);
    expect(gate.accepts("s2")).toBe(true);
  });

  test("drops updates from any session other than the active one", () => {
    const gate = createSessionGate();
    gate.setActive("s1");

    expect(gate.accepts("s1")).toBe(true);
    expect(gate.accepts("s2")).toBe(false);
  });

  test("switching sessions moves the boundary instead of widening it", () => {
    const gate = createSessionGate();
    gate.setActive("s1");
    gate.setActive("s2");

    expect(gate.accepts("s1")).toBe(false);
    expect(gate.accepts("s2")).toBe(true);
  });

  test("clearing the active session accepts everything again", () => {
    const gate = createSessionGate();
    gate.setActive("s1");
    gate.setActive(null);

    expect(gate.accepts("s1")).toBe(true);
    expect(gate.accepts("s2")).toBe(true);
  });
});
