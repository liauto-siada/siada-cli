// User action listeners for trajectory recording.
// Thin DOM-event wiring; all element description/masking logic lives in the
// pure modules (selector.ts / mask.ts).

import { describeTarget } from "./selector";
import { getRecordableValue } from "./mask";
import type { TrajectoryActionEvent } from "@chrome-acp/shared/acp";

export type ActionCallback = (event: TrajectoryActionEvent) => void;

const SCROLL_THROTTLE_MS = 500;

function toElement(target: EventTarget | null): Element | null {
  if (!target) return null;
  if (target instanceof Element) return target;
  if (target instanceof Node) return target.parentElement;
  return null;
}

// Register listeners; returns a cleanup function removing them all.
export function setupActionListeners(onAction: ActionCallback): () => void {
  const emit = (
    kind: TrajectoryActionEvent["action"]["kind"],
    el: Element | null,
    extra: Partial<TrajectoryActionEvent["action"]> = {},
  ) => {
    try {
      // [STEP 2] scroll is throttled but still noisy; skip it in the trace log
      if (kind !== "scroll") {
        console.log(
          `[STEP 2] content-script captured action: kind=${kind} url=${location.href}` +
            (extra.value !== undefined ? ` value=${JSON.stringify(String(extra.value)).slice(0, 80)}` : "") +
            (extra.key !== undefined ? ` key=${extra.key}` : ""),
        );
      }
      onAction({
        ts: Date.now(),
        type: "action",
        url: location.href,
        title: document.title,
        action: {
          kind,
          ...(el ? { target: describeTarget(el) } : {}),
          ...extra,
        },
      });
    } catch {
      // Recording must never break the page
    }
  };

  const onClick = (e: Event) => {
    const el = toElement(e.target);
    if (el) emit("click", el);
  };

  const onChange = (e: Event) => {
    const el = toElement(e.target);
    if (!el) return;
    if (el instanceof HTMLSelectElement) {
      emit("select", el, { value: getRecordableValue(el) });
    } else if (
      el instanceof HTMLInputElement ||
      el instanceof HTMLTextAreaElement
    ) {
      const value =
        el instanceof HTMLInputElement && el.type === "checkbox"
          ? String(el.checked)
          : getRecordableValue(el);
      emit("input", el, { value });
    }
  };

  const onKeydown = (e: KeyboardEvent) => {
    if (e.key !== "Enter" && e.key !== "Tab") return;
    emit("keydown", toElement(e.target), { key: e.key });
  };

  let lastScroll = 0;
  const onScroll = () => {
    const now = Date.now();
    if (now - lastScroll < SCROLL_THROTTLE_MS) return;
    lastScroll = now;
    emit("scroll", null, { scrollX: window.scrollX, scrollY: window.scrollY });
  };

  document.addEventListener("click", onClick, { capture: true, passive: true });
  document.addEventListener("change", onChange, { capture: true, passive: true });
  document.addEventListener("keydown", onKeydown, { capture: true, passive: true });
  window.addEventListener("scroll", onScroll, { passive: true });

  return () => {
    document.removeEventListener("click", onClick, { capture: true });
    document.removeEventListener("change", onChange, { capture: true });
    document.removeEventListener("keydown", onKeydown, { capture: true });
    window.removeEventListener("scroll", onScroll);
  };
}
