// Semantic summarizer for DOM mutations.
// Inspired by rrweb's MutationBuffer, but instead of replay-ready serialized
// mutations it produces a short human/LLM-readable Chinese summary describing
// what changed on the page in response to a user action.

import { briefNode } from "./selector";

export interface MutationSummaryOptions {
  /** Max distinct change lines (default 5) */
  maxItems?: number;
  /** Max total characters (default 200) */
  maxLength?: number;
}

const IGNORED_TAGS = new Set(["script", "style", "noscript"]);

function isElementNode(node: Node): node is Element {
  return node.nodeType === Node.ELEMENT_NODE;
}

function isIgnorable(node: Node): boolean {
  if (isElementNode(node)) {
    const el = node as Element;
    return (
      IGNORED_TAGS.has(el.tagName.toLowerCase()) ||
      el.closest("script, style, noscript") !== null
    );
  }
  if (node.nodeType === Node.TEXT_NODE) {
    // Whitespace-only text carries no semantics
    return !(node.textContent ?? "").trim();
  }
  // Comments and other node types are not meaningful for trajectories
  return true;
}

export function summarizeMutations(
  mutations: MutationRecord[],
  options: MutationSummaryOptions = {},
): string {
  const maxItems = options.maxItems ?? 5;
  const maxLength = options.maxLength ?? 200;

  const lines: string[] = [];
  const seen = new Set<string>();
  let overflow = 0;

  const push = (line: string) => {
    if (seen.has(line)) return;
    seen.add(line);
    if (lines.length < maxItems) {
      lines.push(line);
    } else {
      overflow++;
    }
  };

  for (const mutation of mutations) {
    if (isIgnorable(mutation.target)) continue;

    if (mutation.type === "childList") {
      for (const node of Array.from(mutation.addedNodes)) {
        if (!isIgnorable(node)) push(`新增: ${briefNode(node)}`);
      }
      for (const node of Array.from(mutation.removedNodes)) {
        if (!isIgnorable(node)) push(`移除: ${briefNode(node)}`);
      }
    } else if (mutation.type === "attributes" && mutation.attributeName) {
      push(`属性变化: ${briefNode(mutation.target)} 的 ${mutation.attributeName}`);
    } else if (mutation.type === "characterData") {
      push(`文本变化: ${briefNode(mutation.target)}`);
    }
  }

  let summary = lines.join("；");
  if (overflow > 0) summary += `；等 ${overflow} 处变化`;

  if (summary.length > maxLength) {
    summary = summary.slice(0, maxLength) + "…";
  }
  return summary;
}
