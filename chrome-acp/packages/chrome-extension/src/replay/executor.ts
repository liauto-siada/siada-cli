// Deterministic replay executor: locate an element from a recorded
// TrajectoryTarget and perform one pipeline step, then summarize the DOM
// response. Pure DOM logic — runs both in unit tests (happy-dom) and inside
// the injected page script (replay/inject.ts).

import { summarizeMutations } from "../recorder/mutation-summary";
import type { ReplayStep, TrajectoryTarget } from "@chrome-acp/shared/acp";

export interface ReplayResult {
  ok: boolean;
  error?: string;
  response?: string;
  url: string;
}

export interface RunOptions {
  /** How long to collect DOM changes after the action (default 600ms) */
  responseWaitMs?: number;
}

function normalizeText(s: string | null | undefined): string {
  return (s ?? "").replace(/\s+/g, " ").trim();
}

// Minimal resolver for the absolute tag-path xpaths our recorder generates
// (e.g. "/html/body/div[2]/span"). Avoids relying on document.evaluate,
// which is unavailable in some environments and overkill for this grammar.
function findByXPath(doc: Document, xpath: string): Element | null {
  const segments = xpath.split("/").filter(Boolean);
  if (segments.length === 0) return null;

  let current: Element | null = doc.documentElement;
  const first = segments.shift()!;
  if (!segmentMatches(current, first)) return null;

  for (const segment of segments) {
    const { tag, position } = parseSegment(segment);
    if (!tag || !current) return null;
    const parent: Element = current;
    const matches: Element[] = Array.from(parent.children).filter(
      (child) => child.tagName.toLowerCase() === tag,
    );
    current = matches[position - 1] ?? null;
    if (!current) return null;
  }
  return current;
}

function parseSegment(segment: string): { tag: string | null; position: number } {
  const match = /^([a-zA-Z][\w-]*)(?:\[(\d+)\])?$/.exec(segment);
  if (!match) return { tag: null, position: 1 };
  return { tag: match[1]!.toLowerCase(), position: match[2] ? Number(match[2]) : 1 };
}

function segmentMatches(el: Element | null, segment: string): boolean {
  if (!el) return false;
  const { tag } = parseSegment(segment);
  return tag !== null && el.tagName.toLowerCase() === tag;
}

function findByText(
  doc: Document,
  target: TrajectoryTarget,
): Element | null {
  if (!target.text) return null;
  const wanted = normalizeText(target.text);
  const candidates = doc.getElementsByTagName(target.tag || "*");
  for (const el of Array.from(candidates)) {
    if (normalizeText(el.textContent) === wanted) return el;
  }
  return null;
}

// Location priority: css selector -> xpath -> visible text on matching tag.
export function findElementByTarget(
  doc: Document,
  target: TrajectoryTarget,
): Element | null {
  if (target.selector) {
    try {
      const el = doc.querySelector(target.selector);
      if (el) return el;
    } catch {
      // invalid selector, keep falling back
    }
  }
  if (target.xpath) {
    const el = findByXPath(doc, target.xpath);
    if (el) return el;
  }
  return findByText(doc, target);
}

function dispatchMouseClick(el: Element) {
  el.dispatchEvent(
    new MouseEvent("click", { bubbles: true, cancelable: true, view: window }),
  );
}

// React/Vue-compatible value setting: use the native setter so framework
// trackers see a "real" change, then fire input + change.
function setNativeValue(el: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const proto = Object.getPrototypeOf(el);
  const descriptor = Object.getOwnPropertyDescriptor(proto, "value");
  descriptor?.set?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

export function performAction(
  el: Element | null,
  step: Pick<ReplayStep, "kind" | "value" | "key" | "url" | "scrollX" | "scrollY">,
): void {
  switch (step.kind) {
    case "click":
      (el as HTMLElement).scrollIntoView({ block: "center" });
      dispatchMouseClick(el!);
      break;
    case "input":
      if (el instanceof HTMLInputElement && el.type === "checkbox") {
        const wanted = step.value === "true";
        if (el.checked !== wanted) {
          el.checked = wanted;
          el.dispatchEvent(new Event("change", { bubbles: true }));
        }
      } else if (
        el instanceof HTMLInputElement ||
        el instanceof HTMLTextAreaElement
      ) {
        el.focus();
        setNativeValue(el, step.value ?? "");
      }
      break;
    case "select":
      if (el instanceof HTMLSelectElement) {
        el.value = step.value ?? "";
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }
      break;
    case "keydown":
      (el ?? document.activeElement)?.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: step.key ?? "Enter",
          bubbles: true,
          cancelable: true,
        }),
      );
      break;
    case "scroll":
      window.scrollTo(step.scrollX ?? 0, step.scrollY ?? 0);
      break;
    case "navigate":
      if (step.url) window.location.href = step.url;
      break;
  }
}

// Execute one replay step and summarize the DOM changes it triggers.
export async function runReplayStep(
  step: ReplayStep,
  options: RunOptions = {},
): Promise<ReplayResult> {
  const responseWaitMs = options.responseWaitMs ?? 600;

  let el: Element | null = null;
  if (step.kind !== "scroll" && step.kind !== "navigate") {
    if (!step.target) {
      return { ok: false, error: "missing_target", url: location.href };
    }
    el = findElementByTarget(document, step.target);
    if (!el) {
      return { ok: false, error: "element_not_found", url: location.href };
    }
  }

  const mutations: MutationRecord[] = [];
  const observer = new MutationObserver((records) => mutations.push(...records));
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    characterData: true,
  });

  try {
    performAction(el, step);
  } catch (error) {
    observer.disconnect();
    return { ok: false, error: (error as Error).message, url: location.href };
  }

  await new Promise((resolve) => setTimeout(resolve, responseWaitMs));
  observer.disconnect();

  const response = summarizeMutations(mutations);
  return {
    ok: true,
    url: location.href,
    ...(response ? { response } : {}),
  };
}
