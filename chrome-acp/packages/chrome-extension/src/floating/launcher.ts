export const OPEN_SIDEPANEL_MESSAGE = "siada:open-sidepanel";
export const FLOATING_LAUNCHER_ID = "siada-floating-launcher";

/** Mount one lightweight page entry point, isolated from the website's CSS. */
export function mountFloatingLauncher(
  doc: Document,
  iconUrl: string,
  openSidepanel: () => Promise<void>,
): void {
  if (doc.getElementById(FLOATING_LAUNCHER_ID)) return;

  const host = doc.createElement("div");
  host.id = FLOATING_LAUNCHER_ID;
  // Reset the host as well as the shadow content: website styles can target divs.
  host.style.cssText = "all:initial!important;position:fixed!important;right:0!important;top:50%!important;width:44px!important;height:44px!important;z-index:2147483647!important;display:block!important;visibility:visible!important;opacity:1!important;pointer-events:auto!important;";
  const shadow = host.attachShadow({ mode: "open" });
  const style = doc.createElement("style");
  style.textContent = `
    :host { color-scheme: light; }
    button {
      box-sizing: border-box; width: 44px; height: 44px; padding: 5px;
      border: 1px solid #d5dfe5; border-radius: 50%; background: white;
      box-shadow: 0 2px 10px #24394e24; cursor: pointer;
      display: grid; place-items: center;
      transform: translate(50%, -50%);
      transition: transform 160ms ease-out;
    }
    button:hover,button:focus-visible { transform: translate(0, -50%); }
    button:focus-visible { outline: 2px solid #71a8fb; outline-offset: -3px; }
    img { width: 32px; height: 32px; pointer-events: none; }
    button[data-error] { border-color: #c66b6b; }
    @media (prefers-reduced-motion: reduce) { button { transition: none; } }
    @media print { button { display: none; } }
  `;
  const button = doc.createElement("button");
  button.type = "button";
  button.title = "Open Siada";
  button.setAttribute("aria-label", "Open Siada side panel");
  const icon = doc.createElement("img");
  icon.src = iconUrl;
  icon.alt = "";
  icon.draggable = false;
  button.append(icon);
  button.addEventListener("click", async () => {
    if (button.disabled) return;
    button.removeAttribute("data-error");
    button.title = "Open Siada";
    button.disabled = true;
    try {
      // Invoke immediately in the click handler to preserve Chrome's user gesture.
      await openSidepanel();
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      button.dataset.error = "true";
      button.title = `Unable to open Siada: ${message}. Click to retry.`;
      button.setAttribute("aria-label", button.title);
    } finally {
      button.disabled = false;
      if (!button.hasAttribute("data-error")) {
        button.setAttribute("aria-label", "Open Siada side panel");
      }
    }
  });
  shadow.append(style, button);
  doc.documentElement.append(host);
}