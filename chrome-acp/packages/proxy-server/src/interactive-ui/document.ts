export interface InteractivePage {
  version: 1;
  id: string;
  title: string;
  html: string;
  state: Record<string, unknown>;
  updatedAt: string;
  revision?: string;
}

// Model-authored scripts run only inside an opaque-origin frame. Keep network,
// navigation and extension APIs out of the generated UI's execution context.
export const FRAME_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data: blob:; media-src data: blob:; connect-src 'none'; frame-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'";
const PAGE_CSP = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; frame-src 'self' blob:; form-action 'none'; base-uri 'none'; object-src 'none'";

function scriptJson(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c").replace(/\u2028/g, "\\u2028").replace(/\u2029/g, "\\u2029");
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]!);
}

export function frameDocument(page: InteractivePage): string {
  return `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${FRAME_CSP}"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{margin:0}body{font:14px/1.5 system-ui,sans-serif;color:#172033;background:#fff;padding:16px;box-sizing:border-box}*{box-sizing:border-box}button,input,select,textarea{font:inherit}img,svg,canvas{max-width:100%}</style>
<script>
(() => {
  let state = ${scriptJson(page.state)};
  let binding = null, visible = !document.hidden;
  const visibilityListeners = new Set();
  const send = (type, extra = {}) => parent.postMessage({channel:"siada-ui",id:${scriptJson(page.id)},type,...extra}, "*");
  window.siadaUI = Object.freeze({
    get state() { return structuredClone(state); },
    setState(patch) {
      if (!patch || typeof patch !== "object" || Array.isArray(patch)) return;
      state = {...state,...patch};
      send("state", {state});
    },
    submit(prompt) {
      if (typeof prompt === "string" && prompt.trim()) {
        if(binding) state=binding.capture();
        send("submit", {prompt,state});
      }
    },
    registerState(value) {
      if(!value || typeof value.capture!=="function" || typeof value.restore!=="function") throw new Error("Invalid state binding");
      binding=value; binding.restore(structuredClone(state));
    },
    onVisibility(listener) {
      if(typeof listener !== "function") return () => {};
      visibilityListeners.add(listener); listener(visible);
      return () => visibilityListeners.delete(listener);
    }
  });
  addEventListener("pointerdown", () => send("interaction"), true);
  addEventListener("keydown", () => send("interaction"), true);
  const measure = () => send("height",{height:Math.ceil(document.body.getBoundingClientRect().height)});
  addEventListener("message", event => {
    const data = event.data;
    if(event.source !== parent || !data || data.channel !== "siada-ui" || data.id !== ${scriptJson(page.id)}) return;
    if(data.type==="snapshot" && typeof data.nonce==="string" && data.nonce.length<=80) {
      try {
        if(binding) state=binding.capture();
        const json=JSON.stringify(state);
        if(!state || typeof state!=="object" || Array.isArray(state) || new TextEncoder().encode(json).length>65536) throw new Error("Invalid UI snapshot");
        send("snapshot",{nonce:data.nonce,state});
      } catch { send("snapshot",{nonce:data.nonce,error:"无法读取界面当前状态"}); }
      return;
    }
    if(data.type==="visibility" && typeof data.visible==="boolean") {
      visible=data.visible; for(const listener of visibilityListeners) listener(visible); return;
    }
    if(data.type !== "display") return;
    if(!Number.isFinite(data.scale) || data.scale < 80 || data.scale > 120) return;
    document.documentElement.style.zoom = String(data.scale / 100);
    requestAnimationFrame(measure);
  });
  addEventListener("DOMContentLoaded", () => {
    new ResizeObserver(measure).observe(document.body);
    measure();
    send("ready",{state});
  });
})();
</script></head><body>${page.html}</body></html>`;
}

/** A self-contained document: the trusted host stores state, the child runs UI. */
export function standaloneDocument(page: InteractivePage, shared = false): string {
  const frame = frameDocument(page);
  const { html: _html, ...metadata } = page;
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${PAGE_CSP}"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(page.title)}</title>
<style>body{margin:0;background:#f6f8fb;color:#172033;font:14px/1.5 system-ui,sans-serif}header{padding:16px 24px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}h1{margin:0;font-size:18px}button{font:inherit;border:1px solid #d8dfeb;border-radius:8px;padding:8px 12px;background:white;cursor:pointer}iframe{display:block;width:100%;border:0;background:white;min-height:360px}#status{color:#526078}</style></head>
<body><header><h1>${escapeHtml(page.title)}</h1>${shared ? "" : '<button id="export">下载当前网页</button>'}<span id="status" role="status">可独立使用，状态保存在当前浏览器</span></header><iframe id="view" title="${escapeHtml(page.title)}" sandbox="allow-scripts" referrerpolicy="no-referrer"></iframe>
<script>
(() => {
  const page = ${scriptJson(metadata)};
  const originalFrame = ${scriptJson(frame)};
  const key = "siada-ui:" + page.id + ":" + page.updatedAt;
  const frame = document.getElementById("view");
  const status = document.getElementById("status");
  let state = page.state;
  try { const saved = JSON.parse(localStorage.getItem(key)); if(saved && typeof saved==="object" && !Array.isArray(saved)) state=saved; } catch {}
  const json = value => JSON.stringify(value).replace(/</g,"\\\\u003c").replace(/\\u2028/g,"\\\\u2028").replace(/\\u2029/g,"\\\\u2029");
  const hydrate = (doc, current) => doc.replace("let state = " + json(page.state) + ";", () => "let state = " + json(current) + ";");
  frame.srcdoc = hydrate(originalFrame,state);
  addEventListener("message", event => {
    const data = event.data;
    if(event.source!==frame.contentWindow || !data || data.channel!=="siada-ui" || data.id!==page.id) return;
    if(data.type==="height" && Number.isFinite(data.height)) frame.style.height=Math.min(2400,Math.max(120,data.height))+"px";
    if((data.type==="state" || data.type==="submit") && data.state && typeof data.state==="object" && !Array.isArray(data.state) && JSON.stringify(data.state).length<=65536) {
      state=data.state;
      try { localStorage.setItem(key,JSON.stringify(state)); status.textContent="已保存当前状态"; }
      catch { status.textContent=${scriptJson(shared ? "浏览器存储不可用，刷新后将恢复分享时的状态" : "浏览器存储不可用，请下载网页保存当前状态")}; }
    }
    if(data.type==="submit") status.textContent="独立网页已保存操作；需要助手时，请在 Siada 会话中继续";
  });
  const exportButton = document.getElementById("export");
  if(exportButton) exportButton.onclick = () => {
    // Rewrite only trusted serialized data in the host, never execute child markup.
    const root = document.documentElement.cloneNode(true);
    // Leave a single initialization path on reload, rather than starting the
    // serialized live iframe and then replacing it with another srcdoc.
    root.querySelector("#view").removeAttribute("srcdoc");
    root.querySelector("#view").removeAttribute("style");
    let html = "<!doctype html>" + root.outerHTML;
    html = html.replace("const page = " + json(page) + ";", () => "const page = " + json({...page,state}) + ";");
    html = html.replace("const originalFrame = " + json(originalFrame) + ";", () => "const originalFrame = " + json(hydrate(originalFrame,state)) + ";");
    const url=URL.createObjectURL(new Blob([html],{type:"text/html;charset=utf-8"}));
    const link=document.createElement("a"); link.href=url; link.download="siada-ui-"+page.id+".html"; link.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  };
})();
</script></body></html>`;
}