chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (!msg || msg.type !== 'amazonToEbay_open_url_from_content') return;
  const targetUrl = msg.url;
  // Determine the sender tab index; open a new tab to the right of it
  chrome.tabs.get(sender.tab.id, (tab) => {
    const createProps = { url: targetUrl, index: tab.index + 1, active: false };
    chrome.tabs.create(createProps, () => {
      // Do NOT focus the new tab (active: false ensures this)
      // Send acknowledgement back to content script
      sendResponse({ ok: true });
    });
  });
  // Indicate we'll call sendResponse asynchronously
  return true;
});
