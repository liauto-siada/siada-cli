import { describe, expect, test, beforeEach } from "bun:test";
import { getSelector, getXPath, describeTarget, briefNode } from "./selector";

beforeEach(() => {
  document.body.innerHTML = "";
});

describe("getSelector", () => {
  test("prefers simple id", () => {
    document.body.innerHTML = `<button id="login-btn">登录</button>`;
    const el = document.querySelector("button")!;
    expect(getSelector(el)).toBe("#login-btn");
  });

  test("uses attribute selector for non-simple id", () => {
    document.body.innerHTML = `<div id="123 abc">x</div>`;
    const el = document.querySelector("div")!;
    expect(getSelector(el)).toBe('[id="123 abc"]');
  });

  test("prefers data-testid over classes", () => {
    document.body.innerHTML = `<div><button data-testid="submit" class="btn primary">Go</button></div>`;
    const el = document.querySelector("button")!;
    expect(getSelector(el)).toBe('[data-testid="submit"]');
  });

  test("builds segment with classes and nth-of-type", () => {
    document.body.innerHTML = `
      <div class="list">
        <div class="item">a</div>
        <div class="item">b</div>
      </div>`;
    const items = document.querySelectorAll(".item");
    expect(getSelector(items[1]!)).toBe("div.item:nth-of-type(2)");
  });

  test("filters out dynamic classes containing 3+ digits", () => {
    document.body.innerHTML = `
      <div>
        <button class="btn css-12345 active">x</button>
      </div>`;
    const el = document.querySelector("button")!;
    expect(getSelector(el)).toBe("button.btn.active");
  });

  test("stops climbing once selector is unique", () => {
    document.body.innerHTML = `
      <div class="outer"><span class="mid"><a class="link">x</a></span></div>
      <div class="other"><span><a>x</a></span></div>`;
    const el = document.querySelector(".outer .link")!;
    expect(getSelector(el)).toBe("a.link");
  });

  test("climbs to ancestors when element alone is not unique", () => {
    document.body.innerHTML = `
      <div class="form-a"><button class="btn">a</button></div>
      <div class="form-b"><button class="btn">b</button></div>`;
    const el = document.querySelector(".form-b .btn")!;
    expect(getSelector(el)).toBe("div.form-b > button.btn");
  });

  test("escapes tailwind-style classes", () => {
    document.body.innerHTML = `<div><span class="w-[px]">x</span></div>`;
    const el = document.querySelector("span")!;
    expect(getSelector(el)).toBe("span.w-\\[px\\]");
  });
});

describe("getXPath", () => {
  test("builds absolute xpath with positions among same-tag siblings", () => {
    document.body.innerHTML = `<div><p>a</p><span>s</span><p>b</p></div>`;
    const p2 = document.querySelectorAll("p")[1]!;
    expect(getXPath(p2)).toBe("/html/body/div/p[2]");
  });

  test("omits position when only sibling of its tag", () => {
    document.body.innerHTML = `<div><button>x</button></div>`;
    expect(getXPath(document.querySelector("button")!)).toBe("/html/body/div/button");
  });
});

describe("describeTarget", () => {
  test("includes tag, selector, xpath and text", () => {
    document.body.innerHTML = `<button id="save">保存更改</button>`;
    const t = describeTarget(document.querySelector("button")!);
    expect(t.tag).toBe("button");
    expect(t.selector).toBe("#save");
    expect(t.xpath).toBe("/html/body/button");
    expect(t.text).toBe("保存更改");
  });

  test("truncates text to 50 chars", () => {
    document.body.innerHTML = `<p>${"长".repeat(80)}</p>`;
    const t = describeTarget(document.querySelector("p")!);
    expect(t.text!.length).toBe(50);
  });

  test("captures explicit role and aria-label", () => {
    document.body.innerHTML = `<div role="button" aria-label="关闭">x</div>`;
    const t = describeTarget(document.querySelector("div")!);
    expect(t.role).toBe("button");
    expect(t.ariaLabel).toBe("关闭");
  });

  test("uses input value as text for inputs", () => {
    document.body.innerHTML = `<input id="q" value="关键词">`;
    const t = describeTarget(document.querySelector("input")!);
    expect(t.text).toBe("关键词");
  });
});

describe("briefNode", () => {
  test("describes element with tag and text snippet", () => {
    document.body.innerHTML = `<button>登录</button>`;
    expect(briefNode(document.querySelector("button")!)).toBe(`button"登录"`);
  });

  test("describes text node as quoted snippet", () => {
    document.body.innerHTML = `<div>你好世界</div>`;
    const textNode = document.querySelector("div")!.firstChild!;
    expect(briefNode(textNode)).toBe(`"你好世界"`);
  });

  test("falls back to tag with first stable class when no text", () => {
    document.body.innerHTML = `<div class="modal open"></div>`;
    expect(briefNode(document.querySelector("div")!)).toBe("div.modal");
  });

  test("truncates long text", () => {
    document.body.innerHTML = `<span>${"文".repeat(40)}</span>`;
    const brief = briefNode(document.querySelector("span")!);
    expect(brief.length).toBeLessThanOrEqual(28); // span + quotes + <=20 chars
  });
});
