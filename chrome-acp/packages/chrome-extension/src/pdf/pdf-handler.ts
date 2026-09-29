// Default-PDF-handler for the extension: while the user toggle
// (settings.PDF_HANDLER_ENABLED_KEY) is ON, dynamic declarativeNetRequest
// rules redirect PDF navigations to the extension's vendored pdf.js viewer
// (dist/pdf/web/viewer.html), so any PDF link the user or the agent opens
// lands in a viewer tab the agent can observe (acp-bridge reports
// pagesloaded) and screenshot.
//
// The rule set is adapted from the "PDF Viewer" extension (pdf.js's official
// Chromium extension, Apache-2.0 — pdfHandler.js there). Because DNR cannot
// URL-encode the matched URL, rules redirect to `viewer.html?DNR:<rawUrl>`;
// acp-bridge.js rewrites that to an encoded `?file=` parameter before the
// viewer initializes.
//
// This module self-wires on import (background.ts imports it): applies the
// persisted state at service worker startup and follows storage changes.

import { loadPdfHandlerEnabled, PDF_HANDLER_ENABLED_KEY } from "../settings";

const RULE_ID_BASE = 4100;

function viewerUrl(): string {
  return chrome.runtime.getURL("dist/pdf/web/viewer.html");
}

function buildRules(): chrome.declarativeNetRequest.Rule[] {
  const ACTION_IGNORE_OTHER_RULES = { type: "allow" } as const;
  const ACTION_REDIRECT_TO_VIEWER = {
    type: "redirect",
    redirect: { regexSubstitution: `${viewerUrl()}?DNR:\\0` },
  } as const;

  // Same order as the reference implementation: highest priority first.
  const rules: Omit<chrome.declarativeNetRequest.Rule, "id" | "priority">[] = [
    {
      // Explicit download escape hatch (also used by pdf.js's download button
      // in extension builds).
      condition: {
        urlFilter: "pdfjs.action=download",
        resourceTypes: ["main_frame", "sub_frame"],
      },
      action: ACTION_IGNORE_OTHER_RULES,
    },
    {
      // Local PDF files. Only fires when the user granted the extension
      // "Allow access to file URLs"; otherwise Chrome's built-in viewer wins.
      condition: {
        regexFilter: "^file://.*\\.pdf([?#].*)?$",
        resourceTypes: ["main_frame", "sub_frame"],
      },
      action: ACTION_REDIRECT_TO_VIEWER,
    },
    {
      // Do not hijack intentional downloads in sub-frames.
      condition: {
        urlFilter: "*",
        resourceTypes: ["sub_frame"],
        responseHeaders: [
          { header: "content-disposition", values: ["attachment*"] },
        ],
      },
      action: ACTION_IGNORE_OTHER_RULES,
    },
    {
      // Sites like Google Drive append =download — respect attachment there.
      condition: {
        urlFilter: "=download",
        resourceTypes: ["main_frame"],
        responseHeaders: [
          { header: "content-disposition", values: ["attachment*"] },
        ],
      },
      action: ACTION_IGNORE_OTHER_RULES,
    },
    {
      // Regular http(s) PDF responses. POST responses are excluded: the
      // viewer re-fetches via GET and would lose the body.
      condition: {
        regexFilter: "^.*$",
        excludedRequestMethods: ["post"],
        resourceTypes: ["main_frame", "sub_frame"],
        responseHeaders: [
          { header: "content-type", values: ["application/pdf", "application/pdf;*"] },
        ],
      },
      action: ACTION_REDIRECT_TO_VIEWER,
    },
    {
      // Misconfigured MIME type, but the URL says PDF.
      condition: {
        regexFilter: "^.*\\.pdf\\b.*$",
        excludedRequestMethods: ["post"],
        resourceTypes: ["main_frame", "sub_frame"],
        responseHeaders: [
          { header: "content-type", values: ["application/octet-stream", "application/octet-stream;*"] },
        ],
      },
      action: ACTION_REDIRECT_TO_VIEWER,
    },
    {
      // Misconfigured MIME type, but Content-Disposition filename says PDF.
      // (excludedResponseHeaders simulates AND content-type:octet-stream.)
      condition: {
        regexFilter: "^.*$",
        excludedRequestMethods: ["post"],
        resourceTypes: ["main_frame", "sub_frame"],
        responseHeaders: [
          { header: "content-disposition", values: ["*.pdf", '*.pdf"*', "*.pdf'*"] },
        ],
        excludedResponseHeaders: [
          {
            header: "content-type",
            excludedValues: ["application/octet-stream", "application/octet-stream;*"],
          },
        ],
      },
      action: ACTION_REDIRECT_TO_VIEWER,
    },
  ];

  return rules.map((rule, i) => ({
    ...rule,
    id: RULE_ID_BASE + i,
    priority: rules.length - i,
  }));
}

export async function applyPdfHandlerRules(enabled: boolean): Promise<void> {
  const ruleIds = buildRules().map((r) => r.id);
  if (!enabled) {
    await chrome.declarativeNetRequest.updateDynamicRules({ removeRuleIds: ruleIds });
    return;
  }
  await chrome.declarativeNetRequest.updateDynamicRules({
    removeRuleIds: ruleIds,
    addRules: buildRules(),
  });
}

// Apply persisted state at startup (service workers are restarted often, and
// dynamic rules persist across restarts, so this is mostly a no-op refresh).
void loadPdfHandlerEnabled()
  .then(applyPdfHandlerRules)
  .catch((e) => console.error("[PdfHandler] failed to apply rules", e));

// Follow the sidepanel toggle.
chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local" || !(PDF_HANDLER_ENABLED_KEY in changes)) return;
  const enabled = changes[PDF_HANDLER_ENABLED_KEY].newValue === true;
  applyPdfHandlerRules(enabled).catch((e) =>
    console.error("[PdfHandler] failed to update rules", e),
  );
});
