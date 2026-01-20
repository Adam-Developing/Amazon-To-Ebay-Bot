Install instructions for the Open-Next extension

This small Chrome/Chromium extension listens for messages posted by the web app (the Amazon-To-Ebay-Bot UI) and opens requested external URLs in a new tab immediately to the right of the tab that hosts the UI.

How it works
- The web app posts a window message { type: 'amazonToEbay_open_url_request', url }.
- The extension content script receives the message and sends it to the background service worker.
- The background worker opens a new tab at index (senderTab.index + 1), focusing it.
- The content script posts back a message { type: 'amazonToEbay_open_url_handled', url } to the page so it doesn't open another tab.

To load the extension in Chrome/Edge/Brave (developer mode):
1. Open chrome://extensions/
2. Enable "Developer mode"
3. Click "Load unpacked"
4. Select this `extensions/open-next/` directory.

Notes and limitations
- Browser tabs and their placement are controlled by the browser; a normal web page cannot control tab ordering. This extension uses the tabs API to open the tab at the desired index.
- This extension will only work in Chromium-based browsers that support Manifest V3 and the `tabs` permission.
- When testing, ensure you load the extension and then open the app page in a tab so the extension can open adjacent tabs.

If you'd like, I can also:
- Add an options page to toggle whether the opened tab should be focused.
- Package the extension into a .zip for easy installation.
