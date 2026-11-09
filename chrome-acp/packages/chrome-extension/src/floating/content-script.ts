import { mountFloatingLauncher, OPEN_SIDEPANEL_MESSAGE } from "./launcher";

// Only the top-level page gets an entry point; never duplicate it in iframes.
if (window === window.top) {
  mountFloatingLauncher(
    document,
    chrome.runtime.getURL("icons/icon48.png"),
    async () => {
      const response = await chrome.runtime.sendMessage({ type: OPEN_SIDEPANEL_MESSAGE });
      if (response?.ok !== true) {
        throw new Error(response?.error || "The extension did not open the side panel");
      }
    },
  );
}