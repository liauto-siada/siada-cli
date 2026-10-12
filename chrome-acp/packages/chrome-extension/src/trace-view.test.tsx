// Render tests for the browser-activity viewer. The diff hook needs a canvas
// (absent under happy-dom), which is exactly the code path worth pinning: it
// must degrade to "no overlays" rather than crash the panel. The cases that
// need a real comparison stub the pixel path (see stubPixelPath below) instead
// of asserting around it.

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

beforeEach(() => {
  document.body.innerHTML = "";
  container = document.createElement("div");
  document.body.append(container);
});

afterEach(() => {
  // Unmount so effects from one case (diff decoding, frame subscriptions) do
  // not keep running into the next one.
  act(() => {
    root?.unmount();
  });
});

function render(element: React.ReactElement): void {
  act(() => {
    root = createRoot(container);
    root.render(element);
  });
}

/**
 * Give the rendered picture the pixel size it would decode to. The reported
 * frame metadata (1000x600 in `frame()` below) is deliberately different: the
 * viewer must use the picture's own pixels for geometry.
 */
function reportPictureSize(image: HTMLImageElement, width: number, height: number): void {
  Object.defineProperty(image, "naturalWidth", { value: width, configurable: true });
  Object.defineProperty(image, "naturalHeight", { value: height, configurable: true });
  act(() => {
    image.dispatchEvent(new Event("load", { bubbles: true }));
  });
}

/**
 * happy-dom has neither a 2D canvas nor images that deliver pixels, so the
 * comparison path is stubbed to test what the view does with a real diff:
 * `paints` is the flat grey value each decoded frame gets, in decode order.
 * Pictures load in a microtask by default; hold() parks the load events of
 * pictures requested from then on until release() delivers them, so a test can
 * inspect the view while a pair is still being compared.
 */
function stubPixelPathWith(paints: number[]): {
  hold: () => void;
  release: () => void;
  restore: () => void;
} {
  const originalImage = (globalThis as { Image: unknown }).Image;
  const pending = [...paints];
  const waiting: Array<() => void> = [];
  let holding = false;
  class FakeImage {
    onload: (() => void) | null = null;
    onerror: (() => void) | null = null;
    naturalWidth = 100;
    naturalHeight = 50;
    set src(_value: string) {
      const fire = () => this.onload?.();
      if (holding) waiting.push(fire);
      else queueMicrotask(fire);
    }
  }
  (globalThis as { Image: unknown }).Image = FakeImage;

  const proto = HTMLCanvasElement.prototype as unknown as {
    getContext: (...args: unknown[]) => unknown;
  };
  const originalGetContext = proto.getContext;
  proto.getContext = () => ({
    drawImage: () => {},
    getImageData: (_x: number, _y: number, width: number, height: number) => {
      const paint = pending.shift() ?? 0;
      const data = new Uint8ClampedArray(width * height * 4);
      for (let i = 0; i < data.length; i += 4) {
        data[i] = paint;
        data[i + 1] = paint;
        data[i + 2] = paint;
        data[i + 3] = 255;
      }
      return { data, width, height };
    },
  });

  return {
    hold: () => {
      holding = true;
    },
    release: () => {
      for (const fire of waiting.splice(0)) fire();
    },
    restore: () => {
      (globalThis as { Image: unknown }).Image = originalImage;
      proto.getContext = originalGetContext;
    },
  };
}

/** The always-loading variant used by most tests. */
function stubPixelPath(paints: number[]): () => void {
  return stubPixelPathWith(paints).restore;
}

/** Let the async decode/diff chain settle before asserting. */
async function settleDiff(): Promise<void> {
  await act(async () => {
    for (let tick = 0; tick < 8; tick += 1) await Promise.resolve();
  });
}

function frame(
  key: string,
  phase: TraceFrame["phase"],
  dataUrl = "data:image/jpeg;base64,AAAA",
): TraceFrame {
  return { key, tsMs: 1, phase, dataUrl, width: 1000, height: 600 };
}

// Each call mints a fresh run id, the way beginRun() does, so re-rendering
// with a new `run()` models a new run even when the timestamps coincide.
let runSeq = 0;

function run(overrides: Partial<TraceRun> = {}): TraceRun {
  runSeq += 1;
  return {
    schema: TRACE_SCHEMA,
    runId: `test-run-${runSeq}`,
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

/** Click a step in the timeline (the panel selects the last step by default). */
function selectStep(index: number): void {
  const buttons = Array.from(container.querySelectorAll("li button"));
  act(() => {
    (buttons[index] as HTMLButtonElement).click();
  });
}

/** The default run with step 1 pointing at this pair of pictures. */
function runWithStepPictures(beforeKey: string, afterKey: string): TraceRun {
  const base = run();
  return run({
    steps: base.steps.map((step) =>
      step.i === 1 ? { ...step, frameKey: afterKey, frameKeyBefore: beforeKey } : step,
    ),
  });
}

/**
 * A one-step run whose only step owns the given pair, so the default selection
 * (the last step) is the step with the pictures. That keeps re-renders that
 * change the run under comparison free of extra clicks.
 */
function oneStepRunWithPictures(
  beforeKey: string,
  afterKey: string,
  overrides: Partial<TraceRun> = {},
): TraceRun {
  const base = run();
  return run({
    steps: [
      {
        ...base.steps[0]!,
        pageChanged: null,
        frameKeyBefore: beforeKey,
        frameKey: afterKey,
      },
    ],
    metrics: { stepCount: 1, toolMs: 341, gapMs: 6_749, changedSteps: 0, wastedSteps: 0 },
    ...overrides,
  });
}

describe("Viewport", () => {
  test("renders the placeholder when there is no frame", () => {
    render(<Viewport frame={null} url="https://example.com/" placeholder="no picture" />);

    expect(container.textContent).toContain("no picture");
    expect(container.textContent).toContain("https://example.com/");
    expect(container.querySelector("img")).toBeNull();
  });

  test("scales overlays by the picture's own pixels, not the reported viewport size", () => {
    // The frame reports 1000x600 CSS pixels while the picture itself decoded to
    // 2240x1560 (device pixel ratio, capture limits). The overlay is in the
    // picture's pixel space, so it has to be scaled by the picture.
    render(
      <Viewport
        frame={frame("after-1", "after")}
        url="https://example.com/"
        overlays={[{ kind: "changed", rect: { x: 224, y: 390, w: 1120, h: 780 } }]}
      />,
    );
    reportPictureSize(container.querySelector("img")!, 2240, 1560);

    const overlay = container.querySelector(".border-amber-400") as HTMLElement | null;
    expect(overlay).not.toBeNull();
    // 224/2240 -> 10%, 1120/2240 -> 50%, 390/1560 -> 25%, 780/1560 -> 50%
    expect(overlay!.style.left).toBe("10%");
    expect(overlay!.style.width).toBe("50%");
    expect(overlay!.style.top).toBe("25%");
    expect(overlay!.style.height).toBe("50%");
  });

  test("does not draw overlays until the picture's pixel size is known", () => {
    render(
      <Viewport
        frame={frame("after-1", "after")}
        overlays={[{ kind: "changed", rect: { x: 1, y: 1, w: 2, h: 2 } }]}
      />,
    );
    // The reported metadata is not enough to place anything.
    expect(container.querySelector(".border-amber-400")).toBeNull();

    reportPictureSize(container.querySelector("img")!, 1000, 600);
    expect(container.querySelector(".border-amber-400")).not.toBeNull();
  });

  test("says so when the captured picture cannot be displayed", () => {
    render(<Viewport frame={frame("after-1", "after")} placeholder="no picture" />);

    const image = container.querySelector("img")!;
    act(() => {
      image.dispatchEvent(new Event("error", { bubbles: true }));
    });

    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("This captured picture could not be displayed.");
  });

  test("shows the picture's provenance next to the title", () => {
    render(
      <Viewport
        frame={frame("after-1", "after")}
        title="Example page"
        note="latest picture, not linked to a step"
      />,
    );

    expect(container.textContent).toContain("Example page");
    expect(container.textContent).toContain("latest picture, not linked to a step");
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

  test("a new run drops the step selected in the previous one", () => {
    const frames = createBufferedFrameSource();
    render(<TraceView run={run()} frameSource={frames} />);

    const buttons = Array.from(container.querySelectorAll("li button"));
    act(() => {
      (buttons[1] as HTMLButtonElement).click();
    });
    expect(container.textContent).toContain("step 2");

    // beginRun() mints a new runId, so the panel gets a new run whose first
    // step is the only one: the stale index must not blank the detail panel.
    const next = run({ startedAtMs: 5_000, steps: [run().steps[0]!] });
    act(() => {
      root.render(<TraceView run={next} frameSource={frames} />);
    });

    expect(container.textContent).toContain("step 1");
    expect(container.textContent).not.toContain("Select a step to inspect");
  });

  test("a new run that begins in the same millisecond still drops the previous selection", () => {
    const frames = createBufferedFrameSource();
    render(<TraceView run={run({ runId: "run-a" })} frameSource={frames} />);

    selectStep(1);
    expect(container.textContent).toContain("step 2");

    // Same startedAtMs, new runId: the panel must still know this is a
    // different run, or the index selected above would point at step 2 of a
    // run that only has step 1 — and blank the detail panel.
    const next = run({ runId: "run-b", steps: [run().steps[0]!] });
    act(() => {
      root.render(<TraceView run={next} frameSource={frames} />);
    });

    expect(container.textContent).toContain("step 1");
    expect(container.textContent).not.toContain("Select a step to inspect");
    expect(container.textContent).not.toContain("step 2");
  });

  test("renders trace text as text, never as markup", () => {
    const frames = createBufferedFrameSource();
    const injected = run({
      steps: [
        {
          i: 1,
          tsStartMs: 0,
          tsEndMs: 12,
          durMs: 12,
          kind: "tool",
          action: '<img src=x onerror="globalThis.__tracePwned = true">browser_click',
          status: "complete",
          target: { label: "<script>globalThis.__tracePwned = true</script>" },
          value: "<b>typed</b>",
          pageChanged: true,
        },
      ],
    });

    render(<TraceView run={injected} frameSource={frames} />);

    // The agent (and the page) decide what goes into these strings, so they
    // must stay inert: shown verbatim, never parsed into nodes or executed.
    expect(container.textContent).toContain("<img src=x");
    expect(container.textContent).toContain("<b>typed</b>");
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect((globalThis as { __tracePwned?: boolean }).__tracePwned).toBeUndefined();
  });

  test("says the newest picture is not tied to a step instead of implying it is", () => {
    const frames = createBufferedFrameSource();
    // The run's frames belong to no step here (the capture channel numbers its
    // calls differently), so the stage shows the newest one — and says so.
    frames.push(frame("latest-1", "after"));

    render(<TraceView run={run()} frameSource={frames} />);

    expect(container.textContent).toContain("latest picture, not linked to a step");
  });

  test("states that the change overlay could not be computed, without claiming 'no change'", async () => {
    const frames = createBufferedFrameSource();
    frames.push(frame("before-1", "before"));
    frames.push(frame("after-1", "after"));

    render(<TraceView run={run()} frameSource={frames} />);
    selectStep(0);
    await settleDiff();

    // happy-dom provides no 2D canvas, so the pair cannot be compared; the
    // viewer has to say that instead of reporting "no changed areas".
    expect(container.textContent).toContain("change overlay unavailable");
    expect(container.textContent).toContain("no 2D canvas");
    expect(container.textContent).not.toContain("none found above the diff threshold");
  });

  test("says so when a step has no linked before/after pair", () => {
    const frames = createBufferedFrameSource();
    const noPictures = run({
      steps: run().steps.map((step) => ({
        ...step,
        frameKey: undefined,
        frameKeyBefore: undefined,
      })),
    });

    render(<TraceView run={noPictures} frameSource={frames} />);

    expect(container.textContent).toContain(
      "no before/after picture pair is linked to this step",
    );
  });

  test("phrases a pixel verdict as a threshold observation, not as 'the page did not change'", () => {
    const frames = createBufferedFrameSource();
    render(<TraceView run={run()} frameSource={frames} />);

    selectStep(0);
    expect(container.textContent).toContain("page changed");

    selectStep(1);
    expect(container.textContent).toContain("page diff: no change above threshold");
    expect(container.textContent).not.toContain("page unchanged");
  });

  test("does not turn an unobserved page change into a zero", () => {
    const frames = createBufferedFrameSource();
    render(
      <TraceView
        run={run({
          metrics: {
            stepCount: 0,
            toolMs: 0,
            gapMs: 0,
            changedSteps: 0,
            wastedSteps: 0,
          },
        })}
        frameSource={frames}
      />,
    );

    const noChange = Array.from(container.querySelectorAll("dl > div")).find((row) =>
      row.textContent?.startsWith("no change"),
    );
    // Nothing was compared, so the metric must not read as a verified zero.
    expect(noChange?.textContent).toContain("—");
  });
});

describe("TraceView page-change evidence", () => {
  test("reports the verdict of a real comparison and offers its overlays", async () => {
    const restore = stubPixelPath([0, 255]);
    try {
      const frames = createBufferedFrameSource();
      frames.push(frame("before-a", "before"));
      frames.push(frame("after-a", "after"));
      const reported: Array<[string, boolean]> = [];

      render(
        <TraceView
          run={runWithStepPictures("before-a", "after-a")}
          frameSource={frames}
          onPageChange={(correlationId, changed) =>
            reported.push([correlationId, changed])
          }
        />,
      );
      selectStep(0);
      await settleDiff();

      // Step 1's own pair differs (grey -> white), so the comparison found a
      // changed region and the viewer reports exactly that verdict.
      expect(reported).toEqual([["t1", true]]);
      expect(container.textContent).toContain("1 changed area");

      // The overlay is placed in the picture's pixels (the stubbed decode is
      // 100x50), scaled by the picture's own size.
      reportPictureSize(container.querySelector("img")!, 100, 50);
      expect(container.querySelector(".border-amber-400")).not.toBeNull();
    } finally {
      restore();
    }
  });

  test("drops the previous selection's overlays instead of leaving them on the new picture", async () => {
    const restore = stubPixelPath([0, 255]);
    try {
      const frames = createBufferedFrameSource();
      frames.push(frame("before-b", "before"));
      frames.push(frame("after-b", "after"));

      render(<TraceView run={runWithStepPictures("before-b", "after-b")} frameSource={frames} />);
      selectStep(0);
      await settleDiff();
      reportPictureSize(container.querySelector("img")!, 100, 50);
      expect(container.querySelector(".border-amber-400")).not.toBeNull();

      // Step 2 has no pictures at all: the overlay of step 1 must not stay on
      // the picture that is still on screen.
      selectStep(1);

      expect(container.querySelector(".border-amber-400")).toBeNull();
      expect(container.textContent).toContain(
        "no before/after picture pair is linked to this step",
      );
    } finally {
      restore();
    }
  });

  test("reports a pair that shows no change as a measured not-changed", async () => {
    const restore = stubPixelPath([128, 128]);
    try {
      const frames = createBufferedFrameSource();
      frames.push(frame("before-c", "before"));
      frames.push(frame("after-c", "after"));
      const reported: Array<[string, boolean]> = [];

      render(
        <TraceView
          run={runWithStepPictures("before-c", "after-c")}
          frameSource={frames}
          onPageChange={(correlationId, changed) =>
            reported.push([correlationId, changed])
          }
        />,
      );
      selectStep(0);
      await settleDiff();

      expect(reported).toEqual([["t1", false]]);
      expect(container.textContent).toContain("none found above the diff threshold");
    } finally {
      restore();
    }
  });

  test("while the newly selected pair is still decoding, the previous pair's verdict is neither reported nor drawn", async () => {
    const stub = stubPixelPathWith([0, 255, 10, 10]);
    try {
      const frames = createBufferedFrameSource();
      frames.push(frame("before-held-a", "before"));
      frames.push(frame("after-held-a", "after"));
      frames.push(frame("before-held-b", "before"));
      frames.push(frame("after-held-b", "after"));
      const base = run();
      const withPairs = run({
        steps: [
          { ...base.steps[0]!, frameKeyBefore: "before-held-a", frameKey: "after-held-a" },
          { ...base.steps[1]!, frameKeyBefore: "before-held-b", frameKey: "after-held-b" },
        ],
      });
      const reported: Array<[string, boolean]> = [];

      render(
        <TraceView
          run={withPairs}
          frameSource={frames}
          onPageChange={(correlationId, changed) =>
            reported.push([correlationId, changed])
          }
        />,
      );

      // The default selection is step 2; its pair compares (grey -> white) and
      // its verdict is reported and drawn.
      await settleDiff();
      expect(reported).toEqual([["t2", true]]);
      reportPictureSize(container.querySelector("img")!, 100, 50);
      expect(container.querySelector(".border-amber-400")).not.toBeNull();

      // From here the stub parks picture loads, so selecting step 1 starts a
      // comparison that stays in flight.
      stub.hold();
      selectStep(0);

      // Step 1's pair has not been compared yet. Step 2's verdict and overlays
      // describe other pictures, so neither may be shown as step 1's state, and
      // no change may be reported for a comparison that has not happened.
      expect(container.textContent).toContain("comparing this step's before/after pictures");
      expect(container.textContent).not.toContain("changed area");
      expect(container.querySelector(".border-amber-400")).toBeNull();
      expect(reported).toEqual([["t2", true]]);

      act(() => stub.release());
      await settleDiff();
      expect(reported).toEqual([["t2", true], ["t1", false]]);
      expect(container.textContent).toContain("none found above the diff threshold");
    } finally {
      stub.restore();
    }
  });

  test("a new run reusing the same frame keys and correlation id re-decodes and reports its own verdict", async () => {
    const restore = stubPixelPath([0, 255, 10, 10]);
    try {
      const sourceA = createBufferedFrameSource();
      sourceA.push(frame("before-1", "before", "data:image/jpeg;base64,AAA1"));
      sourceA.push(frame("after-1", "after", "data:image/jpeg;base64,AAA2"));
      const reported: Array<[string, boolean]> = [];
      const onPageChange = (correlationId: string, changed: boolean) =>
        reported.push([correlationId, changed]);

      render(
        <TraceView
          run={oneStepRunWithPictures("before-1", "after-1", { runId: "run-a" })}
          frameSource={sourceA}
          onPageChange={onPageChange}
        />,
      );
      await settleDiff();
      expect(reported).toEqual([["t1", true]]);
      reportPictureSize(container.querySelector("img")!, 100, 50);
      expect(container.querySelector(".border-amber-400")).not.toBeNull();

      // A new run in the same millisecond reuses the step's correlation id and
      // the frame keys, but its pictures are different bytes: the old pixels
      // and the old report are not this run's evidence. The pair must be
      // decoded again and the fresh verdict reported, not suppressed.
      const sourceB = createBufferedFrameSource();
      sourceB.push(frame("before-1", "before", "data:image/jpeg;base64,BBB1"));
      sourceB.push(frame("after-1", "after", "data:image/jpeg;base64,BBB2"));
      act(() => {
        root.render(
          <TraceView
            run={oneStepRunWithPictures("before-1", "after-1", { runId: "run-b" })}
            frameSource={sourceB}
            onPageChange={onPageChange}
          />,
        );
      });
      await settleDiff();

      expect(reported).toEqual([["t1", true], ["t1", false]]);
      expect(container.textContent).toContain("none found above the diff threshold");
      expect(container.textContent).not.toContain("changed area");
    } finally {
      restore();
    }
  });
});
