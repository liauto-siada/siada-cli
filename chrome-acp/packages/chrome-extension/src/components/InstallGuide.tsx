import { useState } from "react";

export const INSTALL_COMMAND = "curl -fsSL https://raw.githubusercontent.com/liauto-siada/siada-cli/main/scripts/install-browser.sh | sh";

export function InstallGuide({ onConnect }: { onConnect: () => void }) {
  const [copied, setCopied] = useState(false);
  const [copyFailed, setCopyFailed] = useState(false);
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-6">
      <div className="my-auto flex flex-col items-center gap-5 py-6">
        <img src={chrome.runtime.getURL("icons/icon128.png")} alt="Chrome ACP" className="h-20 w-20" />
        <h1 className="text-xl font-semibold">安装 Siada CLI</h1>
        <p className="max-w-sm text-center text-sm leading-6 text-muted-foreground">复制命令，在终端中运行。安装后将自动检测，你可以在 Chrome 中继续登录。</p>
        <div className="w-full max-w-lg space-y-3 rounded-xl border p-4">
          <div className="flex items-center justify-between text-sm">
            <span>Linux / macOS</span>
            <button type="button" className="rounded-md border px-3 py-1.5 text-xs hover:bg-muted" onClick={async () => {
              try { await navigator.clipboard.writeText(INSTALL_COMMAND); setCopied(true); setCopyFailed(false); }
              catch { setCopyFailed(true); }
            }}>{copied ? "已复制" : "复制"}</button>
          </div>
          <pre className="whitespace-pre-wrap break-all rounded bg-muted p-3 text-xs select-text">{INSTALL_COMMAND}</pre>
          {copyFailed && <p role="status" className="text-xs">复制失败，请选择上方命令手动复制。</p>}
        </div>
      </div>
      <button type="button" className="mt-6 shrink-0 rounded-lg border p-3 text-sm hover:bg-muted" onClick={onConnect}>已安装 / 其它设备存在 Siada CLI</button>
    </div>
  );
}