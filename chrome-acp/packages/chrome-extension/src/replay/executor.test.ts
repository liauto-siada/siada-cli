import { describe, expect, test, beforeEach } from "bun:test";
import {
  findElementByTarget,
  performAction,
  runReplayStep,
} from "./executor";
import type { ReplayStep } from "@chrome-acp/shared/acp";

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("findElementByTarget", () => {
  test("finds by css selector first", () => {
    document.body.innerHTML = `<button id="a">x</button><button class="dup">y</button>`;
    const el = findElementByTarget(document, {
      tag: "button",
      selector: ".dup",
      xpath: "/html/body/button[1]", // would match the OTHER button
      text: "y",
    });
    expect(el!.className).toBe("dup");
  });

  test("falls back to xpath when selector fails", () => {
    document.body.innerHTML = `<div><span>a</span><span>b</span></div>`;
    const el = findElementByTarget(document, {
      tag: "span",
      selector: ".missing",
      xpath: "/html/body/div/span[2]",
    });
    expect(el!.textContent).toBe("b");
  });

  test("falls back to visible text on matching tag", () => {
    document.body.innerHTML = `<button>取消</button><button>确定</button>`;
    const el = findElementByTarget(document, {
      tag: "button",
      selector: ".missing",
      xpath: "//nonexistent",
      text: "确定",
    });
    expect(el!.textContent).toBe("确定");
  });

  test("text match ignores extra whitespace", () => {
    document.body.innerHTML = `<button>
      提交订单
    </button>`;
    const el = findElementByTarget(document, {
      tag: "button",
      selector: ".missing",
      xpath: "//nonexistent",
      text: "提交订单",
    });
    expect(el).not.toBeNull();
  });

  test("returns null when nothing matches", () => {
    document.body.innerHTML = `<div>nothing</div>`;
    expect(
      findElementByTarget(document, {
        tag: "button",
        selector: ".missing",
        xpath: "//nonexistent",
        text: "不存在",
      }),
    ).toBeNull();
  });
});

describe("performAction", () => {
  test("click dispatches a bubbling mouse event", () => {
    document.body.innerHTML = `<button>ok</button>`;
    const btn = document.querySelector("button")!;
    let clicked = false;
    btn.addEventListener("click", () => (clicked = true));
    performAction(btn, { kind: "click" });
    expect(clicked).toBe(true);
  });

  test("input sets value and fires input+change (React-compatible)", () => {
    document.body.innerHTML = `<input type="text">`;
    const input = document.querySelector("input")!;
    const events: string[] = [];
    input.addEventListener("input", () => events.push("input"));
    input.addEventListener("change", () => events.push("change"));
    performAction(input, { kind: "input", value: "你好" });
    expect(input.value).toBe("你好");
    expect(events).toEqual(["input", "change"]);
  });

  test("select sets value and fires change", () => {
    document.body.innerHTML = `<select><option value="a">A</option><option value="b">B</option></select>`;
    const select = document.querySelector("select")!;
    let changed = false;
    select.addEventListener("change", () => (changed = true));
    performAction(select, { kind: "select", value: "b" });
    expect(select.value).toBe("b");
    expect(changed).toBe(true);
  });

  test("keydown dispatches keyboard event with the key", () => {
    document.body.innerHTML = `<input>`;
    const input = document.querySelector("input")!;
    const seen: string[] = [];
    input.addEventListener("keydown", (e) => seen.push((e as KeyboardEvent).key));
    performAction(input, { kind: "keydown", key: "Enter" });
    expect(seen[0]).toBe("Enter");
  });

  test("checkbox input toggles checked by boolean-ish value", () => {
    document.body.innerHTML = `<input type="checkbox">`;
    const box = document.querySelector("input")!;
    performAction(box, { kind: "input", value: "true" });
    expect(box.checked).toBe(true);
    let changed = 0;
    box.addEventListener("change", () => changed++);
    performAction(box, { kind: "input", value: "false" });
    expect(box.checked).toBe(false);
    expect(changed).toBe(1);
  });
});

describe("runReplayStep", () => {
  test("returns ok with page response summary", async () => {
    document.body.innerHTML = `<button id="load">加载</button>`;
    document.querySelector("button")!.addEventListener("click", () => {
      const item = document.createElement("div");
      item.textContent = "搜索结果";
      document.body.appendChild(item);
    });
    const result = await runReplayStep(
      {
        kind: "click",
        target: { tag: "button", selector: "#load", xpath: "", text: "加载" },
      },
      { responseWaitMs: 30 },
    );
    expect(result.ok).toBe(true);
    expect(result.response).toContain(`新增: div"搜索结果"`);
  });

  test("returns element_not_found when target is missing", async () => {
    const result = await runReplayStep(
      {
        kind: "click",
        target: { tag: "button", selector: "#missing", xpath: "", text: "无" },
      },
      { responseWaitMs: 10 },
    );
    expect(result.ok).toBe(false);
    expect(result.error).toBe("element_not_found");
  });

  test("scroll step needs no target", async () => {
    const result = await runReplayStep(
      { kind: "scroll", scrollX: 0, scrollY: 500 },
      { responseWaitMs: 10 },
    );
    expect(result.ok).toBe(true);
  });
});
