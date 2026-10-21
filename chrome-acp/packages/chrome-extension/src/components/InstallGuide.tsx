import { useState } from "react";

export const INSTALL_COMMANDS = {
  unix: "curl -fsSL https://li.auto/HHuNhPv | sh -s -- --with-browser --browser-host 0.0.0.0",
  windows: '$env:SIADA_BROWSER_HOST="0.0.0.0"; $env:SIADA_WITH_BROWSER="1";\nirm https://li.auto/ZQ3nfD5 | iex',
};

export function InstallGuide({ onConnect }: { onConnect: () => void }) {
  const [copied, setCopied] = useState<string | null>(null);
  const [copyFailed, setCopyFailed] = useState(false);
  const copy = async (platform: keyof typeof INSTALL_COMMANDS) => {
    try {
      await navigator.clipboard.writeText(INSTALL_COMMANDS[platform]);
      setCopied(platform);
      setCopyFailed(false);
    } catch {
      setCopyFailed(true);
    }
  };
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-6">
      <div className="my-auto flex flex-col items-center gap-5 py-6">
        <img src={chrome.runtime.getURL("icons/icon128.png")} alt="Chrome ACP" className="h-20 w-20" />
        <h1 className="text-xl font-semibold">安装 Siada CLI</h1>
        <p className="max-w-sm text-center text-sm leading-6 text-muted-foreground">复制对应系统的命令，在终端中运行。安装后将自动检测，你可以在 Chrome 中继续登录。</p>
        <div className="w-full max-w-lg space-y-4">
          {(["unix", "windows"] as const).map((platform) => (
            <div key={platform} className="space-y-3 rounded-xl border p-4">
              <div className="flex items-center justify-between text-sm">
                <span>{platform === "unix" ? "Linux / macOS" : "Windows PowerShell"}</span>
                <button type="button" className="rounded-md border px-3 py-1.5 text-xs hover:bg-muted" onClick={() => void copy(platform)}>
                  {copied === platform ? "已复制" : "复制"}
                </button>
              </div>
              <pre className="whitespace-pre-wrap break-all rounded bg-muted p-3 text-xs select-text">{INSTALL_COMMANDS[platform]}</pre>
            </div>
          ))}
          <p className="text-xs text-muted-foreground">0.0.0.0 会开启远程控制，并对外开放相应端口。安装完成后将自动检测连接。</p>
          {copyFailed && <p role="status" className="text-xs">复制失败，请选择上方命令手动复制。</p>}
        </div>
      </div>
      <button type="button" className="mt-6 shrink-0 rounded-lg border p-3 text-sm hover:bg-muted" onClick={onConnect}>
        已安装 / 其它设备存在 Siada CLI
      </button>
    </div>
  );
}