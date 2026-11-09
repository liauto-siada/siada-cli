// The fixture deliberately omits browser executors: UI verification must
// never register a test executor with the user's running proxy.
chrome.runtime.onMessage.addListener(() => {});