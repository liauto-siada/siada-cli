// Element location & description utilities for trajectory recording.
// Simplified adaptation of rrweb's serialization goals: produce re-locatable,
// human/LLM-readable element descriptors instead of replay-ready snapshots.

import type { TrajectoryTarget } from "@chrome-acp/shared/acp";

const MAX_TEXT_LEN = 50;
const MAX_BRIEF_TEXT_LEN = 20;
const MAX_SELECTOR_DEPTH = 5;

// Minimal CSS identifier escaping (avoids relying on the CSS global).
function escapeIdent(value: string): string {
  return value.replace(/[^a-zA-Z0-9_-]/g, (ch) => `\\${ch}`);
}

function escapeAttr(value: string): string {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

// Classes that look auto-generated (e.g. css-12345) are unstable selectors.
function isStableClass(cls: string): boolean {
  return !/\d{3,}/.test(cls);
}

function stableClasses(el: Element): string[] {
  return Array.from(el.classList).filter(isStableClass).slice(0, 2);
}

// Segment like: button.btn.active or button:nth-of-type(2)
function segmentFor(el: Element): string {
  const tag = el.tagName.toLowerCase();

  const testId = el.getAttribute("data-testid");
  if (testId) return `[data-testid="${escapeAttr(testId)}"]`;

  const classes = stableClasses(el);
  let segment = tag + classes.map((c) => `.${escapeIdent(c)}`).join("");

  const parent = el.parentElement;
  if (parent) {
    const sameTag = Array.from(parent.children).filter(
      (s) => s.tagName === el.tagName,
    );
    // nth-of-type only when classes alone can't disambiguate among siblings
    const ambiguous =
      sameTag.length > 1 &&
      (classes.length === 0 ||
        sameTag.some(
          (s) =>
            s !== el &&
            stableClasses(s).join(" ") === classes.join(" "),
        ));
    if (ambiguous) {
      segment += `:nth-of-type(${sameTag.indexOf(el) + 1})`;
    }
  }
  return segment;
}

function isUnique(selector: string): boolean {
  try {
    return document.querySelectorAll(selector).length === 1;
  } catch {
    return false;
  }
}

export function getSelector(el: Element): string {
  const id = el.getAttribute("id");
  if (id) {
    return /^[a-zA-Z][\w-]*$/.test(id) ? `#${id}` : `[id="${escapeAttr(id)}"]`;
  }

  const testId = el.getAttribute("data-testid");
  if (testId) return `[data-testid="${escapeAttr(testId)}"]`;

  const segments: string[] = [];
  let current: Element | null = el;
  while (
    current &&
    current !== document.documentElement &&
    segments.length < MAX_SELECTOR_DEPTH
  ) {
    segments.unshift(segmentFor(current));

    const ancestorId = current.getAttribute("id");
    if (ancestorId && current !== el) {
      segments[0] = /^[a-zA-Z][\w-]*$/.test(ancestorId)
        ? `#${ancestorId}`
        : `[id="${escapeAttr(ancestorId)}"]`;
      break;
    }

    const candidate = segments.join(" > ");
    if (isUnique(candidate)) break;
    current = current.parentElement;
  }
  return segments.join(" > ");
}

export function getXPath(el: Element): string {
  const segments: string[] = [];
  let current: Element | null = el;
  while (current && current.nodeType === Node.ELEMENT_NODE) {
    const node: Element = current;
    const tag = node.tagName.toLowerCase();
    const parent: Element | null = node.parentElement;
    if (!parent) {
      segments.unshift(tag);
      break;
    }
    const sameTag = Array.from(parent.children).filter(
      (s) => s.tagName === node.tagName,
    );
    segments.unshift(
      sameTag.length > 1 ? `${tag}[${sameTag.indexOf(current) + 1}]` : tag,
    );
    current = parent;
  }
  return `/${segments.join("/")}`;
}

function elementText(el: Element): string {
  const raw =
    el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement
      ? el.value
      : (el.textContent ?? "");
  return raw.replace(/\s+/g, " ").trim().slice(0, MAX_TEXT_LEN);
}

export function describeTarget(el: Element): TrajectoryTarget {
  const target: TrajectoryTarget = {
    tag: el.tagName.toLowerCase(),
    selector: getSelector(el),
    xpath: getXPath(el),
  };
  const text = elementText(el);
  if (text) target.text = text;
  const role = el.getAttribute("role");
  if (role) target.role = role;
  const ariaLabel = el.getAttribute("aria-label");
  if (ariaLabel) target.ariaLabel = ariaLabel;
  return target;
}

// One-line human/LLM-readable node description, e.g. button"登录" or div.modal
export function briefNode(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = (node.textContent ?? "")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, MAX_BRIEF_TEXT_LEN);
    return `"${text}"`;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return node.nodeName.toLowerCase();

  const el = node as Element;
  const tag = el.tagName.toLowerCase();
  const text = (el.textContent ?? "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, MAX_BRIEF_TEXT_LEN);
  if (text) return `${tag}"${text}"`;
  const firstClass = stableClasses(el)[0];
  return firstClass ? `${tag}.${escapeIdent(firstClass)}` : tag;
}
