chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== 'amazonToEbay_open_url_from_content') return;
  const targetUrl = msg.url;
  const sourceTab = sender.tab;
  if (!sourceTab || typeof sourceTab.id !== 'number') {
    sendResponse({ ok: false, error: 'Missing sender tab context' });
    return;
  }

  // Open the tab in the same window without activating it.
  chrome.tabs.create(
    {
      url: targetUrl,
      windowId: sourceTab.windowId,
      index: sourceTab.index + 1,
      active: false,
      openerTabId: sourceTab.id,
    },
    (createdTab) => {
      if (chrome.runtime.lastError) {
        sendResponse({ ok: false, error: chrome.runtime.lastError.message });
        return;
      }

      sendResponse({ ok: true, tabId: createdTab && createdTab.id });
    }
  );
  // Indicate we'll call sendResponse asynchronously
  return true;
});
