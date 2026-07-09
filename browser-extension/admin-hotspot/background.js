const ADMIN_URL = "http://127.0.0.1:8750/admin";
const OPEN_ADMIN_API = "http://127.0.0.1:8750/api/open-admin";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "stay-compass-open-admin") {
    return false;
  }

  const tabId = sender.tab && sender.tab.id;
  if (typeof tabId !== "number") {
    sendResponse({ ok: false });
    return false;
  }

  (async () => {
    try {
      const response = await fetch(OPEN_ADMIN_API, { method: "POST" });

      if (!response.ok) {
        console.info("Admin hotspot denied by local admin service.", response.status);
        sendResponse({ ok: false, status: response.status });
        return;
      }

      await chrome.tabs.update(tabId, { url: ADMIN_URL });
      sendResponse({ ok: true });
    } catch (error) {
      console.error("Admin hotspot failed to reach local admin service.", error);
      sendResponse({ ok: false, error: String(error) });
    }
  })();

  return true;
});
