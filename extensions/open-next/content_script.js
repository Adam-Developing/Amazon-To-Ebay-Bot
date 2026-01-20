// Listen for page messages from the web app and forward to the extension background script
window.addEventListener('message', (event) => {
  if (!event || !event.data) return;
  const d = event.data;
  if (d && d.type === 'amazonToEbay_open_url_request' && d.url) {
    try {
      // Ensure the chrome.runtime API is available
      if (window.chrome && chrome.runtime && typeof chrome.runtime.sendMessage === 'function') {
        chrome.runtime.sendMessage({ type: 'amazonToEbay_open_url_from_content', url: d.url }, () => {
          // Notify the page that we handled it so it won't open another tab
          try {
            window.postMessage({ type: 'amazonToEbay_open_url_handled', url: d.url }, '*');
          } catch (e) {
            // ignore
          }
        });
      }
      // If the runtime is not available, do nothing and let the page fallback to opening a tab.
    } catch (err) {
      // If the extension is being reloaded/unloaded this call can throw "Extension context invalidated".
      // Swallow the error so it doesn't crash the page; letting the page fallback open a tab.
    }
  }
});
