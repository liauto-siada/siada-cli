import { describe, expect, test } from "bun:test";
import { parseShareLink } from "./share-link";

describe("parseShareLink", () => {
  test("parses session, cwd and token when all are present", () => {
    expect(parseShareLink("?session=sess-123&cwd=/work/project&token=topsecret")).toEqual({
      sessionId: "sess-123",
      cwd: "/work/project",
      token: "topsecret",
    });
  });

  test("returns only sessionId when only session is present", () => {
    expect(parseShareLink("?session=sess-456")).toEqual({
      sessionId: "sess-456",
    });
  });

  test("returns an empty object for an empty search string", () => {
    expect(parseShareLink("")).toEqual({});
  });

  test("returns an empty object when none of the share params are present", () => {
    expect(parseShareLink("?foo=bar&baz=qux")).toEqual({});
  });

  test("decodes a URL-encoded cwd path", () => {
    expect(
      parseShareLink("?session=sess-1&cwd=%2Fhome%2Fuser%2Fmy%20project&token=t")
    ).toEqual({
      sessionId: "sess-1",
      cwd: "/home/user/my project",
      token: "t",
    });
  });
});