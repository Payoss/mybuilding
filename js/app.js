// ============================================================
// mybuilding.dev — Shared utilities
// ============================================================

// ---- Logo SVG ----
var LOGO_SVG = `<svg width="18" height="18" viewBox="0 0 18 18" fill="none">
  <rect x="3" y="8" width="12" height="9" rx="1" fill="white" opacity="0.9"/>
  <path d="M1.5 9L9 2L16.5 9" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  <rect x="7" y="12" width="4" height="5" rx="0.5" fill="rgba(13,148,136,0.9)"/>
  <rect x="4.5" y="10" width="2.5" height="2.5" rx="0.4" fill="rgba(13,148,136,0.7)"/>
  <rect x="11" y="10" width="2.5" height="2.5" rx="0.4" fill="rgba(13,148,136,0.7)"/>
</svg>`;

// ---- Formatters ----
function fmtEur(n) {
  if (n == null || n === '') return '€0';
  n = parseFloat(n);
  if (n >= 1000) return '€' + (n / 1000).toFixed(1).replace('.0', '') + 'K';
  return '€' + n.toLocaleString('fr-FR');
}

function fmtDate(d) {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' });
}

function fmtRelative(d) {
  if (!d) return '—';
  const diff = (Date.now() - new Date(d)) / 1000;
  if (diff < 3600) return Math.floor(diff / 60) + 'm';
  if (diff < 86400) return Math.floor(diff / 3600) + 'h';
  if (diff < 604800) return Math.floor(diff / 86400) + 'j';
  return fmtDate(d);
}

// ---- Stage badge ----
var STAGE_MAP = {
  lead:        ['teal',   'Lead'],
  proposal:    ['blue',   'Proposition'],
  active:      ['green',  'Actif'],
  inactive:    ['t3',     'Inactif'],
  churned:     ['red',    'Churned'],
  prospect:    ['teal',   'Prospect'],
  negotiation: ['amber',  'Négo'],
  won:         ['green',  'Won'],
  lost:        ['red',    'Lost'],
  paused:      ['t3',     'Pause'],
};

function stageBadge(stage) {
  var m = STAGE_MAP[stage] || ['t3', stage || '—'];
  return '<span class="status-chip sc-' + m[0] + '">' + m[1] + '</span>';
}

function scorePill(score) {
  if (score == null) return '<span class="muted">—</span>';
  var cls;
  if (score <= 10) {
    // Scale /10 (worth_score)
    cls = score >= 8 ? 'sp-high' : score >= 6 ? 'sp-med' : 'sp-low';
  } else {
    // Scale /100 (feasibility)
    cls = score >= 75 ? 'sp-high' : score >= 55 ? 'sp-med' : 'sp-low';
  }
  return '<span class="score-pill ' + cls + '">' + score + '</span>';
}

// ---- Toast ----
function toast(msg, type) {
  type = type || 'success';
  var t = document.createElement('div');
  t.className = 'toast toast-' + type;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function() { t.classList.add('show'); }, 10);
  setTimeout(function() {
    t.classList.remove('show');
    setTimeout(function() { t.remove(); }, 300);
  }, 3000);
}

// ---- Sidebar HTML ----
function renderSidebar(activePage) {
  var links = [
    { page: 'dashboard', href: '/dashboard.html', icon: '<path d="M2 3h5v5H2zm7 0h5v5H9zm-7 7h5v5H2zm7 0h5v5H9z"/>', label: 'Dashboard' },
    { page: 'crm',       href: '/crm.html',       icon: '<path d="M8 8a3 3 0 100-6 3 3 0 000 6zm-5 5a5 5 0 0110 0H3z"/>', label: 'CRM' },
    { page: 'upwork',    href: '/upwork.html',     icon: '<path d="M13 2H3a1 1 0 00-1 1v10a1 1 0 001 1h10a1 1 0 001-1V3a1 1 0 00-1-1zM6 9H4V7h2v2zm0-3H4V4h2v2zm3 3H7V7h2v2zm0-3H7V4h2v2zm3 3h-2V7h2v2zm0-3h-2V4h2v2z"/>', label: 'Upwork' },
    { page: 'calendar',  href: '/calendar.html',   icon: '<path d="M12 2H4a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2V4a2 2 0 00-2-2zM4 6h8v6H4V6zm1-3h2v1H5V3zm4 0h2v1H9V3z"/>', label: 'Calendrier' },
  ];
  var financeLinks = [
    { page: 'invoices', href: '/invoices.html', icon: '<path d="M2 3a1 1 0 011-1h10a1 1 0 011 1v1H2V3zm0 3h12v8a1 1 0 01-1 1H3a1 1 0 01-1-1V6z"/>', label: 'Factures' },
    { page: 'quotes',   href: '/quotes.html',   icon: '<path d="M2 2h12v2H2V2zm0 3h12v9H2V5z"/>', label: 'Devis' },
  ];

  function navItem(item) {
    var cls = item.page === activePage ? ' active' : '';
    return '<a class="nav-item' + cls + '" href="' + item.href + '" data-page="' + item.page + '">'
      + '<svg viewBox="0 0 16 16" fill="currentColor">' + item.icon + '</svg>'
      + item.label + '</a>';
  }

  return '<div class="blob blob-1"></div><div class="blob blob-2"></div>'
    + '<aside class="sidebar">'
    + '<div class="sidebar-top">'
    + '<div class="logo">' + LOGO_SVG + '</div>'
    + '<div><div class="logo-name">mybuilding</div><div class="logo-domain">mybuilding.dev</div></div>'
    + '</div>'
    + '<div class="nav-section"><div class="nav-label">Workspace</div>'
    + links.map(navItem).join('')
    + '</div>'
    + '<div class="nav-section"><div class="nav-label">Finance</div>'
    + financeLinks.map(navItem).join('')
    + '</div>'
    + '<div class="sidebar-bottom"><div class="user-row">'
    + '<div class="user-av">PA</div>'
    + '<div style="flex:1;min-width:0"><div class="user-name">Paul Annes</div><div class="user-plan">Freelance</div></div>'
    + '<div class="online-dot"></div>'
    + '</div></div></aside>';
}
