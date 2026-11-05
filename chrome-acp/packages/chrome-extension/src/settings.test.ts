import { describe, expect, test } from "bun:test";
import {
  DEFAULT_SETTINGS,
  type ACPSettings,
} from "@chrome-acp/shared/acp";
import { flipLoopbackWsScheme, resolveProxySettings, trajectoryWsUrlFor } from "./settings";

describe("resolveProxySettings", () => {
  test("returns all defaults when nothing is stored", () => {
    expect(resolveProxySettings(undefined)).toEqual(DEFAULT_SETTINGS);
  });

  test("stored settings override the defaults", () => {
    const stored: Partial<ACPSettings> = {
      proxyUrl: "wss://192.168.1.5:9315/ws",
      token: "secret-token",
    };
    expect(resolveProxySettings(stored)).toEqual({
      ...DEFAULT_SETTINGS,
      proxyUrl: "wss://192.168.1.5:9315/ws",
      token: "secret-token",
    });
  });

  test("partial stored settings only override provided fields", () => {
    const stored: Partial<ACPSettings> = { token: "abc" };
    const resolved = resolveProxySettings(stored);
    expect(resolved.proxyUrl).toBe(DEFAULT_SETTINGS.proxyUrl);
    expect(resolved.token).toBe("abc");
  });
});

describe("trajectoryWsUrlFor", () => {
  test("rewrites the default localhost proxy URL", () => {
    expect(trajectoryWsUrlFor("ws://localhost:9315/ws")).toBe(
      "ws://localhost:9315/ws/trajectory",
    );
  });

  test("rewrites a remote wss proxy URL", () => {
    expect(trajectoryWsUrlFor("wss://192.168.1.5:9315/ws")).toBe(
      "wss://192.168.1.5:9315/ws/trajectory",
    );
  });

  test("replaces any existing pathname", () => {
    expect(trajectoryWsUrlFor("ws://localhost:9315/some/other/path")).toBe(
      "ws://localhost:9315/ws/trajectory",
    );
  });

  test("preserves scheme, host and port", () => {
    expect(trajectoryWsUrlFor("wss://proxy.example.com:9443/anything")).toBe(
      "wss://proxy.example.com:9443/ws/trajectory",
    );
  });
});

describe("flipLoopbackWsScheme", () => {
  test("flips wss to ws for localhost, keeping path and query", () => {
    expect(flipLoopbackWsScheme("wss://localhost:9315/ws/trajectory")).toBe(
      "ws://localhost:9315/ws/trajectory",
    );
    expect(flipLoopbackWsScheme("wss://localhost:9315/ws?token=abc")).toBe(
      "ws://localhost:9315/ws?token=abc",
    );
  });

  test("flips ws to wss for loopback IPs", () => {
    expect(flipLoopbackWsScheme("ws://127.0.0.1:9315/ws")).toBe(
      "wss://127.0.0.1:9315/ws",
    );
    expect(flipLoopbackWsScheme("ws://[::1]:9315/ws")).toBe(
      "wss://[::1]:9315/ws",
    );
  });

  test("returns null for non-loopback hosts", () => {
    expect(flipLoopbackWsScheme("wss://192.168.1.5:9315/ws")).toBeNull();
    expect(flipLoopbackWsScheme("wss://proxy.example.com/ws")).toBeNull();
  });

  test("returns null for non-WS or invalid URLs", () => {
    expect(flipLoopbackWsScheme("https://localhost:9315/app")).toBeNull();
    expect(flipLoopbackWsScheme("not a url")).toBeNull();
  });
});