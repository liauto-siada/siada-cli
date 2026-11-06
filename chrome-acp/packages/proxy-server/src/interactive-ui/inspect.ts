import { chromium } from "playwright";
import { access, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { frameDocument, type InteractivePage } from "./document.js";

async function browserExecutable(): Promise<string | undefined> {
  const explicit = process.env.SIADA_UI_CHROMIUM || process.env.CHROMIUM;
  if (explicit) return explicit;
  for (const path of [
    chromium.executablePath(),
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
  ]) {
    try { await access(path); return path; } catch { /* Try the next installed browser. */ }
  }
  throw new Error("No Chromium found. Set SIADA_UI_CHROMIUM or install Chromium with Playwright.");
}

/** Inspect in an isolated browser, never in the user's existing Chrome profile. */
export async function inspectInteractivePage(page: InteractivePage, directory: string, requestedViews?: unknown, requestedWidth?: unknown) {
  const views = requestedViews === undefined ? ["default"] : requestedViews;
  if (!Array.isArray(views) || !views.length || views.length > 4 || views.some(view => typeof view !== "string" || view.length > 40)) throw new Error("views must contain 1–4 registered view names");
  const width = requestedWidth === undefined ? 1000 : Number(requestedWidth);
  if (!Number.isInteger(width) || width < 320 || width > 1600) throw new Error("width must be 320–1600");
  const browser = await chromium.launch({ headless: true, executablePath: await browserExecutable(), args: ["--enable-webgl", "--ignore-gpu-blocklist"] });
  const timer = setTimeout(() => { void browser.close(); }, 60000);
  try {
    const context = await browser.newContext({ viewport: { width, height: 900 }, deviceScaleFactor: 1 });
    const host = await context.newPage();
    const errors: string[] = [];
    host.on("pageerror", error => { if (errors.length < 20) errors.push(error.message.slice(0, 800)); });
    host.on("console", message => { if (message.type() === "error" && errors.length < 20) errors.push(message.text().slice(0, 800)); });
    await host.setContent(`<style>body{margin:0}iframe{border:0;width:100%;height:900px}</style><iframe id="view" sandbox="allow-scripts"></iframe><script>addEventListener("message",e=>{if(e.data?.channel==="siada-ui"&&e.data.type==="height")view.style.height=Math.min(1600,Math.max(120,e.data.height))+"px"})</script>`);
    await host.evaluate(html => { (globalThis as any).document.getElementById("view").srcdoc = html; }, frameDocument(page));
    const frame = host.frames().find(item => item.parentFrame() === host.mainFrame())!;
    await frame.waitForFunction(() => {
      const win = globalThis as any;
      return !!win.siadaUI && (win.uiInspection ? win.uiInspection.ready === true : win.document.readyState === "complete");
    }, undefined, { timeout: 30000 });
    const screenshots: string[] = [];
    const checks: object[] = [];
    for (const view of views) {
      await frame.evaluate(name => {
        const inspector = (globalThis as any).uiInspection;
        if(name !== "default") {
          if(!inspector?.views?.[name]) throw new Error("Unknown inspection view: " + name);
          inspector.applyState(inspector.views[name]);
        }
        inspector?.render();
      }, view);
      const metrics = await frame.evaluate(() => {
        const win = globalThis as any;
        return {
          state: win.uiInspection?.getState?.() ?? win.siadaUI.state,
          metrics: win.uiInspection?.metrics?.() ?? {},
          controls: [...win.document.querySelectorAll("button,input,select")].filter(element => element.getBoundingClientRect().height > 0).map(element => ({
            label: element.getAttribute("aria-label") || element.textContent?.slice(0, 80),
            height: element.getBoundingClientRect().height,
          })).slice(0, 40),
        };
      });
      const height = Math.min(1600, Math.max(120, Math.ceil(await frame.evaluate(() => (globalThis as any).document.body.getBoundingClientRect().height))));
      await host.setViewportSize({ width, height });
      const image = await host.screenshot({ type: "jpeg", quality: 75 });
      screenshots.push(image.toString("base64"));
      checks.push({ view, width, ...metrics });
    }
    const sheet = await context.newPage();
    await sheet.setViewportSize({ width: views.length > 1 ? 1200 : width, height: 900 });
    await sheet.setContent(`<style>body{margin:0;font:16px system-ui;background:#edf0f5}.grid{display:grid;grid-template-columns:repeat(${views.length > 1 ? 2 : 1},1fr);gap:8px}.tile{background:white;padding:8px}.tile img{display:block;width:100%;max-height:720px;object-fit:contain}</style><div class="grid"></div>`);
    await sheet.evaluate(items => {
      const document = (globalThis as any).document;
      const grid=document.querySelector('.grid');
      items.forEach(item => {
        const tile=document.createElement('div');tile.className='tile';
        const title=document.createElement('div');title.textContent=item.name;
        const image=document.createElement('img');image.src='data:image/jpeg;base64,'+item.image;
        tile.append(title,image);grid.append(tile);
      });
    }, views.map((name, index) => ({ name, image: screenshots[index] })));
    await sheet.locator("img").evaluateAll(images => Promise.all(images.map(image => (image as any).decode())));
    const image = await sheet.screenshot({ type: "jpeg", quality: 80, fullPage: true });
    const imagePath = join(directory, `${page.id}-inspection.jpg`);
    await writeFile(imagePath, image, { mode: 0o600 });
    const report = { id: page.id, revision: page.revision, checks, errors, imagePath, passed: errors.length === 0 };
    await writeFile(join(directory, `${page.id}-inspection.json`), JSON.stringify(report), { mode: 0o600 });
    return { report, image };
  } finally {
    clearTimeout(timer);
    await browser.close();
  }
}