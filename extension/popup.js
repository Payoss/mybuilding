// mybuilding — Popup logic (MV3 CSP-compliant, no inline handlers)

let _isDetailMode = false;
let _isChatMode = false;

function _isDetailUrl(url) {
  return /\/jobs\/~[a-zA-Z0-9]+/.test(url) || /\/nx\/search\/jobs\/details\/~[a-zA-Z0-9]+/.test(url);
}
function _isChatUrl(url) {
  return url.includes('/messages/rooms/') || url.includes('/ab/messages/') || url.includes('/nx/messages/');
}

function updateScanMode(url) {
  _isDetailMode = _isDetailUrl(url || '');
  _isChatMode = _isChatUrl(url || '');
  const btn = document.getElementById('scanBtn');
  const hint = document.getElementById('scan-hint');
  if (_isChatMode) {
    btn.textContent = '💬 Scan the chat';
    hint.textContent = 'Extrait les messages de cette conversation et les sync dans le CRM';
  } else if (_isDetailMode) {
    btn.textContent = '🔍 Enrichir ce job';
    hint.textContent = 'Mode détail — récupère la description complète et met à jour le CRM';
  } else {
    btn.textContent = '⚡ Scan This Page';
    hint.textContent = "Scans the current Upwork search page you're viewing — manual only, no auto-refresh";
  }
}

function switchTab(tab, el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('tab-' + tab).classList.add('active');
}

function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2000);
}

function scanNow() {
  const btn = document.getElementById('scanBtn');
  btn.textContent = '⏳ En cours...';
  btn.disabled = true;
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tabId = tabs[0]?.id;
    chrome.runtime.sendMessage({ type: 'CHECK_NOW', tabId }, () => {
      btn.textContent = _isChatMode ? '💬 Scan the chat' : _isDetailMode ? '🔍 Enrichir ce job' : '⚡ Scan This Page';
      btn.disabled = false;
      toast(_isChatMode ? 'Chat synchronisé ✓' : _isDetailMode ? 'Job enrichi ✓' : 'Scan terminé ✓');
      loadStatus();
    });
  });
}

function openMybuilding() {
  chrome.tabs.create({ url: 'https://mybuilding.dev/upwork.html' });
}

function saveSettings() {
  const settings = {
    supabaseUrl: document.getElementById('inp-url').value.trim(),
    supabaseKey: document.getElementById('inp-key').value.trim()
  };
  chrome.runtime.sendMessage({ type: 'UPDATE_SETTINGS', settings }, () => {
    toast('Settings sauvés ✓');
    loadStatus();
  });
}

function loadStatus() {
  chrome.runtime.sendMessage({ type: 'GET_STATUS' }, (data) => {
    if (!data) return;
    const s = data.mb_settings || {};
    const connected = !!(s.supabaseUrl && s.supabaseKey);
    document.getElementById('sb-status').innerHTML = connected
      ? '<span class="status-dot dot-ok"></span> Connecté'
      : '<span class="status-dot dot-err"></span> Non configuré';
    if (data.mb_last_check) {
      const d = new Date(data.mb_last_check);
      document.getElementById('last-check').textContent = d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
    }
    document.getElementById('last-count').textContent = data.mb_last_count || 0;
    document.getElementById('last-snipers').textContent = data.mb_last_snipers || 0;
    document.getElementById('last-golds').textContent = data.mb_last_golds || 0;
    if (s.supabaseUrl) document.getElementById('inp-url').value = s.supabaseUrl;
    if (s.supabaseKey) document.getElementById('inp-key').value = s.supabaseKey;
  });
}

// Event listeners (MV3 CSP — no inline onclick allowed)
document.getElementById('tab-btn-status').addEventListener('click', function() { switchTab('status', this); });
document.getElementById('tab-btn-settings').addEventListener('click', function() { switchTab('settings', this); });
document.getElementById('scanBtn').addEventListener('click', scanNow);
document.getElementById('openBtn').addEventListener('click', openMybuilding);
document.getElementById('saveBtn').addEventListener('click', saveSettings);
document.getElementById('reloadBtn').addEventListener('click', () => chrome.runtime.reload());
document.getElementById('clearCacheBtn').addEventListener('click', () => {
  chrome.storage.local.remove('mb_seen_ids', () => toast('Cache vidé ✓'));
});

// Detect active tab context to set scan mode
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  updateScanMode(tabs[0]?.url || '');
});

loadStatus();
