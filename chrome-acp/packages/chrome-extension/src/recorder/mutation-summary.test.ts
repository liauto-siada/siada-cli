import { describe, expect, test, beforeEach } from "bun:test";
import { summarizeMutations } from "./mutation-summary";

beforeEach(() => {
  document.body.innerHTML = "";
});

// Collect real MutationRecords by mutating the DOM under an observer.
async function collect(mutate: () => void): Promise<MutationRecord[]> {
  const records: MutationRecord[] = [];
  const observer = new MutationObserver((rs) => records.push(...rs));
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    characterData: true,
  });
  mutate();
  await new Promise((resolve) => setTimeout(resolve, 10));
  observer.disconnect();
  return records;
}

describe("summarizeMutations", () => {
  test("describes added elements", async () => {
    const records = await collect(() => {
      const el = document.createElement("button");
      el.textContent = "登录";
      document.body.appendChild(el);
    });
    expect(summarizeMutations(records)).toBe(`新增: button"登录"`);
  });

  test("describes removed elements", async () => {
    document.body.innerHTML = `<span id="x">旧内容</span>`;
    const records = await collect(() => {
      document.querySelector("#x")!.remove();
    });
    expect(summarizeMutations(records)).toBe(`移除: span"旧内容"`);
  });

  test("describes text changes", async () => {
    document.body.innerHTML = `<p>旧文本</p>`;
    const records = await collect(() => {
      document.querySelector("p")!.firstChild!.textContent = "新文本";
    });
    expect(summarizeMutations(records)).toBe(`文本变化: "新文本"`);
  });

  test("describes attribute changes", async () => {
    document.body.innerHTML = `<div>内容</div>`;
    const records = await collect(() => {
      document.querySelector("div")!.setAttribute("class", "modal open");
    });
    expect(summarizeMutations(records)).toBe(`属性变化: div"内容" 的 class`);
  });

  test("ignores script and style additions", async () => {
    const records = await collect(() => {
      const script = document.createElement("script");
      script.textContent = "console.log(1)";
      document.body.appendChild(script);
      const style = document.createElement("style");
      style.textContent = "body{}";
      document.body.appendChild(style);
    });
    expect(summarizeMutations(records)).toBe("");
  });

  test("ignores whitespace-only text additions", async () => {
    const records = await collect(() => {
      document.body.appendChild(document.createTextNode("   \n  "));
    });
    expect(summarizeMutations(records)).toBe("");
  });

  test("dedupes identical lines", async () => {
    const records = await collect(() => {
      for (let i = 0; i < 3; i++) {
        const el = document.createElement("li");
        el.textContent = "相同项";
        document.body.appendChild(el);
      }
    });
    expect(summarizeMutations(records)).toBe(`新增: li"相同项"`);
  });

  test("caps items and reports the overflow count", async () => {
    const records = await collect(() => {
      for (let i = 1; i <= 8; i++) {
        const el = document.createElement("div");
        el.textContent = `项目${i}`;
        document.body.appendChild(el);
      }
    });
    const summary = summarizeMutations(records, { maxItems: 5 });
    expect(summary).toBe(
      `新增: div"项目1"；新增: div"项目2"；新增: div"项目3"；新增: div"项目4"；新增: div"项目5"；等 3 处变化`,
    );
  });

  test("caps total length", async () => {
    const records = await collect(() => {
      for (let i = 0; i < 10; i++) {
        const el = document.createElement("div");
        el.textContent = `内容${i}-${"长".repeat(30)}`;
        document.body.appendChild(el);
      }
    });
    const summary = summarizeMutations(records, { maxItems: 10, maxLength: 60 });
    expect(summary.length).toBeLessThanOrEqual(61); // 60 + ellipsis
    expect(summary.endsWith("…")).toBe(true);
  });

  test("returns empty string for no mutations", () => {
    expect(summarizeMutations([])).toBe("");
  });
});
