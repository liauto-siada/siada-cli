import { useEffect, useRef, useState } from "react";

type Model = { id: string; name: string };
type Provider = { id: string; name: string; baseUrl: string; models: Model[] };
type Selector = { providers?: Provider[]; liidDisabled?: boolean; freeTrialModels?: Model[] };

/** Render the CLI wizard; only the CLI validates and persists credentials. */
export function BrowserLogin({ endpoint, extensionId, icon, reconfigure = false, onComplete, onCancel }: {
  endpoint: string; extensionId: string; icon: string; reconfigure?: boolean;
  onComplete?: () => void; onCancel?: () => void;
}) {
  const socket = useRef<WebSocket | null>(null);
  const [selector, setSelector] = useState<Selector | null>(null);
  const [phase, setPhase] = useState<"select" | "apikey" | "trial" | "waiting">("select");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [url, setUrl] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [providerId, setProviderId] = useState("custom");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [copied, setCopied] = useState(false);
  const callbacks = useRef({ onComplete, onCancel });
  callbacks.current = { onComplete, onCancel };
  useEffect(() => {
    let active = true;
    let succeeded = false;
    const target = new URL(endpoint);
    target.protocol = "ws:";
    target.pathname = "/local-login";
    target.search = "";
    target.searchParams.set("extensionId", extensionId);
    if (reconfigure) target.searchParams.set("reconfigure", "1");
    const ws = new WebSocket(target);
    socket.current = ws;
    setError(""); setSelector(null); setBusy(false); setPhase("select"); setUrl(""); setCopied(false);
    ws.onmessage = event => {
      if (!active) return;
      try {
        const data = JSON.parse(event.data);
        if (data.method === "ui/showLoginSelector") {
          setSelector(data.params); setBusy(false);
          setPhase(current => current === "waiting" ? "select" : current);
        } else if (data.method === "ui/loginDeviceUrl") {
          const link = new URL(data.params.url);
          if (link.protocol !== "https:") throw new Error("Invalid login URL");
          setUrl(link.toString()); setPhase("waiting");
          if (data.params.openBrowser) window.open(link.toString(), "_blank", "noopener,noreferrer");
        } else if (data.method === "ui/loginError") {
          setError(data.params.error || "登录失败，请重试"); setBusy(false);
        } else if (data.method === "ui/loginSuccess") {
          succeeded = true; setApiKey(""); setPhase("waiting"); setUrl("");
          callbacks.current.onComplete?.();
        }
      } catch { setError("无法读取登录结果，请重试"); setBusy(false); }
    };
    ws.onerror = () => { if (active) setError("无法连接本机登录服务，请重试"); };
    ws.onclose = () => { if (active && !succeeded) { setError("登录连接已关闭，请重试"); setBusy(false); } };
    return () => { active = false; ws.close(); socket.current = null; };
  }, [endpoint, extensionId, attempt, reconfigure]);

  function submit(choice: string, payload?: object) {
    if (busy) return;
    if (socket.current?.readyState !== WebSocket.OPEN) { setError("登录连接已关闭，请重试"); return; }
    setBusy(true); setError("");
    socket.current.send(JSON.stringify({ choice, payload }));
    setApiKey("");
  }
  const providers = selector?.providers ?? [];
  const selected = providers.find(provider => provider.id === providerId);
  const fieldClass = "mt-1.5 w-full min-w-0 rounded-lg border border-input bg-background px-3 py-2.5 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
  const primaryClass = "w-full rounded-lg bg-primary px-4 py-3 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90 disabled:opacity-50";
  const secondaryClass = "w-full rounded-lg border px-4 py-2.5 text-sm hover:bg-muted disabled:opacity-50";
  const optionClass = "w-full rounded-xl border bg-background px-4 py-4 text-left transition-colors hover:border-primary/50 hover:bg-muted/50 focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50";
  return <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-background px-5 py-8">
    <div className="my-auto w-full max-w-sm self-center space-y-6 py-2">
      <div className="space-y-3 text-center">
        <img src={icon} alt="Chrome ACP" className="mx-auto h-14 w-14" />
        <h1 className="text-xl font-semibold tracking-tight">{reconfigure ? "重新登录 / 切换模型服务" : "登录 Siada CLI"}</h1>
        <p className="text-sm leading-6 text-muted-foreground">{reconfigure ? "选择新的登录方式，完成后自动重新连接。" : "选择登录方式，完成后即可开始对话。"}</p>
      </div>
      {!selector && !error && <p role="status">正在加载登录选项…</p>}
      {selector && phase === "select" && <div className="flex flex-col gap-3">
        {!selector.liidDisabled && <>
          <button className={optionClass} disabled={busy} onClick={() => submit("1")}><span className="block text-sm font-medium">Sign in with LiId</span><span className="mt-1 block text-xs text-muted-foreground">使用理想账号，自动打开授权页面</span></button>
          <button className={optionClass} disabled={busy} onClick={() => submit("2")}><span className="block text-sm font-medium">Sign in with Device Code</span><span className="mt-1 block text-xs text-muted-foreground">复制授权链接，在其它浏览器或设备登录</span></button>
        </>}
        <button className={optionClass} disabled={busy} onClick={() => setPhase("apikey")}><span className="block text-sm font-medium">Configure API Key</span><span className="mt-1 block text-xs text-muted-foreground">使用自己的模型服务和 API Key</span></button>
        {!!selector.freeTrialModels?.length && <button className={optionClass} disabled={busy} onClick={() => {
          setModel(selector.freeTrialModels![0]!.id); setPhase("trial");
        }}><span className="block text-sm font-medium">Free Trial</span><span className="mt-1 block text-xs text-muted-foreground">选择免费模型，无需 API Key</span></button>}
      </div>}
      {phase === "apikey" && <form className="space-y-4 rounded-xl border p-4 text-sm" onSubmit={event => {
        event.preventDefault(); submit("3", { provider_id: providerId, base_url: baseUrl, model, api_key: apiKey });
      }}>
        <h2 className="font-semibold">配置 API Key</h2>
        <label className="block">模型服务商<select className={fieldClass} value={providerId} disabled={busy} onChange={event => {
          const id = event.target.value; const p = providers.find(item => item.id === id);
          setProviderId(id); setBaseUrl(p?.baseUrl ?? ""); setModel(p?.models[0]?.id ?? "");
        }}>
          <option value="custom">Custom Provider</option>
          {providers.filter(p => p.id !== "custom").map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select></label>
        <label className="block">Base URL<input className={fieldClass} type="url" required value={baseUrl} disabled={busy} onChange={e => setBaseUrl(e.target.value)} /></label>
        <label className="block">模型<input className={fieldClass} placeholder="选择或输入模型 ID" list="login-models" required value={model} disabled={busy} onChange={e => setModel(e.target.value)} /></label>
        <datalist id="login-models">{selected?.models.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}</datalist>
        <label className="block">API Key<input className={fieldClass} type="password" autoComplete="off" required value={apiKey} disabled={busy} onChange={e => setApiKey(e.target.value)} /></label>
        <button className={primaryClass} disabled={busy} type="submit">{busy ? "正在保存…" : "保存并连接"}</button>
        <button className={secondaryClass} type="button" disabled={busy} onClick={() => { setApiKey(""); setError(""); setPhase("select"); }}>返回登录方式</button>
      </form>}
      {phase === "trial" && <form className="space-y-4 rounded-xl border p-4 text-sm" onSubmit={event => { event.preventDefault(); submit("4", { model }); }}>
        <h2 className="font-semibold">Free Trial</h2>
        <p className="text-xs leading-5 text-muted-foreground">选择免费模型即可开始。可用性由模型服务商决定，之后可随时切换。</p>
        <label className="block">Free model<select className={fieldClass} value={model} disabled={busy} onChange={e => setModel(e.target.value)}>
          {selector?.freeTrialModels?.map(m => <option key={m.id} value={m.id}>{m.name}</option>)}
        </select></label>
        <button className={primaryClass} type="submit" disabled={busy}>{busy ? "正在连接…" : "开始免费试用"}</button>
        <button className={secondaryClass} type="button" disabled={busy} onClick={() => { setError(""); setPhase("select"); }}>返回登录方式</button>
      </form>}
      {phase === "waiting" && <div className="space-y-4 rounded-xl border bg-muted/30 p-4 text-sm leading-6">
        <p>{url ? "请打开授权页面完成登录，完成后将自动连接。" : "登录成功，正在连接…"}</p>
        {url && <>
          <a className={`${primaryClass} block text-center`} href={url} target="_blank" rel="noopener noreferrer">打开授权页面</a>
          <code className="block max-h-24 overflow-auto break-all rounded-md bg-muted p-3 text-xs leading-5">{url}</code>
          <button className={secondaryClass} onClick={() => void navigator.clipboard.writeText(url).then(() => setCopied(true)).catch(() => setError("复制失败，请手动复制授权链接"))}>{copied ? "已复制链接" : "复制授权链接"}</button>
          <button className={secondaryClass} onClick={() => setAttempt(n => n + 1)}>返回登录方式</button>
        </>}
      </div>}
      {busy && phase !== "waiting" && <p role="status">正在处理…</p>}
      {error && <div role="alert" className="space-y-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm"><p className="break-words leading-6 text-destructive">{error}</p><button className={secondaryClass} onClick={() => setAttempt(n => n + 1)}>重试登录</button></div>}
      {onCancel && <button className={secondaryClass} onClick={() => { setApiKey(""); callbacks.current.onCancel?.(); }}>{reconfigure ? "取消，保留当前配置" : "连接其它设备"}</button>}
    </div>
  </div>;
}