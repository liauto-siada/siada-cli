// Input masking rules (mirrors rrweb's maskInput defaults):
// password inputs are always masked; any element can opt into masking for
// itself or its subtree via the data-acp-mask attribute.

export const MASKED_VALUE = "***";

export function shouldMaskValue(el: Element): boolean {
  if (
    el instanceof HTMLInputElement &&
    el.type.toLowerCase() === "password"
  ) {
    return true;
  }
  return el.closest("[data-acp-mask]") !== null;
}

// Value worth recording for an element, or undefined if not value-bearing.
export function getRecordableValue(el: Element): string | undefined {
  const isValueElement =
    el instanceof HTMLInputElement ||
    el instanceof HTMLTextAreaElement ||
    el instanceof HTMLSelectElement;
  if (!isValueElement) return undefined;
  if (shouldMaskValue(el)) return MASKED_VALUE;
  return el.value;
}
