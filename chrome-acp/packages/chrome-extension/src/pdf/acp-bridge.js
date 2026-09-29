// Bridge between the vendored pdf.js viewer and the chrome-acp extension
// background service worker.
//
// Injected into the vendored viewer.html at build time (see build.ts) as a
// CLASSIC script, before viewer.mjs: it must run before the viewer app
// initializes so it can rewrite DNR redirect URLs in time. Plain
// dependency-free file on purpose: it is copied verbatim into
// dist/pdf/web/, next to the vendored viewer assets, so it must not import
// anything.
//
// Two jobs:
// 1. DNR redirect support: declarativeNetRequest cannot URL-encode, so the
//    pdf-handler rules redirect to `viewer.html?DNR:<rawUrl>`. The viewer
//    only understands `?file=<encoded>` — rewrite and replace here before
//    viewer.mjs reads the URL.
// 2. Report viewer lifecycle events (loaded / pagechanging / documenterror)
//    to the background service worker via chrome.runtime.sendMessage, which
//    lets `browser_pdf_render` wait for a document to finish loading.
//    Outside an extension context (e.g. viewer served over plain http for
//    debugging) the reporting is a no-op.
// 3. Agent tooling for viewer tabs: chrome.scripting cannot inject into
//    chrome-extension:// pages, so the service worker routes
//    browser_read/execute/paragraphs/annotate calls for viewer tabs here via
//    chrome.tabs.sendMessage. Annotations use pdf.js's NATIVE annotation
//    editors (FreeText / Highlight), so they live in annotationStorage and
//    are embedded into the PDF by `acp_pdf_save` (app.save()).
//    On viewer tabs an annotate item's `index` is the 1-based PAGE number.

// Job 1 runs unconditionally and synchronously.
(function rewriteDnrUrl() {
  const queryString = location.search.slice(1);
  if (!queryString.startsWith("DNR:")) return;
  const rawUrl = queryString.slice(4); // not encoded — DNR cannot encode
  const target = `viewer.html?file=${encodeURIComponent(rawUrl)}${location.hash}`;
  location.replace(target);
})();

// Job 2: event reporting (extension context only).
(function () {
  const runtime = globalThis.chrome?.runtime;
  if (!runtime?.id) return;

  function post(payload) {
    try {
      runtime.sendMessage({ type: "pdf_viewer_event", ...payload }, () => {
        // Swallow "receiving end does not exist" — the background worker may
        // be asleep; event delivery is best-effort.
        void runtime.lastError;
      });
    } catch {
      // Never break the viewer because of the bridge.
    }
  }

  function hook(app) {
    const fileUrl = app.baseUrl || new URLSearchParams(location.search).get("file") || "";
    app.eventBus.on("pagesloaded", () => {
      post({
        event: "loaded",
        fileUrl,
        pages: app.pagesCount,
        title: app.documentInfo?.Title || document.title || "",
      });
    });
    app.eventBus.on("pagechanging", (evt) => {
      post({ event: "pagechanging", fileUrl, page: evt.pageNumber });
    });
    app.eventBus.on("documenterror", (evt) => {
      post({ event: "documenterror", fileUrl, message: evt.message || "failed to load document" });
    });
  }

  // This classic script runs during parsing, before the deferred viewer.mjs
  // module — poll briefly until PDFViewerApplication exists.
  let attempts = 0;
  const timer = setInterval(() => {
    const app = globalThis.PDFViewerApplication;
    if (app) {
      clearInterval(timer);
      if (app.initializedPromise) {
        app.initializedPromise.then(() => hook(app)).catch(() => hook(app));
      } else {
        hook(app);
      }
    } else if (++attempts > 200) {
      clearInterval(timer);
    }
  }, 50);
})();

// Job 3: agent tooling for viewer tabs (extension context only).
(function () {
  const runtime = globalThis.chrome?.runtime;
  if (!runtime?.id) return;

  const PAGE_TEXT_CAP = 4000;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function waitFor(cond, timeoutMs = 15000) {
    for (let i = 0; i < timeoutMs / 100; i++) {
      const v = cond();
      if (v) return v;
      await sleep(100);
    }
    return null;
  }

  const app = () => globalThis.PDFViewerApplication;
  const editorTypes = () => globalThis.pdfjsLib?.AnnotationEditorType;

  // uiManager.getEditors(pageIndex) is a GENERATOR — spread it to count.
  const editorCount = (ui, pageIndex) => [...ui.getEditors(pageIndex)].length;

  function getUiManager() {
    const a = app();
    // PDFViewer exposes its layers via the public _layerProperties getter.
    return a?.pdfViewer?._layerProperties?.annotationEditorUIManager ?? null;
  }

  // Ensure the page view is rendered; returns its AnnotationEditorLayer.
  // Rendering far-away pages via pageView.draw() directly can hang, so we
  // scroll the page into view and let the viewer render it natively.
  async function ensureEditorLayer(pageIndex) {
    const a = app();
    const pv = a?.pdfViewer?.getPageView(pageIndex);
    if (!pv) return null;
    if (pv.annotationEditorLayer?.annotationEditorLayer) {
      return pv.annotationEditorLayer.annotationEditorLayer;
    }
    a.pdfViewer.scrollPageIntoView({ pageNumber: pageIndex + 1 });
    const layer = await waitFor(
      () => pv.annotationEditorLayer?.annotationEditorLayer, 15000);
    return layer ?? null;
  }

  async function pageText(pageNumber) {
    const page = await app().pdfDocument.getPage(pageNumber);
    const tc = await page.getTextContent();
    const text = tc.items
      .map((it) => it.str + (it.hasEOL ? "\n" : ""))
      .join("")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    return text.length > PAGE_TEXT_CAP ? text.slice(0, PAGE_TEXT_CAP) + "…" : text;
  }

  async function readViewer() {
    const a = app();
    if (!a?.pdfDocument) return { error: "no document loaded" };
    return {
      url: location.href.split("#")[0],
      title: document.title,
      page: a.page,
      pages: a.pagesCount,
      text: await pageText(a.page),
    };
  }

  async function paragraphsViewer() {
    const a = app();
    if (!a?.pdfDocument) return { error: "no document loaded" };
    const n = a.pdfDocument.numPages;
    const texts = await Promise.all(
      Array.from({ length: n }, (_, i) => pageText(i + 1).catch(() => "")),
    );
    return {
      paragraphs: texts.map((text, i) => ({ index: i + 1, tag: "page", text })),
      truncated: false,
    };
  }

  // Select `target` (whitespace-insensitive) inside a rendered page's
  // textLayer. Returns true when a DOM selection was established.
  function selectTextInPage(pageIndex, target) {
    const pv = app().pdfViewer.getPageView(pageIndex);
    const spans = pv?.textLayer?.div?.querySelectorAll("span");
    if (!spans?.length) return false;

    // Concatenate text nodes with a back-map rawOffset -> {node, offset}.
    const nodes = [];
    let raw = "";
    for (const span of spans) {
      const tn = span.firstChild;
      if (tn?.nodeType === Node.TEXT_NODE) {
        nodes.push({ node: tn, start: raw.length });
        raw += tn.textContent;
      }
    }
    const at = (off) => {
      let best = nodes[0];
      for (const n of nodes) if (n.start <= off) best = n;
      return { node: best.node, offset: off - best.start };
    };
    const norm = (s) => s.replace(/\s+/g, "").toLowerCase();

    // Whitespace-insensitive substring search over the concatenated text.
    const sig = [];
    for (let i = 0; i < raw.length; i++) {
      if (!/\s/.test(raw[i])) sig.push(i);
    }
    const needle = norm(target);
    if (!needle) return false;
    const hay = sig.map((i) => raw[i].toLowerCase()).join("");
    const pos = hay.indexOf(needle);
    if (pos < 0) return false;
    const startOff = sig[pos];
    const endOff = sig[pos + needle.length - 1] + 1;

    const range = document.createRange();
    const s = at(startOff);
    const e = at(endOff);
    range.setStart(s.node, s.offset);
    range.setEnd(e.node, e.offset);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    return true;
  }

  async function annotateViewer(items, clear) {
    const a = app();
    if (!a?.pdfDocument) return { error: "no document loaded" };
    const ui = getUiManager();
    if (!ui) return { error: "annotation editors unavailable in this viewer" };

    let cleared = false;
    if (clear) {
      for (let i = 0; i < a.pdfDocument.pagesCount; i++) {
        for (const ed of [...ui.getEditors(i)]) ed.remove();
      }
      cleared = true;
    }

    let inserted = 0;
    const missing = [];
    const errors = [];

    for (const item of items) {
      if (!item || typeof item.text !== "string" || !item.text.trim()) continue;
      const pageNum = Math.max(1, Math.round(Number(item.index) || 1));
      const pageIndex = pageNum - 1;
      if (pageIndex >= a.pdfDocument.numPages) { missing.push(pageNum); continue; }

      try {
        if (item.kind === "highlight") {
          // selectTextInPage needs the page's rendered textLayer.
          if (!(await ensureEditorLayer(pageIndex))) {
            missing.push(pageNum);
            continue;
          }
          // highlightSelection in NONE mode goes through a slow async mode
          // switch (eventBus round-trip) AND that path can also clear the
          // DOM selection. Switch modes first (the switch itself may clear
          // the selection too, so build the selection after it), then
          // highlightSelection creates the editor synchronously.
          const types = editorTypes();
          const prevMode = ui.getMode?.() ?? null;
          if (prevMode === (types?.NONE ?? 0)) {
            try { await ui.updateMode(types?.HIGHLIGHT ?? 9); } catch { /* keep going */ }
          }
          const before = editorCount(ui, pageIndex);
          if (!selectTextInPage(pageIndex, item.text)) {
            errors.push(`page ${pageNum}: text not found for highlight`);
          } else {
            ui.highlightSelection("acp_bridge");
            const ok = await waitFor(
              () => editorCount(ui, pageIndex) > before, 8000);
            if (ok) inserted++;
            else errors.push(`page ${pageNum}: highlight creation timed out`);
          }
          if (prevMode === (types?.NONE ?? 0)) {
            try { await ui.updateMode(types?.NONE ?? 0); } catch { /* keep mode */ }
          }
        } else {
          // FreeText note (default). x/y/width/height are page fractions,
          // top-left origin; defaults put the note in the top-right corner.
          const layer = await ensureEditorLayer(pageIndex);
          if (!layer) { missing.push(pageNum); continue; }
          const types = editorTypes();
          const clamp01 = (v, d) => {
            const n = Number(v);
            return Number.isFinite(n) ? Math.min(1, Math.max(0, n)) : d;
          };
          const x = clamp01(item.x, 0.55);
          const y = clamp01(item.y, 0.06);
          const w = clamp01(item.width, 0.35);
          const h = clamp01(item.height, 0.14);
          const [W, H] = layer.pageDimensions;
          const data = {
            annotationType: types?.FREETEXT ?? 3,
            rect: [x * W, (1 - y - h) * H, (x + w) * W, (1 - y) * H],
            rotation: 0,
            color: Array.isArray(item.color) && item.color.length === 3
              ? item.color.map(Number)
              : (item.kind === "explanation" ? [30, 90, 200] : [190, 70, 0]),
            fontSize: Number(item.fontSize) > 0 ? Number(item.fontSize) : 12,
            value: item.text,
          };
          if (item.comment) data.comment = String(item.comment);
          const editor = await layer.deserialize(data);
          if (!editor) { errors.push(`page ${pageNum}: freetext deserialize failed`); continue; }
          // FreeTextEditor.render() only fills the text content on the
          // _isCopy / annotationElementId paths (everything else renders an
          // empty editable div). This mirrors the native findClonesForPage
          // flow: _isCopy makes render() populate the content and isClone
          // suppresses the paste offset in _moveAfterPaste.
          editor._isCopy = true;
          editor.isClone = true;
          layer.addOrRebuild(editor);
          layer.div.hidden = false; // unhide when the page was rendered empty
          inserted++;
        }
      } catch (e) {
        errors.push(`page ${pageNum}: ${e?.message || e}`);
      }
    }

    return { inserted, missing, cleared, errors };
  }

  // Extension pages cannot eval (MV3 CSP forbids unsafe-eval), so
  // browser_execute on viewer tabs is served by a fixed command set
  // instead of arbitrary scripts.
  async function commandViewer(cmd, args) {
    const a = app();
    if (!a?.pdfViewer) return { error: "viewer app not ready" };
    switch (String(cmd || "")) {
      case "state":
        return {
          page: a.page,
          pages: a.pagesCount,
          scale: a.pdfViewer.currentScaleValue,
          rotation: a.pdfViewer.pagesRotation,
          annotations: a.pdfDocument?.annotationStorage?.size ?? 0,
        };
      case "goto": {
        const page = Math.max(1, Math.round(Number(args?.page) || 1));
        a.pdfViewer.scrollPageIntoView({ pageNumber: Math.min(page, a.pagesCount) });
        return { page: Math.min(page, a.pagesCount) };
      }
      case "zoom": {
        const v = args?.scale;
        const scale = typeof v === "number" ? v : String(v || "page-fit");
        a.pdfViewer.currentScaleValue = scale;
        return { scale };
      }
      case "rotate": {
        const deg = ((Math.round(Number(args?.deg) || 0) % 360) + 360) % 360;
        a.pdfViewer.pagesRotation = deg;
        return { rotation: deg };
      }
      case "save":
        return saveViewer();
      default:
        return { error: `unknown command '${cmd}' — supported: state, goto, zoom, rotate, save` };
    }
  }

  async function saveViewer() {
    const a = app();
    if (!a?.pdfDocument) return { error: "no document loaded" };
    await a.save();
    return { saved: true, filename: a._docFilename || "" };
  }

  const handlers = {
    acp_pdf_read: () => readViewer(),
    acp_pdf_paragraphs: () => paragraphsViewer(),
    acp_pdf_annotate: (m) => annotateViewer(m.items ?? [], !!m.clear),
    acp_pdf_execute: (m) => commandViewer(m.cmd, m),
    acp_pdf_save: () => saveViewer(),
  };

  runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    const handler = handlers[msg?.type];
    if (!handler) return;
    handler(msg)
      .then((result) => sendResponse(result ?? {}))
      .catch((e) => sendResponse({ error: String(e?.message || e) }));
    return true; // async sendResponse
  });
})();
