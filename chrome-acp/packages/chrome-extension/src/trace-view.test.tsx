// Render tests for the browser-activity viewer. The diff hook needs a canvas
// (absent under happy-dom), which is exactly the code path worth pinning: it
// must degrade to "no overlays" rather than crash the panel.

import { describe, expect, test, beforeEach, afterEach } from "bun:test";
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { TraceView, Viewport } from "@chrome-acp/shared/components";
import {
  TRACE_SCHEMA,
  createBufferedFrameSource,
  type TraceFrame,
  type TraceRun,
} from "@chrome-acp/shared/trace";

// React needs this flag to treat act() as the real thing rather than warn.
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

let container: HTMLDivElement;
let root: Root;
const originalImage = globalThis.Image;
const originalContext = HTMLCanvasElement.prototype.getContext;

beforeEach(() => {
  document.body.innerHTML = "";
  container = document.createElement("div");
  document.body.append(container);
});

afterEach(() => {
  if (root) act(() => root.unmount());
  globalThis.Image = originalImage;
  HTMLCanvasElement.prototype.getContext = originalContext;
});

function loadDisplayedImage(width: number, height: number) {
  const image = container.querySelector("img")!;
  Object.defineProperty(image, "naturalWidth", { configurable: true, value: width });
  Object.defineProperty(image, "naturalHeight", { configurable: true, value: height });
  act(() => { image.dispatchEvent(new Event("load")); });
}

/** Simulate decoded pixels, never fetch an image or use a real browser canvas. */
function enablePixelDecoding() {
  globalThis.Image = class {
    naturalWidth = 4;
    naturalHeight = 4;
    sample = 0;
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    set src(value: string) {
      this.sample = value.includes("bright") ? 255 : 0;
      if (value.includes("wide")) this.naturalWidth = 8;
      queueMicrotask(() => this.onload?.());
    }
  } as unknown as typeof Image;
  HTMLCanvasElement.prototype.getContext = (() => {
    let image: { sample: number; naturalWidth: number; naturalHeight: number };
    return {
      drawImage: (value: typeof image) => { image = value; },
      getImageData: () => ({
        data: new Uint8ClampedArray(image.naturalWidth * image.naturalHeight * 4).fill(image.sample),
      }),
    };
  }) as unknown as typeof originalContext;
}

function render(element: React.ReactElement): void {
  act(() => {
    root = createRoot(container);
    root.render(element);
  });
}

function frame(
  key: string,
  phase: TraceFrame["phase"],
  dataUrl = "data:image/jpeg;base64,AAAA",
): TraceFrame {
  return { key, tsMs: 1, phase, dataUrl, width: 1000, height: 600 };
}

function run(overrides: Partial<TraceRun> = {}): TraceRun {
  return {
    schema: TRACE_SCHEMA,
    startedAtMs: 0,
    endedAtMs: 7090,
    elapsedMs: 7090,
    url: "https://example.com/",
    task: "Find a flight",
    steps: [
      {
        i: 1,
        tsStartMs: 0,
        tsEndMs: 341,
        durMs: 341,
        kind: "tool",
        action: "browser_click",
        status: "complete",
        target: { label: "Where from?" },
        pageChanged: true,
        frameKey: "after-1",
        frameKeyBefore: "before-1",
        correlationId: "t1",
      },
      {
        i: 2,
        tsStartMs: 400,
        tsEndMs: 800,
        durMs: 400,
        kind: "tool",
        action: "browser_execute",
        status: "error",
        pageChanged: false,
        correlationId: "t2",
      },
    ],
    frames: [],
    metrics: {
      stepCount: 2,
      toolMs: 741,
      gapMs: 6349,
      changedSteps: 1,
      wastedSteps: 1,
    },
    ...overrides,
  };
}

describe("Viewport", () => {
  test("renders the placeholder when there is no frame", () => {
    render(<Viewport frame={null} url="https://example.com/" placeholder="no picture" />);

    expect(container.textContent).toContain("no picture");
    expect(container.textContent).toContain("https://example.com/");
    expect(container.querySelector("img")).toBeNull();
  });

  test("scales overlays using decoded image pixels rather than viewport metadata", () => {
    render(
      <Viewport
        frame={frame("after-1", "after")}
        url="https://example.com/"
        overlays={[{ kind: "changed", rect: { x: 100, y: 150, w: 500, h: 300 } }]}
      />,
    );

    expect(container.querySelector("img")?.getAttribute("src")).toContain("data:image/jpeg");
    expect(container.querySelector(".border-amber-400")).toBeNull();
    loadDisplayedImage(2000, 1200);
    const overlay = container.querySelector(".border-amber-400") as HTMLElement | null;
    expect(overlay).not.toBeNull();
    expect(overlay!.style.left).toBe("5%");
    expect(overlay!.style.width).toBe("25%");
    expect(overlay!.style.top).toBe("12.5%");
    expect(overlay!.style.height).toBe("25%");
  });

  test("unknown viewport dimensions use the image size once decoded", () => {
    render(
      <Viewport
        frame={{ ...frame("after-1", "after"), width: 0, height: 0 }}
        overlays={[{ kind: "changed", rect: { x: 1, y: 1, w: 2, h: 2 } }]}
      />,
    );

    expect(container.querySelector(".border-amber-400")).toBeNull();
    loadDisplayedImage(100, 100);
    expect(container.querySelector(".border-amber-400")).not.toBeNull();
  });
});

describe("TraceView", () => {
  test("shows the run summary and every step", () => {
    const frames = createBufferedFrameSource();
    render(<TraceView run={run()} frameSource={frames} />);

    const text = container.textContent ?? "";
    expect(text).toContain("7.09 s");
    expect(text).toContain("browser_click");
    expect(text).toContain("browser_execute");
    expect(text).toContain("341 ms");
    expect(text).toContain("400 ms");
  });

  test("renders the newest frame before decoding a diff", () => {
    const frames = createBufferedFrameSource();
    frames.push(frame("after-1", "after"));

    render(<TraceView run={run()} frameSource={frames} />);

    expect(container.querySelector("img")?.getAttribute("src")).toContain("data:image/jpeg");
  });

  test("shows the selected step's detail and marks the running one", () => {
    const frames = createBufferedFrameSource();
    const withRunning = run({
      endedAtMs: null,
      steps: [
        ...run().steps,
        {
          i: 3,
          tsStartMs: 900,
          tsEndMs: null,
          durMs: null,
          kind: "tool",
          action: "browser_read",
          status: "running",
          pageChanged: null,
        },
      ],
    });

    render(<TraceView run={withRunning} frameSource={frames} />);

    // The last step is selected by default, so its detail is on screen.
    expect(container.textContent).toContain("step 3");
    expect(container.textContent).toContain("live");
  });

  test("an empty run explains itself instead of rendering nothing", () => {
    const frames = createBufferedFrameSource();
    render(
      <TraceView
        run={run({ steps: [], metrics: { stepCount: 0, toolMs: 0, gapMs: 0, changedSteps: 0, wastedSteps: 0 } })}
        frameSource={frames}
      />,
    );

    expect(container.textContent).toContain("Steps appear here as the agent acts");
  });

  test("selecting a step swaps the detail via the timeline", () => {
    const frames = createBufferedFrameSource();
    render(<TraceView run={run()} frameSource={frames} />);

    const buttons = Array.from(container.querySelectorAll("li button"));
    expect(buttons).toHaveLength(2);
    act(() => {
      (buttons[0] as HTMLButtonElement).click();
    });

    expect(container.textContent).toContain("step 1");
    expect(container.textContent).toContain("target: Where from?");
    expect(container.textContent).toContain("page changed");
  });

  test("an unavailable canvas produces no page-change verdict", async () => {
    const frames = createBufferedFrameSource();
    frames.push(frame("before-1", "before"));
    frames.push(frame("after-1", "after", "data:image/jpeg;base64,BBBB"));
    const seen: boolean[] = [];
    await act(async () => {
      root = createRoot(container);
      root.render(<TraceView run={run({ steps: [run().steps[0]!], runId: "no-canvas" })}
        frameSource={frames} onPageChange={(_id, changed) => seen.push(changed)} />);
    });
    expect(seen).toEqual([]);
    expect(container.textContent).toContain("comparison unavailable");
  });

  for (const [sample, verdict] of [["dark", false], ["bright", true]] as const) {
    test(`reports ${verdict} only after a successful comparison`, async () => {
      enablePixelDecoding();
      const frames = createBufferedFrameSource();
      frames.push(frame("before-1", "before", "data:image/png;base64,comparison-before-dark"));
      frames.push(frame("after-1", "after", `data:image/png;base64,${sample}-after-${sample}`));
      const seen: Array<[string, boolean, string | undefined]> = [];
      await act(async () => {
        root = createRoot(container);
        root.render(<TraceView run={run({ steps: [run().steps[0]!], runId: `comparison-${sample}` })}
          frameSource={frames} onPageChange={(id, changed, runId) => seen.push([id, changed, runId])} />);
      });
      expect(seen).toEqual([["t1", verdict, `comparison-${sample}`]]);
    });
  }

  test("different decoded dimensions are unavailable rather than unchanged", async () => {
    enablePixelDecoding();
    const frames = createBufferedFrameSource();
    frames.push(frame("before-1", "before", "data:image/png;base64,size-dark"));
    frames.push(frame("after-1", "after", "data:image/png;base64,size-wide"));
    const seen: boolean[] = [];
    await act(async () => {
      root = createRoot(container);
      root.render(<TraceView run={run({ steps: [run().steps[0]!] })}
        frameSource={frames} onPageChange={(_id, value) => seen.push(value)} />);
    });
    expect(seen).toEqual([]);
    expect(container.textContent).toContain("different sizes");
  });

  test("a new run in the same millisecond resets the selected step", async () => {
    const frames = createBufferedFrameSource();
    render(<TraceView run={run({ runId: "old" })} frameSource={frames} />);
    act(() => { (container.querySelector("li button") as HTMLButtonElement).click(); });
    expect(container.textContent).toContain("step 1");
    await act(async () => {
      root.render(<TraceView run={run({ runId: "new" })} frameSource={frames} />);
    });
    expect(container.textContent).toContain("step 2");
  });
});
