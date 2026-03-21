// ============================================================
// mybuilding.dev — Shared utilities
// ============================================================

// ---- Logo SVG ----
var LOGO_SVG = `<svg width="18" height="18" viewBox="0 0 18 18" fill="none">
  <rect x="3" y="8" width="12" height="9" rx="1" fill="white" opacity="0.9"/>
  <path d="M1.5 9L9 2L16.5 9" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
  <rect x="7" y="12" width="4" height="5" rx="0.5" fill="rgba(45,212,191,0.9)"/>
  <rect x="4.5" y="10" width="2.5" height="2.5" rx="0.4" fill="rgba(45,212,191,0.7)"/>
  <rect x="11" y="10" width="2.5" height="2.5" rx="0.4" fill="rgba(45,212,191,0.7)"/>
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

// ---- Create / Edit Contact Modal ----
// openCreateClientModal(jobOrNull, callback, existingContact?)
// - job: upwork_jobs row (CREATE mode) or null
// - existingContact: contacts row (EDIT mode) — also accepted as first param for openContactEdit pattern
// - callback(contact): called with the saved/updated contact object
function openCreateClientModal(jobOrNull, callback, existingContact) {
  // Support: openCreateClientModal(existingContact, cb, existingContact) from openContactEdit
  var isEdit = !!existingContact;
  var job = isEdit ? null : (jobOrNull && !jobOrNull.name ? jobOrNull : null);
  var contact = existingContact || null;

  var old = document.getElementById('_ccm_overlay');
  if (old) old.remove();

  // ── Prefill values ──
  var name     = (contact && contact.name)    || '';
  var email    = (contact && contact.email)   || '';
  var company  = (contact && contact.company) || '';
  var phone    = (contact && contact.phone)   || '';
  var stage    = (contact && contact.stage)   || 'lead';
  var notes    = (contact && contact.notes)   || '';
  var country  = (contact && contact.country) || (job && job.country ? job.country.replace(/^Location\s+/i,'') : '');
  var linkedin = (contact && contact.linkedin_url) || '';

  var modalTitle = isEdit ? 'Modifier le contact' : 'Nouveau contact client';
  var btnLabel   = isEdit ? 'Enregistrer' : 'Créer le contact';

  // ── Overlay ──
  var ov = document.createElement('div');
  ov.id = '_ccm_overlay';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.65);z-index:500;display:flex;align-items:center;justify-content:center;padding:20px;box-sizing:border-box;backdrop-filter:blur(6px)';

  // ── Modal ──
  var STAGES = [
    {v:'lead',lbl:'Lead'},{v:'prospect',lbl:'Prospect'},{v:'active',lbl:'Actif'},
    {v:'negotiation',lbl:'Négo'},{v:'won',lbl:'Won'},{v:'inactive',lbl:'Inactif'},
    {v:'lost',lbl:'Lost'},{v:'churned',lbl:'Churned'}
  ];
  var stageOpts = STAGES.map(function(s){
    return '<option value="'+s.v+'"'+(stage===s.v?' selected':'')+'>'+s.lbl+'</option>';
  }).join('');

  var jobBadge = (!isEdit && job)
    ? '<div style="background:rgba(45,212,191,0.08);border:1px solid rgba(45,212,191,0.2);border-radius:8px;padding:8px 12px;margin-bottom:14px;font-size:11px;color:var(--teal,#2dd4bf)">'+
      '🔗 Job : <span style="color:#e2e8f0;font-weight:500">'+
      (job.title||'Sans titre').substring(0,70)+'</span></div>'
    : '';

  ov.innerHTML =
    '<div style="background:#0f0f17;border:1px solid rgba(255,255,255,0.09);border-radius:14px;width:100%;max-width:480px;max-height:90vh;overflow-y:auto;box-shadow:0 24px 80px rgba(0,0,0,0.6)">'+
      '<div style="display:flex;align-items:center;justify-content:space-between;padding:18px 22px 14px;border-bottom:1px solid rgba(255,255,255,0.06)">'+
        '<div style="font-size:15px;font-weight:700;color:#f1f5f9">'+modalTitle+'</div>'+
        '<button id="_ccm_close" style="background:none;border:none;color:#64748b;cursor:pointer;font-size:20px;padding:2px 8px;border-radius:6px;line-height:1;transition:all 0.15s" onmouseover="this.style.color=\'#f1f5f9\'" onmouseout="this.style.color=\'#64748b\'">✕</button>'+
      '</div>'+
      '<div style="padding:18px 22px 22px">'+
        jobBadge+
        '<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">'+
          '<div style="grid-column:1/-1">'+
            '<label style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px">Nom complet *</label>'+
            '<input id="_ccm_name" type="text" value="'+_ccmEsc(name)+'" placeholder="John Smith" style="'+_ccmInput()+'" required>'+
          '</div>'+
          '<div>'+
            '<label style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px">Email</label>'+
            '<input id="_ccm_email" type="email" value="'+_ccmEsc(email)+'" placeholder="john@company.com" style="'+_ccmInput()+'">'+
          '</div>'+
          '<div>'+
            '<label style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px">Entreprise</label>'+
            '<input id="_ccm_company" type="text" value="'+_ccmEsc(company)+'" placeholder="Acme Corp" style="'+_ccmInput()+'">'+
          '</div>'+
          '<div>'+
            '<label style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px">Téléphone</label>'+
            '<input id="_ccm_phone" type="text" value="'+_ccmEsc(phone)+'" placeholder="+33 6 00 00 00 00" style="'+_ccmInput()+'">'+
          '</div>'+
          '<div>'+
            '<label style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px">Pays</label>'+
            '<input id="_ccm_country" type="text" value="'+_ccmEsc(country)+'" placeholder="France" style="'+_ccmInput()+'">'+
          '</div>'+
          '<div>'+
            '<label style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px">Étape</label>'+
            '<select id="_ccm_stage" style="'+_ccmInput()+'cursor:pointer">'+stageOpts+'</select>'+
          '</div>'+
          '<div style="grid-column:1/-1">'+
            '<label style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px">LinkedIn</label>'+
            '<input id="_ccm_linkedin" type="url" value="'+_ccmEsc(linkedin)+'" placeholder="https://linkedin.com/in/..." style="'+_ccmInput()+'">'+
          '</div>'+
          '<div style="grid-column:1/-1">'+
            '<label style="font-size:10px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.06em;display:block;margin-bottom:5px">Notes</label>'+
            '<textarea id="_ccm_notes" rows="3" placeholder="Notes..." style="'+_ccmInput()+'resize:vertical;min-height:60px;line-height:1.5">'+_ccmEsc(notes)+'</textarea>'+
          '</div>'+
        '</div>'+
        '<div id="_ccm_err" style="display:none;background:rgba(248,113,113,0.08);border:1px solid rgba(248,113,113,0.25);border-radius:8px;padding:8px 12px;font-size:12px;color:#f87171;margin-top:12px"></div>'+
        '<div style="display:flex;gap:8px;margin-top:16px">'+
          '<button id="_ccm_cancel" style="flex:1;padding:11px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:9px;color:#94a3b8;font-family:inherit;font-size:13px;cursor:pointer;transition:all 0.15s">Annuler</button>'+
          '<button id="_ccm_submit" style="flex:2;padding:11px;background:#2dd4bf;border:none;border-radius:9px;color:white;font-family:inherit;font-size:13px;font-weight:700;cursor:pointer;transition:all 0.15s;box-shadow:0 0 20px rgba(45,212,191,0.3)">'+btnLabel+'</button>'+
        '</div>'+
      '</div>'+
    '</div>';

  document.body.appendChild(ov);

  // Focus name
  setTimeout(function(){ var n=document.getElementById('_ccm_name'); if(n)n.focus(); }, 80);

  // Close handlers
  function closeModal() { ov.remove(); }
  document.getElementById('_ccm_close').addEventListener('click', closeModal);
  document.getElementById('_ccm_cancel').addEventListener('click', closeModal);
  ov.addEventListener('click', function(e){ if(e.target===ov) closeModal(); });

  // Hover styles on buttons
  var submitBtn = document.getElementById('_ccm_submit');
  submitBtn.addEventListener('mouseover', function(){ this.style.opacity='.88'; });
  submitBtn.addEventListener('mouseout', function(){ this.style.opacity='1'; });

  // ── Submit ──
  document.getElementById('_ccm_submit').addEventListener('click', async function() {
    var nameVal = (document.getElementById('_ccm_name').value||'').trim();
    if (!nameVal) {
      var err = document.getElementById('_ccm_err');
      err.textContent = 'Le nom est obligatoire.';
      err.style.display = 'block';
      document.getElementById('_ccm_name').style.borderColor = '#f87171';
      return;
    }

    submitBtn.textContent = '⏳ Enregistrement...';
    submitBtn.disabled = true;

    var payload = {
      name:    nameVal,
      email:   (document.getElementById('_ccm_email').value||'').trim()||null,
      company: (document.getElementById('_ccm_company').value||'').trim()||null,
      phone:   (document.getElementById('_ccm_phone').value||'').trim()||null,
      country: (document.getElementById('_ccm_country').value||'').trim()||null,
      stage:   document.getElementById('_ccm_stage').value,
      linkedin_url: (document.getElementById('_ccm_linkedin').value||'').trim()||null,
      notes:   (document.getElementById('_ccm_notes').value||'').trim()||null,
    };

    if (!isEdit) {
      payload.source = 'upwork';
      if (job && job.id)  payload.upwork_job_id = job.id;
      if (job && job.url) payload.upwork_url = job.url;
    }

    try {
      var saved;
      if (isEdit && contact && contact.id) {
        // UPDATE — try with new columns first, fallback without
        var { data, error } = await sb.from('contacts').update(payload).eq('id', contact.id).select().single();
        if (error) {
          // Fallback: remove columns that might not exist yet
          var safe = Object.assign({}, payload);
          delete safe.upwork_job_id; delete safe.upwork_url;
          var r2 = await sb.from('contacts').update(safe).eq('id', contact.id).select().single();
          if (r2.error) throw r2.error;
          data = r2.data;
        }
        saved = data || Object.assign({}, contact, payload);
      } else {
        // INSERT
        var { data, error } = await sb.from('contacts').insert(payload).select().single();
        if (error) {
          // Fallback without new columns
          var safe = Object.assign({}, payload);
          delete safe.upwork_job_id; delete safe.upwork_url;
          var r2 = await sb.from('contacts').insert(safe).select().single();
          if (r2.error) throw r2.error;
          data = r2.data;
        }
        saved = data || Object.assign({id: '_local_'+Date.now()}, payload);
      }

      closeModal();
      if (typeof toast === 'function') toast(isEdit ? 'Contact mis à jour ✓' : 'Contact créé ✓');
      if (typeof callback === 'function') callback(saved);

    } catch(e) {
      var err = document.getElementById('_ccm_err');
      if (err) { err.textContent = 'Erreur : '+(e.message||e); err.style.display='block'; }
      submitBtn.textContent = btnLabel;
      submitBtn.disabled = false;
    }
  });
}

// ── Modal input style helper (shared) ──
function _ccmInput() {
  return 'width:100%;padding:8px 11px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:8px;color:#f1f5f9;font-family:inherit;font-size:12px;outline:none;box-sizing:border-box;transition:border-color 0.15s;';
}
function _ccmEsc(s) {
  return s ? String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;') : '';
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
    + '<div class="sidebar-bottom">'
    + '<div class="user-row">'
    + '<div class="user-av">PA</div>'
    + '<div style="flex:1;min-width:0"><div class="user-name">Paul Annes</div><div class="user-plan">Freelance</div></div>'
    + '<div class="online-dot"></div>'
    + '</div>'
    + '<div style="padding:6px 8px 2px"><button onclick="sessionStorage.removeItem(\'mb_auth\');window.location.href=\'/landing.html\'" style="width:100%;padding:6px 0;border-radius:6px;background:rgba(251,113,133,0.08);border:1px solid rgba(251,113,133,0.15);color:#fb7185;font-size:11px;font-weight:500;cursor:pointer;font-family:inherit;transition:all 0.15s" onmouseover="this.style.background=\'rgba(251,113,133,0.15)\'" onmouseout="this.style.background=\'rgba(251,113,133,0.08)\'">Déconnexion</button></div>'
    + '</div></aside>';
}
