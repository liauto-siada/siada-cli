import { useEffect, useRef, useState } from "react";
import { useStickToBottomContext } from "use-stick-to-bottom";
import { useDisplaySettings } from "./DisplaySettings";
import type { ACPClient } from "../acp/client";
import { splitInteractiveMessage, uiActionPrompt, validUiState, type InteractiveUiReference } from "../lib/interactive-ui";
import { Button } from "./ui/button";
import { MessageResponse } from "./ai-elements/message";

interface InteractiveUIProps {
  page: InteractiveUiReference;
  client: ACPClient;
  onSubmit: (text: string, displayText: string) => void;
}

export function InteractiveUI({ page, client, onSubmit }: InteractiveUIProps) {
  const { stopScroll } = useStickToBottomContext();
  const { scale } = useDisplaySettings();
  const frame = useRef<HTMLIFrameElement>(null);
  const state = useRef<Record<string, unknown>>({});
  const writes = useRef<Promise<unknown>>(Promise.resolve());
  const submit = useRef(onSubmit);
  submit.current = onSubmit;
  const [height, setHeight] = useState(360);
  const [ready, setReady] = useState(false);
  const [status, setStatus] = useState("正在加载交互界面…");
  const [saving, setSaving] = useState(false);
  const [sharedUrl, setSharedUrl] = useState<string | null>(null);
  const visible = useRef(true);
  const section = useRef<HTMLElement>(null);
  const pending = useRef<{ nonce: string; resolve: (state: Record<string, unknown>) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> } | null>(null);
  const sendDisplaySettings = () => frame.current?.contentWindow?.postMessage({
    channel: "siada-ui", id: page.id, type: "display", scale,
  }, "*");

  const sendVisibility = () => frame.current?.contentWindow?.postMessage({ channel: "siada-ui", id: page.id, type: "visibility", visible: visible.current && !document.hidden }, "*");
  useEffect(() => { sendDisplaySettings(); }, [scale, page.id, page.revision]);
  useEffect(() => {
    if (!section.current || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(entries => { visible.current = !!entries[0]?.isIntersecting; sendVisibility(); });
    observer.observe(section.current);
    document.addEventListener("visibilitychange", sendVisibility);
    return () => { observer.disconnect(); document.removeEventListener("visibilitychange", sendVisibility); };
  }, [page.id, page.revision]);

  function persist(current: Record<string, unknown>): Promise<unknown> {
    const work = writes.current.catch(() => {}).then(() => client.saveInteractiveUiState(page.id, current));
    writes.current = work;
    void work.catch(() => setStatus("状态同步失败，请点击 Share 重试"));
    return work;
  }

  useEffect(() => {
    let active = true;
    setReady(false);
    setSharedUrl(null);
    const loadTimeout = setTimeout(() => setStatus("界面加载失败，请检查代理连接后刷新"), 10000);
    const listener = (event: MessageEvent) => {
      const data = event.data;
      if (event.source !== frame.current?.contentWindow || !data || data.channel !== "siada-ui" || data.id !== page.id) return;
      if (data.type === "snapshot" && pending.current && pending.current.nonce === data.nonce) {
        const request = pending.current; pending.current = null; clearTimeout(request.timer);
        if (validUiState(data.state) && !data.error) { state.current = data.state; request.resolve(data.state); }
        else request.reject(new Error(data.error || "界面状态无效"));
        return;
      }
      if (data.type === "interaction") stopScroll();
      if (data.type === "height" && Number.isFinite(data.height)) setHeight(Math.min(2400, Math.max(120, data.height)));
      if (data.type === "ready" && validUiState(data.state)) {
        clearTimeout(loadTimeout);
        state.current = data.state;
        setReady(true);
        setStatus("可以直接操作界面");
      }
      if ((data.type === "state" || data.type === "submit") && validUiState(data.state)) {
        state.current = data.state;
        const work = persist(data.state);
        void work.then(() => { if (active) setStatus("当前状态已更新"); }, () => {});
        if (data.type === "submit" && typeof data.prompt === "string" && data.prompt.trim() && data.prompt.length <= 8000) {
          submit.current(uiActionPrompt(page, data.prompt, data.state), data.prompt.trim());
        }
      }
    };
    window.addEventListener("message", listener);
    return () => {
      active = false; clearTimeout(loadTimeout); window.removeEventListener("message", listener);
      if (pending.current) { clearTimeout(pending.current.timer); pending.current.reject(new Error("界面已更新，请重新分享")); pending.current = null; }
    };
  }, [page.id, page.revision, client, stopScroll]);

  function currentSnapshot(): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
      const nonce = crypto.randomUUID();
      const timer = setTimeout(() => {
        if (pending.current?.nonce === nonce) pending.current = null;
        reject(new Error("读取当前界面状态超时，请重试"));
      }, 5000);
      pending.current = { nonce, resolve, reject, timer };
      frame.current?.contentWindow?.postMessage({ channel: "siada-ui", id: page.id, type: "snapshot", nonce }, "*");
    });
  }

  async function share() {
    setSaving(true);
    setSharedUrl(null);
    try {
      const snapshot = await currentSnapshot();
      await persist(snapshot);
      const { url } = await client.shareInteractiveUi(page.id, snapshot);
      setSharedUrl(url);
      setStatus("分享网页已生成，同一局域网可访问");
    } catch (error) { setStatus(`分享失败：${(error as Error).message}`); }
    finally { setSaving(false); }
  }

  async function copyLink() {
    try { await navigator.clipboard.writeText(sharedUrl!); setStatus("链接已复制"); }
    catch { setStatus("复制失败，请选中链接手动复制"); }
  }

  return (
    <section ref={section} className="w-full min-w-0 rounded-xl border bg-background overflow-hidden" aria-label={`交互界面：${page.title}`}
      onPointerEnter={() => stopScroll()} onPointerDownCapture={() => stopScroll()} onFocusCapture={() => stopScroll()}>
      <div className="flex flex-wrap items-center gap-2 border-b p-3">
        <strong className="min-w-0 flex-1">{page.title}</strong>
        <Button size="sm" variant="outline" disabled={!ready || saving} onClick={() => void share()}>{saving ? "Sharing…" : "Share"}</Button>
      </div>
      {sharedUrl && <div className="flex flex-wrap items-center gap-2 border-t px-3 py-2">
        <input aria-label="局域网分享链接" readOnly value={sharedUrl} onFocus={event => event.target.select()}
          className="w-full min-w-0 rounded border bg-muted px-2 py-1 text-xs" />
        <a className="text-xs underline" href={sharedUrl} target="_blank" rel="noopener noreferrer">打开网页</a>
        <Button type="button" variant="ghost" size="sm" onClick={() => void copyLink()}>复制链接</Button>
      </div>}
      <div className="flex flex-wrap gap-2 px-3 py-2 text-xs text-muted-foreground" role="status">
        <span>{status}</span>
      </div>
      <iframe ref={frame} title={page.title} sandbox="allow-scripts" referrerPolicy="no-referrer"
        src={`${client.interactiveUiUrl(page.id, "frame")}${page.revision ? `?revision=${page.revision}` : ""}`} style={{ width: "100%", height, border: 0 }}
        onLoad={() => { sendDisplaySettings(); sendVisibility(); }}
        onError={() => setStatus("界面加载失败，请检查本地代理连接")} />
    </section>
  );
}

export function InteractiveMessage({ text, client, onSubmit, renderPage }: {
  text: string;
  client: ACPClient;
  onSubmit: (text: string, displayText: string) => void;
  renderPage?: (page: InteractiveUiReference, key: string) => React.ReactNode;
}) {
  return splitInteractiveMessage(text).map((part, index) => part.type === "ui"
    ? renderPage ? renderPage(part.page, `${index}:${part.page.id}`) : <InteractiveUI key={`${index}:${part.page.id}`} page={part.page} client={client} onSubmit={onSubmit} />
    : <MessageResponse key={index}>{part.text}</MessageResponse>);
}