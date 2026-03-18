// mybuilding.dev ↔ Extension Bridge
// Injected on mybuilding.dev pages — relays messages between the page and the extension background script.
// upwork.html sends postMessage → bridge.js → chrome.runtime.sendMessage → background.js

(function() {
  window.addEventListener('message', function(event) {
    if (event.source !== window) return;
    if (!event.data || event.data.source !== 'mybuilding-page') return;

    // Forward to extension background
    chrome.runtime.sendMessage(event.data.payload, function(response) {
      window.postMessage({
        source: 'mybuilding-extension',
        id: event.data.id,
        response: response || { error: chrome.runtime.lastError?.message || 'no response' }
      }, '*');
    });
  });

  // Signal to the page that extension bridge is ready
  window.postMessage({ source: 'mybuilding-extension', type: 'BRIDGE_READY' }, '*');
})();
