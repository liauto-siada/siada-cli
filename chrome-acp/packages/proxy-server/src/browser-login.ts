import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import { basename } from "node:path";
import { createInterface } from "node:readline";
import type { WSContext } from "hono/ws";

/** One login process belongs to one authorized WebSocket and is never reused. */
export function browserLoginSocket(command: string, cwd: string, reconfigure = false) {
  let child: ChildProcessWithoutNullStreams | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const stop = () => {
    clearTimeout(timer);
    child?.kill();
    child = undefined;
  };
  return {
    onOpen(_event: Event, ws: WSContext) {
      if (!/^siada-cli(?:\.exe)?$/i.test(basename(command))) { ws.close(1008); return; }
      child = spawn(command, ["--browser-login", ...(reconfigure ? ["--reconfigure"] : [])], { cwd, stdio: ["pipe", "pipe", "pipe"] });
      timer = setTimeout(() => { stop(); ws.close(1000, "Login timed out"); }, 600_000);
      // Consume stderr without forwarding credentials or local diagnostics.
      child.stderr.resume();
      const lines = createInterface({ input: child.stdout });
      lines.on("line", line => {
        if (line.length > 4_000_000) return;
        try {
          const event = JSON.parse(line);
          if (["ui/showLoginSelector", "ui/loginDeviceUrl", "ui/loginSuccess", "ui/loginError"].includes(event.method)) {
            ws.send(JSON.stringify(event));
          }
        } catch { /* Non-protocol diagnostics are not sent to the browser. */ }
      });
      child.on("error", () => {
        ws.send(JSON.stringify({ method: "ui/loginError", params: { error: "Could not start Siada CLI." } }));
        stop(); ws.close();
      });
      child.on("exit", () => { clearTimeout(timer); ws.close(); });
    },
    onMessage(event: MessageEvent, ws: WSContext) {
      const raw = event.data.toString();
      if (raw.length > 64_000) { ws.close(1009); stop(); return; }
      try {
        const data = JSON.parse(raw);
        if (!["1", "2", "3", "4"].includes(data.choice) || !child?.stdin.writable) {
          ws.close(1008); stop(); return;
        }
        child.stdin.write(JSON.stringify({ choice: data.choice, payload: data.payload ?? {} }) + "\n");
      } catch { ws.close(1008); stop(); }
    },
    onClose: stop,
    onError: stop,
  };
}