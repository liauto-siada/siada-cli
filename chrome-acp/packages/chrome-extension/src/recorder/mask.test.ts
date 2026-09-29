import { describe, expect, test, beforeEach } from "bun:test";
import { shouldMaskValue, getRecordableValue } from "./mask";

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("shouldMaskValue", () => {
  test("masks password inputs", () => {
    document.body.innerHTML = `<input type="password" value="secret">`;
    expect(shouldMaskValue(document.querySelector("input")!)).toBe(true);
  });

  test("masks elements with data-acp-mask", () => {
    document.body.innerHTML = `<input type="text" data-acp-mask value="token">`;
    expect(shouldMaskValue(document.querySelector("input")!)).toBe(true);
  });

  test("masks elements inside a data-acp-mask ancestor", () => {
    document.body.innerHTML = `<form data-acp-mask><input type="text" value="x"></form>`;
    expect(shouldMaskValue(document.querySelector("input")!)).toBe(true);
  });

  test("does not mask normal inputs", () => {
    document.body.innerHTML = `<input type="text" value="hello">`;
    expect(shouldMaskValue(document.querySelector("input")!)).toBe(false);
  });
});

describe("getRecordableValue", () => {
  test("returns *** for masked inputs", () => {
    document.body.innerHTML = `<input type="password" value="secret">`;
    expect(getRecordableValue(document.querySelector("input")!)).toBe("***");
  });

  test("returns raw value for normal inputs", () => {
    document.body.innerHTML = `<input type="text" value="关键词">`;
    expect(getRecordableValue(document.querySelector("input")!)).toBe("关键词");
  });

  test("returns undefined for non-input elements", () => {
    document.body.innerHTML = `<button>ok</button>`;
    expect(getRecordableValue(document.querySelector("button")!)).toBeUndefined();
  });
});
