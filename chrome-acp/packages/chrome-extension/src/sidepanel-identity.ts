const LEGACY_SESSION_KEY = "sidepanel_last_session";
const MIGRATION_WINDOW_KEY = "sidepanel_legacy_session_window";

/** One browser window owns one reconnect identity for this browser lifetime. */
export async function loadSidepanelIdentity() {
  const window = await chrome.windows.getCurrent();
  if (window.id === undefined) throw new Error("Unable to identify the sidepanel window");
  const identityKey = `sidepanel_connection:${window.id}`;
  const lastSessionKey = `${LEGACY_SESSION_KEY}:${window.id}`;
  const [session, local] = await Promise.all([
    chrome.storage.session.get([identityKey, MIGRATION_WINDOW_KEY]),
    chrome.storage.local.get([lastSessionKey, LEGACY_SESSION_KEY]),
  ]);
  const previousId = session[identityKey];
  const retentionId = typeof previousId === "string" && /^[a-f0-9-]{36}$/i.test(previousId)
    ? previousId : crypto.randomUUID();
  const migrate = session[MIGRATION_WINDOW_KEY] === undefined;
  await chrome.storage.session.set({
    [identityKey]: retentionId,
    ...(migrate ? { [MIGRATION_WINDOW_KEY]: window.id } : {}),
  });
  // Preserve the old single-window history once, then scope new history to
  // its window so opening a second sidepanel cannot replace the first thread.
  const last = local[lastSessionKey] ?? (migrate ? local[LEGACY_SESSION_KEY] : null);
  if (last && local[lastSessionKey] === undefined) {
    await chrome.storage.local.set({ [lastSessionKey]: last });
  }
  const lastSession = last && typeof last === "object" && "sessionId" in last
    && typeof last.sessionId === "string"
    ? { sessionId: last.sessionId } : null;
  return { retentionId, lastSessionKey, lastSession };
}