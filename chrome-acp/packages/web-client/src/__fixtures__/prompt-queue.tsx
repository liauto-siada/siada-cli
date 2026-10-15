// Offline browser fixture: real ChatInterface, controllable agent transport.
import { createRoot } from "react-dom/client";
import { ChatInterface } from "../../../shared/src/components/ChatInterface";
import { TooltipProvider } from "../../../shared/src/components/ui/tooltip";
import type { ACPClient } from "../../../shared/src/acp/client";
import "../../../shared/src/styles/index.css";

const handlers = new Map<string, (...args: any[]) => void>();
const sent: { content: unknown; id: string }[] = [];
const steered: unknown[] = [];
let sessionId = "fixture-session";
const client = new Proxy({
  supportsImages: new URLSearchParams(location.search).get("images") === "1",
  supportsSteering: true, modelState: null,
  async createSession() {
    sessionId = crypto.randomUUID();
    handlers.get("setSessionCreatedHandler")?.(sessionId);
  },
  async sendPrompt(content: unknown, id: string) { sent.push({ content, id }); },
  async steer(content: unknown) { steered.push(content); },
  cancel() {
    handlers.get("setPromptCompleteHandler")?.("cancelled", sessionId, sent.at(-1)?.id);
  },
}, {
  get(target, key) {
    if (key in target) return target[key as keyof typeof target];
    if (typeof key === "string" && key.startsWith("set")) {
      return (handler: (...args: any[]) => void) => {
        handlers.set(key, handler);
        if (key === "setModelStateChangedHandler") handler(null);
      };
    }
    return undefined;
  },
}) as unknown as ACPClient;

(window as any).fixture = {
  sent, steered,
  complete(reason = "end_turn") {
    handlers.get("setPromptCompleteHandler")?.(reason, sessionId, sent.at(-1)?.id);
  },
};
createRoot(document.getElementById("root")!).render(
  <TooltipProvider>
    <div style={{ height: "100vh", maxWidth: 540, margin: "auto" }}>
      <ChatInterface client={client} />
    </div>
  </TooltipProvider>,
);