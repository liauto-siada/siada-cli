import { describe, expect, test } from "bun:test";
import { directoriesToRefresh, isDeletedPath } from "./file-explorer-refresh";

describe("file explorer refresh after build cleanup", () => {
  test("does not request unloaded build directories", () => {
    expect(directoriesToRefresh([
      { event: "delete", path: "service/target/classes/db/migration/schema.sql" },
      { event: "delete", path: "service/target/classes/web/Controller.class" },
    ], new Set(["", "service"]))).toEqual([]);
  });

  test("refreshes the surviving parent instead of deleted descendants", () => {
    expect(directoriesToRefresh([
      { event: "delete", path: "service/target" },
      { event: "delete", path: "service/target/classes/db/schema.sql" },
      { event: "delete", path: "service/target/classes/web/Controller.class" },
    ], new Set(["", "service", "service/target", "service/target/classes/db", "service/target/classes/web"])))
      .toEqual(["service"]);
  });

  test("coalesces changes in a loaded directory and refreshes root entries", () => {
    expect(directoriesToRefresh([
      { event: "update", path: "src/a.ts" },
      { event: "create", path: "src/b.ts" },
      { event: "create", path: "README.md" },
    ], new Set(["", "src"]))).toEqual(["src", ""]);
  });

  test("deleted subtree matching respects path boundaries", () => {
    const changes = [{ event: "delete" as const, path: "target" }];
    expect(isDeletedPath("target/classes", changes)).toBe(true);
    expect(isDeletedPath("target", changes)).toBe(true);
    expect(isDeletedPath("target-backup/classes", changes)).toBe(false);
  });
});