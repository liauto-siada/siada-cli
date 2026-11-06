import { join } from "node:path";
import type { McpToolCallResult, McpTool } from "../mcp/types.js";
import { interactivePages } from "./store.js";
import type { InteractivePageShares } from "./share.js";
import { InteractiveUiProjects } from "./project.js";
import { inspectInteractivePage } from "./inspect.js";

export const INTERACTIVE_UI_TOOLS: McpTool[] = [
  {
    name: "browser_present_ui",
    description: "Present a working interactive UI immediately inside the CURRENT Siada chat. The returned siada-ui fence renders inline; quote it verbatim when referring to the page in an assistant message. Prefer this inline view as the primary deliverable. Use Share only when the user asks for a separate or shared webpage. Supply responsive self-contained HTML with inline CSS/JS; no external resources, network, forms, popups or parent navigation. Use siadaUI.state, setState(patch) and submit('first-person request') for state and assistant actions. Choose yourself whether direct HTML or optional source/teardown tools help. Presentation needs no inspect call: browser_ui_inspect is optional when a specific uncertainty or defect warrants it. Present first, then explain; avoid redundant inspection steps.",
    inputSchema: {
      type: "object",
      properties: {
        title: { type: "string", description: "Page title, 1–200 characters" },
        html: { type: "string", description: "HTML body fragment, inline CSS and JS, at most 2 MiB" },
        state: { type: "object", description: "Initial JSON state, at most 64 KiB" },
      },
      required: ["title", "html"],
    },
  },
  {
    name: "browser_ui_project",
    description: "Create an editable source workspace when you judge source modules or the optional teardown toolkit useful. Direct HTML remains available through browser_present_ui. blank starts a small page; teardown supplies the installed public kit and guide; teardown-v8 supplies its geometry/kinematics with responsive controls. Reuse modules and build to present inline in the current chat. Inspect only when it helps resolve a specific uncertainty; there is no mandatory tool sequence or iteration tier.",
    inputSchema: { type: "object", properties: { title: { type: "string" }, template: { type: "string", enum: ["blank", "teardown", "teardown-v8"] } }, required: ["title"] },
  },
  {
    name: "browser_ui_build",
    description: "Apply small source edits and build a UI project, immediately presenting the artifact INLINE in the current chat. files maps relative paths to text; omit it after editing the workspace with file tools. Builds update the same card and preserve user state; failures keep the previous page. Quote the returned siada-ui fence verbatim if presenting it in assistant text. Decide yourself whether further edits or optional inspection are useful; do not require inspect before showing the UI or substitute an external link. Only owned source and installed Three.js imports are allowed.",
    inputSchema: { type: "object", properties: { id: { type: "string" }, files: { type: "object" }, entry: { type: "string" }, state: { type: "object" } }, required: ["id"] },
  },
  {
    name: "browser_ui_inspect",
    description: "OPTIONAL diagnostic tool: inspect an already presented UI when you need evidence about a particular layout, runtime or mechanism issue. It is not a prerequisite for presentation. Returns a contact sheet, runtime errors, control sizes and registered measurements without changing the user's page. Select only relevant views (V8: assembled, section, exploded) and width 320–1600. Reuse existing findings; repeat only after relevant changes or unresolved failures. Keep the UI inline in the current chat while inspecting.",
    inputSchema: { type: "object", properties: { id: { type: "string" }, views: { type: "array", items: { type: "string" } }, width: { type: "integer" } }, required: ["id"] },
  },
  {
    name: "browser_share_ui",
    description: "Publish an existing interactive UI as a persistent webpage accessible on the local network. Use only when the user asks to share or publish. Supply its id and optionally the user's current state. Returns a LAN webpage URL without proxy credentials. The published page is an independent snapshot; recipients can interact without accessing the original conversation.",
    inputSchema: { type: "object", properties: { id: { type: "string" }, state: { type: "object" } }, required: ["id"] },
  },
  {
    name: "browser_save_ui",
    description: "Save an existing interactive UI as a persistent webpage and standalone offline HTML file. Use the id from browser_present_ui or browser_list_ui. Omit state to preserve the latest state saved by the chat UI; supply state from a user's UI action when available. Return the stable URL and HTML path. The standalone page works without an agent or model; assistant actions resume in Siada chat.",
    inputSchema: {
      type: "object",
      properties: { id: { type: "string" }, state: { type: "object" } },
      required: ["id"],
    },
  },
  {
    name: "browser_list_ui",
    description: "List locally saved interactive webpages with ids, titles and stable links, including pages from previous sessions.",
    inputSchema: { type: "object", properties: {} },
  },
];

let pageBaseUrl = "http://127.0.0.1:9315";
export function setInteractiveUiBaseUrl(url: string): void { pageBaseUrl = url.replace(/\/$/, ""); }
let pageShares: InteractivePageShares | undefined;
export function setInteractiveUiShares(shares: InteractivePageShares): void { pageShares = shares; }
export const interactiveUiProjects = new InteractiveUiProjects(interactivePages);

export async function callInteractiveUiTool(name: string, args: Record<string, unknown> = {}): Promise<McpToolCallResult> {
  try {
    if (name === "browser_ui_project") return { content: [{ type: "text", text: JSON.stringify(await interactiveUiProjects.create(args)) }] };
    if (name === "browser_ui_build") {
      const info = await interactiveUiProjects.build(String(args.id ?? ""), args.files, args.entry, args.state) as { id: string; title: string; revision: string };
      return { content: [{ type: "text", text: `\`\`\`siada-ui\n${JSON.stringify({ id: info.id, title: info.title, revision: info.revision })}\n\`\`\`\n\n${JSON.stringify(info)}` }] };
    }
    if (name === "browser_ui_inspect") {
      const { report, image } = await inspectInteractivePage(await interactivePages.read(String(args.id ?? "")), interactivePages.directory, args.views, args.width);
      return { content: [{ type: "text", text: JSON.stringify(report) }, { type: "image", data: image.toString("base64"), mimeType: "image/jpeg" }], ...(report.passed ? {} : { isError: true }) };
    }
    if (name === "browser_list_ui") {
      const pages = await interactivePages.list();
      return { content: [{ type: "text", text: JSON.stringify(pages.map(page => ({ ...page, url: `${pageBaseUrl}/ui/${page.id}` }))) }] };
    }
    const page = name === "browser_present_ui"
      ? await interactivePages.create(args)
      : await interactivePages.updateState(String(args.id ?? ""), args.state);
    if (name === "browser_share_ui") {
      if (!pageShares) throw new Error("UI sharing is unavailable");
      return { content: [{ type: "text", text: JSON.stringify(await pageShares.publish(page)) }] };
    }
    const info = name === "browser_present_ui" ? {
      id: page.id, title: page.title, display: "inline",
      next: "The interactive UI is displayed in the current chat. Quote the siada-ui fence verbatim if presenting it in assistant text. Explain it here; inspection is optional. Use Share only when the user asks for a standalone webpage.",
    } : {
      id: page.id, title: page.title, url: `${pageBaseUrl}/ui/${page.id}`,
      downloadUrl: `${pageBaseUrl}/ui/${page.id}/download`,
      htmlPath: join(interactivePages.directory, `${page.id}.html`),
    };
    return {
      content: [{ type: "text", text: `\`\`\`siada-ui\n${JSON.stringify({ id: page.id, title: page.title })}\n\`\`\`\n\n${JSON.stringify(info)}` }],
    };
  } catch (error) {
    return { content: [{ type: "text", text: (error as Error).message }], isError: true };
  }
}