import { OPEN_SIDEPANEL_MESSAGE } from "./launcher";

export function registerFloatingLauncher(
  api: Pick<typeof chrome, "runtime" | "sidePanel">,
): void {
  api.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type !== OPEN_SIDEPANEL_MESSAGE) return;
    if (
      sender.id !== api.runtime.id ||
      sender.frameId !== 0 ||
      !Number.isInteger(sender.tab?.id)
    ) {
      sendResponse({ ok: false, error: "A top-level extension content script is required" });
      return;
    }
    try {
      // No asynchronous work before open(): it must retain the click's user gesture.
      api.sidePanel.open({ tabId: sender.tab!.id! }).then(
        () => sendResponse({ ok: true }),
        (error: unknown) => sendResponse({
          ok: false,
          error: error instanceof Error ? error.message : String(error),
        }),
      );
    } catch (error) {
      sendResponse({
        ok: false,
        error: error instanceof Error ? error.message : String(error),
      });
    }
    return true;
  });
}