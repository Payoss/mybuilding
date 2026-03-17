// mybuilding.dev — Background Service Worker (TOS-Safe Mode)
// Manual-only scan: user clicks "Scan Now" while on Upwork search page
// NO automatic polling, NO alarms — compliant with Upwork TOS
// Scoring engine runs locally (instant, no network)

const CONFIG = {
  SUPABASE_URL: '',   // Set in popup settings
  SUPABASE_KEY: '',   // Set in popup settings
  MAX_JOBS_PER_CYCLE: 50
};

// ══════════════════════════════════════════════════════════════
// SCORING ENGINE — inline (no network needed, instant)
// ══════════════════════════════════════════════════════════════

const FEAS_BOOSTS = {
  'n8n': 20, 'make.com': 18, 'zapier': 12, 'integromat': 10,
  'workflow automation': 18, 'workflow': 12, 'automation': 14,
  'telegram bot': 20, 'telegram': 16,
  'whatsapp business': 20, 'whatsapp': 16, 'twilio': 16,
  'claude': 20, 'anthropic': 18, 'claude api': 20,
  'ai agent': 18, 'autonomous agent': 18, 'agentic': 16,
  'multi-agent': 14, 'multi agent': 14, 'langgraph': 12, 'crewai': 10,
  'llm': 12, 'gpt': 8, 'openai': 10,
  'chatbot': 14, 'conversational ai': 12,
  'rag': 16, 'rag pipeline': 18, 'retrieval': 14,
  'vector': 12, 'embedding': 12, 'pinecone': 14, 'chroma': 12,
  'knowledge base': 14, 'document qa': 16,
  'mcp': 16, 'model context protocol': 18, 'mcp server': 18,
  'airtable': 14, 'google sheets': 12, 'notion': 8,
  'supabase': 12, 'railway': 12,
  'python': 12, 'fastapi': 12, 'flask': 8,
  'webhook': 12, 'api integration': 14, 'rest api': 12,
  'email automation': 16, 'mailchimp': 12, 'sendgrid': 12,
  'crm automation': 16, 'lead qualification': 14, 'lead generation': 12,
  'browser automation': 14, 'playwright': 12, 'selenium': 10,
  'voice agent': 12, 'voice ai': 12,
  'invoice': 12, 'pdf extraction': 14, 'ocr': 10, 'pdf': 10,
  'scraping': 12, 'web scraping': 14, 'data extraction': 12,
  'retainer': 14, 'ongoing': 10, 'long term': 10,
};

const FEAS_PENALTIES = {
  'blockchain': -28, 'solidity': -32, 'web3': -25, 'nft': -28, 'defi': -28,
  'ios': -25, 'swift': -25, 'android': -22, 'kotlin': -22,
  'react native': -18, 'flutter': -18,
  'rust': -20, 'c++': -20, 'embedded': -22, 'firmware': -28,
  'unity': -22, 'unreal': -25, 'game development': -18,
  'pytorch': -18, 'tensorflow': -18, 'fine-tuning': -12,
  'kubernetes': -12, 'terraform': -12,
  'volunteer': -30, 'unpaid': -30,
  'wordpress': -15, 'php': -15,
};

const FRENCH_WORDS = [
  'bonjour', 'automatisation', 'besoin', 'développement', 'nous recherchons',
  'notre', 'système', 'créer', 'mise en place', 'gestion', 'données',
  'francophone', 'français', 'france', 'entreprise', 'société',
];

const TIER1_COUNTRIES = [
  'united states', 'canada', 'australia', 'united kingdom', 'germany',
  'netherlands', 'switzerland', 'denmark', 'norway', 'sweden',
  'france', 'singapore', 'ireland', 'belgium',
];

function computeFeasibility(title, description) {
  const text = ((title || '') + ' ' + (description || '')).toLowerCase();
  let score = 45;
  for (const [kw, pts] of Object.entries(FEAS_BOOSTS)) { if (text.includes(kw)) score += pts; }
  for (const [kw, pts] of Object.entries(FEAS_PENALTIES)) { if (text.includes(kw)) score += pts; }
  if ((description || '').length > 300) score += 5;
  if ((description || '').length > 600) score += 5;
  return Math.min(99, Math.max(5, Math.round(score)));
}

function computeWorthScore(title, description, feasibility, budgetMin, budgetMax, budgetType, country, scrapedAt, isFrench) {
  const text = ((title || '') + ' ' + (description || '')).toLowerCase();
  let score = 3.5;

  if (feasibility >= 90) score += 3.5;
  else if (feasibility >= 80) score += 2.5;
  else if (feasibility >= 70) score += 1.5;
  else if (feasibility >= 55) score += 0.5;
  else score -= 1.5;

  let budget = 0;
  if (budgetMin && budgetMax) budget = (budgetMin + budgetMax) / 2;
  else if (budgetMin) budget = budgetMin;
  else if (budgetMax) budget = budgetMax;
  if (budgetType === 'hourly' && budget) budget *= 40;

  if (budget >= 5000) score += 3.5;
  else if (budget >= 3000) score += 3;
  else if (budget >= 1500) score += 2.5;
  else if (budget >= 800) score += 2;
  else if (budget >= 400) score += 1.5;
  else if (budget >= 200) score += 0.8;
  else if (budget > 0 && budget < 50) score -= 2;

  if (text.includes('retainer') || text.includes('ongoing') || text.includes('monthly')) score += 1.5;
  if (text.includes('long term') || text.includes('long-term')) score += 1;
  if (text.includes('urgent') || text.includes('asap')) score += 0.5;

  if (scrapedAt) {
    try {
      const ageMin = (Date.now() - new Date(scrapedAt).getTime()) / 60000;
      if (ageMin < 60) score += 1.5;
      else if (ageMin < 120) score += 0.8;
    } catch (e) {}
  }

  const cl = (country || '').toLowerCase();
  if (TIER1_COUNTRIES.some(c => cl.includes(c))) score += 1;
  if (isFrench) score += 0.5;
  if (text.includes('mcp') || text.includes('model context protocol')) score += 1;
  if (text.includes('rag') || text.includes('rag pipeline')) score += 0.8;
  if (text.includes('volunteer') || text.includes('unpaid')) score -= 5;
  if ((text.includes('quick') || text.includes('simple')) && budget < 100) score -= 1.5;

  return Math.min(10, Math.max(1, Math.round(score * 2) / 2));
}

function detectFrench(title, description, country) {
  if (/\bfrance\b/i.test(country || '')) return true;
  const text = ((title || '') + ' ' + (description || '')).toLowerCase();
  if (FRENCH_WORDS.some(w => text.includes(w))) return true;
  if (/[àâäéèêëîïôùûüç]/i.test((title || '') + (description || ''))) return true;
  return false;
}

function computeSniperMode(feasibility, worthScore, scrapedAt, budgetMin, budgetMax, budgetType) {
  let budget = 0;
  if (budgetMin && budgetMax) budget = (budgetMin + budgetMax) / 2;
  else if (budgetMin) budget = budgetMin;
  else if (budgetMax) budget = budgetMax;
  if (budgetType === 'hourly' && budget) budget *= 40;

  let ageMin = 999;
  if (scrapedAt) {
    try { ageMin = (Date.now() - new Date(scrapedAt).getTime()) / 60000; } catch (e) {}
  }
  return feasibility >= 85 && worthScore >= 8.5 && ageMin < 120 && budget >= 500;
}

function computeTimeEstimate(title, description, feasibility) {
  const text = ((title || '') + ' ' + (description || '')).toLowerCase();
  let h = 8;
  if (text.includes('landing') || text.includes('form')) h = 4;
  if (text.includes('bot') || text.includes('telegram') || text.includes('whatsapp')) h = 6;
  if (text.includes('workflow') || text.includes('n8n') || text.includes('automation')) h = 8;
  if (text.includes('dashboard') || text.includes('crm')) h = 12;
  if (text.includes('saas') || text.includes('auth')) h = 20;
  if (text.includes('agent') || text.includes('ai system')) h = 16;
  if (feasibility < 60) h = Math.round(h * 1.5);
  return h <= 4 ? '2-4h' : h <= 8 ? '4-8h' : h <= 16 ? '1-2j' : '2-4j';
}

function scoreJob(job) {
  const { title, description, country, scraped_at, budget_min, budget_max, budget_type } = job;
  const isFrench = detectFrench(title, description, country);
  const feasibility = computeFeasibility(title, description);
  let worthScore = computeWorthScore(title, description, feasibility, budget_min, budget_max, budget_type, country, scraped_at, isFrench);
  const sniperMode = computeSniperMode(feasibility, worthScore, scraped_at, budget_min, budget_max, budget_type);
  if (sniperMode) worthScore = Math.min(10, worthScore + 2.5);
  const timeEstimate = computeTimeEstimate(title, description, feasibility);
  return { feasibility, worth_score: worthScore, sniper_mode: sniperMode, is_french: isFrench, time_estimate: timeEstimate };
}

// ── Init ──
chrome.runtime.onInstalled.addListener(() => {
  // TOS-Safe: no auto-polling alarm. Scan is manual only (user clicks "Scan Now")
  // Clear any leftover alarm from previous versions
  chrome.alarms.clearAll();
  console.log('[mybuilding BG] Extension installée (TOS-safe mode — scan manuel uniquement)');
});

// ── Load settings from storage ──
async function getSettings() {
  return new Promise(resolve => {
    chrome.storage.local.get(['mb_settings'], ({ mb_settings }) => {
      resolve(mb_settings || {});
    });
  });
}

async function getSupabase() {
  const s = await getSettings();
  return {
    url: s.supabaseUrl || '',
    key: s.supabaseKey || ''
  };
}

// ── Supabase API helper ──
async function supabaseInsert(table, rows) {
  const { url, key } = await getSupabase();
  if (!url || !key) {
    console.warn('[mybuilding BG] Supabase non configuré');
    return { error: 'not_configured' };
  }
  try {
    const res = await fetch(`${url}/rest/v1/${table}?on_conflict=url`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'apikey': key,
        'Authorization': `Bearer ${key}`,
        'Prefer': 'return=representation,resolution=merge-duplicates'
      },
      body: JSON.stringify(rows)
    });
    if (!res.ok) {
      const text = await res.text();
      console.error('[mybuilding BG] Supabase error:', res.status, text);
      return { error: text };
    }
    return { data: await res.json() };
  } catch (e) {
    console.error('[mybuilding BG] Supabase fetch error:', e);
    return { error: e.message };
  }
}

async function supabaseSelect(table, query) {
  const { url, key } = await getSupabase();
  if (!url || !key) return { data: [] };
  try {
    const res = await fetch(`${url}/rest/v1/${table}?${query}`, {
      headers: {
        'apikey': key,
        'Authorization': `Bearer ${key}`
      }
    });
    return { data: await res.json() };
  } catch (e) {
    return { data: [] };
  }
}

// ── Job dedup ──
async function getSeenIds() {
  return new Promise(resolve => {
    chrome.storage.local.get(['mb_seen_ids'], ({ mb_seen_ids }) => {
      resolve(new Set(mb_seen_ids || []));
    });
  });
}

async function addSeenIds(ids) {
  const seen = await getSeenIds();
  ids.forEach(id => seen.add(id));
  // Keep max 500
  const arr = Array.from(seen).slice(-500);
  chrome.storage.local.set({ mb_seen_ids: arr });
}

// ── Main check loop ──
async function checkForNewJobs() {
  console.log('[mybuilding BG] Checking for new jobs...');

  // Find active Upwork tab with search page
  const tabs = await chrome.tabs.query({ url: 'https://www.upwork.com/*' });
  const searchTab = tabs.find(t =>
    t.url.includes('/search/jobs') || t.url.includes('/nx/find-work') || t.url.includes('/nx/search')
  );

  if (!searchTab) {
    console.log('[mybuilding BG] No Upwork search tab found');
    return;
  }

  try {
    let response;
    try {
      response = await chrome.tabs.sendMessage(searchTab.id, { type: 'GET_JOBS_FROM_DOM' });
    } catch (e) {
      // Content script not loaded yet (e.g. after extension reload) — inject it
      console.log('[mybuilding BG] Content script not found, injecting...');
      await chrome.scripting.executeScript({
        target: { tabId: searchTab.id },
        files: ['content.js']
      });
      // Wait for it to initialize
      await new Promise(r => setTimeout(r, 1000));
      response = await chrome.tabs.sendMessage(searchTab.id, { type: 'GET_JOBS_FROM_DOM' });
    }
    const jobs = response?.jobs || [];
    if (!jobs.length) return;

    // Dedup
    const seen = await getSeenIds();
    const newJobs = jobs.filter(j => !seen.has(j.id));
    if (!newJobs.length) {
      console.log('[mybuilding BG] No new jobs');
      return;
    }

    // Dedup by URL within the same batch (PostgREST rejects duplicate keys in one request)
    const urlSeen = new Set();
    const batchDeduped = newJobs.filter(j => {
      if (!j.url || urlSeen.has(j.url)) return false;
      urlSeen.add(j.url);
      return true;
    });
    if (!batchDeduped.length) {
      console.log('[mybuilding BG] No unique new jobs');
      return;
    }

    // Dedup against Supabase — filter URLs already in DB (not deleted)
    const { url: sbUrl, key: sbKey } = await getSupabase();
    let uniqueJobs = batchDeduped;
    if (sbUrl && sbKey) {
      const urlList = batchDeduped.map(j => j.url).filter(Boolean);
      try {
        const res = await fetch(
          `${sbUrl}/rest/v1/upwork_jobs?select=url&url=in.(${urlList.map(u => `"${u}"`).join(',')})`,
          { headers: { 'apikey': sbKey, 'Authorization': `Bearer ${sbKey}` } }
        );
        if (res.ok) {
          const existing = await res.json();
          const existingUrls = new Set(existing.map(r => r.url));
          uniqueJobs = batchDeduped.filter(j => !existingUrls.has(j.url));
          if (existingUrls.size) {
            // Re-sync local cache with whatever Supabase knows
            await addSeenIds(existing.map(r => {
              const m = r.url.match(/~([a-zA-Z0-9]+)/);
              return m ? m[1] : null;
            }).filter(Boolean));
          }
        }
      } catch (e) {
        console.warn('[mybuilding BG] Supabase dedup check failed, proceeding:', e.message);
      }
    }

    if (!uniqueJobs.length) {
      console.log('[mybuilding BG] All jobs already in Supabase');
      return;
    }

    console.log(`[mybuilding BG] ${uniqueJobs.length} new jobs found`);

    // Parse budget + score each job locally
    const supabaseRows = uniqueJobs.map(j => {
      const budgetParsed = parseBudget(j.budget);
      const base = {
        title: j.title,
        description: j.description,
        url: j.url,
        country: j.country,
        scraped_at: j.scraped_at,
        budget_min: budgetParsed.min,
        budget_max: budgetParsed.max,
        budget_type: budgetParsed.type,
        skills: j.skills || [],
        source: 'extension',
        status: 'new'
      };
      // Score locally (instant, no API call)
      const scores = scoreJob(base);
      return { ...base, ...scores };
    });

    // Identify gold/sniper jobs for special notifications
    const sniperJobs = supabaseRows.filter(j => j.sniper_mode);
    const goldJobs = supabaseRows.filter(j => j.worth_score >= 8 && !j.sniper_mode);

    // POST to Supabase
    const result = await supabaseInsert('upwork_jobs', supabaseRows);
    if (!result.error) {
      await addSeenIds(uniqueJobs.map(j => j.id));
      // Update badge
      chrome.action.setBadgeText({ text: String(uniqueJobs.length) });
      chrome.action.setBadgeBackgroundColor({ color: sniperJobs.length ? '#f59e0b' : '#0d9488' });

      // Sniper/Gold notification (priority)
      if (sniperJobs.length > 0) {
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'icon48.png',
          title: `🎯 SNIPER — ${sniperJobs.length} jobs en or !`,
          message: sniperJobs.slice(0, 3).map(j => `${j.worth_score}/10 — ${j.title}`).join('\n')
        });
      } else if (goldJobs.length > 0) {
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'icon48.png',
          title: `⭐ ${goldJobs.length} gold jobs — worth ≥ 8/10`,
          message: goldJobs.slice(0, 3).map(j => `${j.worth_score}/10 — ${j.title}`).join('\n')
        });
      } else if (uniqueJobs.length > 0) {
        chrome.notifications.create({
          type: 'basic',
          iconUrl: 'icon48.png',
          title: `mybuilding — ${uniqueJobs.length} nouveaux jobs`,
          message: uniqueJobs.slice(0, 3).map(j => j.title).join('\n')
        });
      }

      // Store count + scoring summary for popup
      chrome.storage.local.set({
        mb_last_check: new Date().toISOString(),
        mb_last_count: uniqueJobs.length,
        mb_last_snipers: sniperJobs.length,
        mb_last_golds: goldJobs.length
      });

      // Phase 5: Pre-enrich top jobs in background (async, non-blocking)
      const topJobs = supabaseRows.filter(j => j.worth_score >= 7 || j.sniper_mode);
      if (topJobs.length > 0 && result.data) {
        preEnrichJobs(topJobs, result.data).catch(e =>
          console.warn('[mybuilding BG] Pre-enrich error (non-critical):', e.message)
        );
      }
    }
  } catch (e) {
    console.error('[mybuilding BG] Error:', e);
  }
}

// ── Phase 5: Pre-enrich top jobs at scan time ──
async function preEnrichJobs(topJobs, insertedRows) {
  const settings = await getSettings();
  const apiBase = settings.apiUrl || 'https://mybuilding.dev';

  // Match inserted rows to get Supabase IDs
  const idMap = {};
  for (const row of insertedRows) {
    if (row.url) idMap[row.url] = row.id;
  }

  // Pre-enrich up to 3 jobs (avoid overloading)
  const batch = topJobs.slice(0, 3);
  for (const job of batch) {
    try {
      const res = await fetch(`${apiBase}/api/pre-enrich`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: job.title,
          description: job.description,
          skills: job.skills || [],
          budget_min: job.budget_min,
          budget_max: job.budget_max,
          budget_type: job.budget_type,
          country: job.country
        })
      });
      if (!res.ok) continue;
      const enrichData = await res.json();

      // Cache enrichment in Supabase
      const jobId = idMap[job.url];
      if (jobId && enrichData) {
        const { url: sbUrl, key: sbKey } = await getSupabase();
        if (sbUrl && sbKey) {
          await fetch(`${sbUrl}/rest/v1/upwork_jobs?id=eq.${jobId}`, {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
              'apikey': sbKey,
              'Authorization': `Bearer ${sbKey}`,
              'Prefer': 'return=minimal'
            },
            body: JSON.stringify({
              analysis: enrichData,
              status: enrichData.verdict === 'SKIP' ? 'skipped' : 'enriched'
            })
          });
        }
      }
      console.log(`[mybuilding BG] Pre-enriched: ${job.title.slice(0, 50)}`);
    } catch (e) {
      console.warn(`[mybuilding BG] Pre-enrich failed for ${job.title.slice(0, 30)}:`, e.message);
    }
  }
}

function parseBudget(str) {
  if (!str) return { min: null, max: null, type: 'fixed' };
  const isHourly = /\/hr|hourly|per hour/i.test(str);
  const nums = str.match(/[\d,.]+/g);
  if (!nums) return { min: null, max: null, type: isHourly ? 'hourly' : 'fixed' };
  const values = nums.map(n => parseFloat(n.replace(/,/g, ''))).filter(n => !isNaN(n));
  if (values.length >= 2) {
    return { min: Math.min(...values), max: Math.max(...values), type: isHourly ? 'hourly' : 'fixed' };
  }
  if (values.length === 1) {
    return { min: values[0], max: values[0], type: isHourly ? 'hourly' : 'fixed' };
  }
  return { min: null, max: null, type: 'fixed' };
}

// ── Re-générer le plan IA après enrichissement manuel ──
async function _reEnrichPlan(jobId, patch, detail) {
  const { url: sbUrl, key: sbKey } = await getSupabase();
  if (!sbUrl || !sbKey) return;
  const settings = await getSettings();
  const apiBase = settings.apiUrl || 'https://mybuilding.dev';

  const res = await fetch(`${apiBase}/api/pre-enrich`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      title: patch.title || detail.title || '',
      description: detail.description,
      skills: detail.skills || [],
      budget_min: patch.budget_min ?? null,
      budget_max: patch.budget_max ?? null,
      budget_type: patch.budget_type ?? null,
      country: patch.country || detail.country || ''
    })
  });
  if (!res.ok) { console.warn('[mybuilding BG] Re-enrich plan HTTP', res.status); return; }
  const enrichData = await res.json();
  if (!enrichData) return;

  await fetch(`${sbUrl}/rest/v1/upwork_jobs?id=eq.${jobId}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      'apikey': sbKey, 'Authorization': `Bearer ${sbKey}`, 'Prefer': 'return=minimal'
    },
    body: JSON.stringify({
      analysis: enrichData,
      status: enrichData.verdict === 'SKIP' ? 'skipped' : 'enriched'
    })
  });
  console.log('[mybuilding BG] Plan IA régénéré pour job', jobId);
}

// ── Chat page sync ──
async function checkChatPage(tab) {
  const { url: sbUrl, key: sbKey } = await getSupabase();
  if (!sbUrl || !sbKey) return;

  let chat;
  try {
    chat = await chrome.tabs.sendMessage(tab.id, { type: 'GET_CHAT_MESSAGES' });
  } catch (e) {
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
      await new Promise(r => setTimeout(r, 800));
      chat = await chrome.tabs.sendMessage(tab.id, { type: 'GET_CHAT_MESSAGES' });
    } catch (e2) {
      console.warn('[mybuilding BG] Cannot extract chat:', e2.message);
      chrome.storage.local.set({ mb_last_chat_sync: { ok: false, reason: 'script_error' } });
      return;
    }
  }

  if (!chat?.messages?.length) {
    console.log('[mybuilding BG] Chat: no messages extracted — selectors may need updating');
    chrome.storage.local.set({ mb_last_chat_sync: { ok: false, reason: 'no_messages', clientName: chat?.clientName } });
    return;
  }

  // ── Find matching job in Supabase ──
  let jobId = null;

  // Generic Upwork labels that are NOT real job titles — skip title search for these
  const GENERIC_LABELS = ['direct contracts', 'messages', 'inbox', 'contracts', 'my jobs'];
  const titleIsGeneric = !chat.jobTitle || GENERIC_LABELS.some(l => chat.jobTitle.toLowerCase().includes(l));

  // 1. Try by job title (only if not a generic label)
  if (!titleIsGeneric) {
    try {
      const safe = chat.jobTitle.substring(0, 60).replace(/[%_']/g, '\\$&');
      const res = await fetch(
        `${sbUrl}/rest/v1/upwork_jobs?select=id&title=ilike.*${encodeURIComponent(safe)}*&limit=1`,
        { headers: { 'apikey': sbKey, 'Authorization': `Bearer ${sbKey}` } }
      );
      if (res.ok) { const rows = await res.json(); if (rows.length) jobId = rows[0].id; }
    } catch (e) {}
  }

  // 2. Try by client name — handle "Name1, Name2" (group chats) by trying each part
  if (!jobId && chat.clientName) {
    const nameParts = chat.clientName.split(',').map(n => n.trim()).filter(Boolean);
    for (const namePart of nameParts) {
      if (jobId) break;
      try {
        const safe = namePart.substring(0, 50).replace(/[%_']/g, '\\$&');
        const res = await fetch(
          `${sbUrl}/rest/v1/contacts?select=upwork_job_id&name=ilike.*${encodeURIComponent(safe)}*&limit=1`,
          { headers: { 'apikey': sbKey, 'Authorization': `Bearer ${sbKey}` } }
        );
        if (res.ok) { const rows = await res.json(); if (rows.length && rows[0].upwork_job_id) jobId = rows[0].upwork_job_id; }
      } catch (e) {}
    }
  }

  // 3. Try most recent interviewing/negotiation job as fallback
  if (!jobId) {
    try {
      const res = await fetch(
        `${sbUrl}/rest/v1/upwork_jobs?select=id&status=in.(interviewing,negotiation)&order=applied_at.desc&limit=1`,
        { headers: { 'apikey': sbKey, 'Authorization': `Bearer ${sbKey}` } }
      );
      if (res.ok) { const rows = await res.json(); if (rows.length) jobId = rows[0].id; }
    } catch (e) {}
  }

  // ── Fetch job URL (needed for contact link) ──
  let jobUrl = null;
  if (jobId) {
    try {
      const res = await fetch(
        `${sbUrl}/rest/v1/upwork_jobs?select=url&id=eq.${jobId}`,
        { headers: { 'apikey': sbKey, 'Authorization': `Bearer ${sbKey}` } }
      );
      if (res.ok) { const rows = await res.json(); if (rows.length) jobUrl = rows[0].url; }
    } catch (e) {}
  }

  // ── Auto-create contact if not found ──
  if (chat.clientName) {
    // Check if contact already exists for this job or name
    let contactExists = false;
    try {
      const nameParts = chat.clientName.split(',').map(n => n.trim()).filter(Boolean);
      const firstName = nameParts[0] || chat.clientName;
      const safe = firstName.substring(0, 50).replace(/[%_']/g, '\\$&');
      const q = jobId
        ? `upwork_job_id=eq.${jobId}`
        : `name=ilike.*${encodeURIComponent(safe)}*`;
      const res = await fetch(
        `${sbUrl}/rest/v1/contacts?select=id&${q}&limit=1`,
        { headers: { 'apikey': sbKey, 'Authorization': `Bearer ${sbKey}` } }
      );
      if (res.ok) { const rows = await res.json(); contactExists = rows.length > 0; }
    } catch (e) {}

    if (!contactExists) {
      const contactPayload = {
        name: chat.clientName.split(',')[0].trim(), // take first name if multiple
        source: 'upwork',
        stage: 'lead',
      };
      if (jobId) contactPayload.upwork_job_id = jobId;
      if (jobUrl) contactPayload.upwork_url = jobUrl;
      try {
        const res = await fetch(`${sbUrl}/rest/v1/contacts`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'apikey': sbKey, 'Authorization': `Bearer ${sbKey}`,
            'Prefer': 'return=minimal'
          },
          body: JSON.stringify(contactPayload)
        });
        if (res.ok || res.status === 201) {
          console.log('[mybuilding BG] Contact créé auto:', contactPayload.name);
        }
      } catch (e) {
        console.warn('[mybuilding BG] Contact auto-create failed:', e.message);
      }
    }
  }

  // ── If still no job, use fallback ──
  if (!jobId) {
    console.warn('[mybuilding BG] Chat sync: no job matched, messages not saved');
    chrome.storage.local.set({ mb_last_chat_sync: { ok: false, reason: 'no_job_match', clientName: chat.clientName } });
    return;
  }

  // ── Merge messages ──
  let existingAnalysis = {};
  try {
    const res = await fetch(
      `${sbUrl}/rest/v1/upwork_jobs?select=analysis&id=eq.${jobId}`,
      { headers: { 'apikey': sbKey, 'Authorization': `Bearer ${sbKey}` } }
    );
    if (res.ok) { const rows = await res.json(); if (rows.length) existingAnalysis = rows[0].analysis || {}; }
  } catch (e) {}

  const existing = existingAnalysis.messages || [];
  const existingKeys = new Set(existing.map(m => (m.text || '').substring(0, 50) + m.sender));
  const newMsgs = chat.messages.filter(m => !existingKeys.has((m.text || '').substring(0, 50) + m.sender));
  const merged = [...existing, ...newMsgs].sort((a, b) => new Date(a.ts) - new Date(b.ts));

  const updatedAnalysis = { ...existingAnalysis, messages: merged };

  // ── PATCH ──
  try {
    const patchRes = await fetch(`${sbUrl}/rest/v1/upwork_jobs?id=eq.${jobId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'apikey': sbKey, 'Authorization': `Bearer ${sbKey}`, 'Prefer': 'return=minimal'
      },
      body: JSON.stringify({ analysis: updatedAnalysis })
    });
    if (patchRes.ok) {
      console.log(`[mybuilding BG] Chat synced — ${newMsgs.length} new msgs, total ${merged.length}`);
      chrome.storage.local.set({
        mb_last_chat_sync: { ok: true, newCount: newMsgs.length, totalCount: merged.length, clientName: chat.clientName },
        mb_last_check: new Date().toISOString(),
        mb_last_count: 0
      });
      chrome.notifications.create({
        type: 'basic', iconUrl: 'icon48.png',
        title: `mybuilding — Chat synchronisé`,
        message: `${newMsgs.length} nouveau${newMsgs.length > 1 ? 'x' : ''} message${newMsgs.length > 1 ? 's' : ''} — ${chat.clientName || 'client inconnu'}`
      });
    }
  } catch (e) {
    console.warn('[mybuilding BG] Chat PATCH failed:', e.message);
  }
}

// ── Detail page enrichment ──
async function checkDetailPage(tab) {
  console.log('[mybuilding BG] Detail mode — enriching job...');
  const { url: sbUrl, key: sbKey } = await getSupabase();
  if (!sbUrl || !sbKey) { console.warn('[mybuilding BG] Supabase non configuré'); return; }

  let detail;
  try {
    detail = await chrome.tabs.sendMessage(tab.id, { type: 'GET_JOB_DETAIL' });
  } catch (e) {
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['content.js'] });
      await new Promise(r => setTimeout(r, 800));
      detail = await chrome.tabs.sendMessage(tab.id, { type: 'GET_JOB_DETAIL' });
    } catch (e2) {
      console.warn('[mybuilding BG] Cannot contact content script:', e2.message);
      return;
    }
  }

  if (!detail?.id) {
    console.warn('[mybuilding BG] Detail page: no job ID extracted — panel not detected');
    return;
  }
  if (!detail.description) {
    console.warn('[mybuilding BG] Detail page: no description — will patch skills/title only');
  }

  // Check if job exists — try canonical URL, side-panel URL, then LIKE on job ID (handles slug URLs)
  const canonicalUrl = `https://www.upwork.com/jobs/~${detail.id}`;
  const sideUrl = `https://www.upwork.com/nx/search/jobs/details/~${detail.id}`;
  let existing = [];
  const lookups = [
    `url=eq.${encodeURIComponent(canonicalUrl)}`,
    `url=eq.${encodeURIComponent(sideUrl)}`,
    `url=like.*~${detail.id}*`
  ];
  for (const q of lookups) {
    try {
      const res = await fetch(
        `${sbUrl}/rest/v1/upwork_jobs?select=id,url&${q}`,
        { headers: { 'apikey': sbKey, 'Authorization': `Bearer ${sbKey}` } }
      );
      if (res.ok) {
        const rows = await res.json();
        if (rows.length > 0) { existing = rows; break; }
      }
    } catch (e) {
      console.warn('[mybuilding BG] Detail existence check failed:', e.message);
    }
  }
  console.log(`[mybuilding BG] Detail lookup: found=${existing.length}, id=${detail.id}`);

  if (existing.length > 0) {
    // PATCH using the URL actually stored in Supabase (not the normalized one)
    const storedUrl = existing[0].url;
    const patch = { url: canonicalUrl, source: 'extension' };

    // description_full — uniquement si substantielle (évite d'écraser avec une string vide)
    if (detail.description && detail.description.length > 50) {
      patch.description_full = detail.description;
    }

    // title — ne pas écraser avec des titres génériques de pages (ex: "Search Freelance Jobs on Upwork")
    if (detail.title) {
      const GENERIC_TITLES = [
        'search freelance jobs', 'find freelance jobs', 'best matches',
        'find work on upwork', 'jobs on upwork', 'upwork - hire freelancers'
      ];
      const titleLower = detail.title.toLowerCase().trim();
      const isGeneric = titleLower === 'upwork' ||
        GENERIC_TITLES.some(g => titleLower.includes(g));
      if (!isGeneric) patch.title = detail.title;
    }

    if (detail.skills?.length) patch.skills = detail.skills;
    if (detail.country) patch.country = detail.country;
    if (detail.budget) {
      const bp = parseBudget(detail.budget);
      if (bp.min != null) patch.budget_min = bp.min;
      if (bp.max != null) patch.budget_max = bp.max;
      if (bp.type) patch.budget_type = bp.type;
    }

    // Re-score avec la description complète (score initial = description tronquée de la liste)
    if (detail.description && detail.description.length > 200) {
      const scores = scoreJob({
        title: patch.title || detail.title || '',
        description: detail.description,
        country: patch.country || detail.country || '',
        scraped_at: new Date().toISOString()
      });
      Object.assign(patch, scores);
    }
    try {
      const patchRes = await fetch(`${sbUrl}/rest/v1/upwork_jobs?url=eq.${encodeURIComponent(storedUrl)}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json', 'apikey': sbKey, 'Authorization': `Bearer ${sbKey}`, 'Prefer': 'return=minimal' },
        body: JSON.stringify(patch)
      });
      if (patchRes.ok) {
        console.log('[mybuilding BG] Detail PATCHED OK — status:', patchRes.status, 'url:', storedUrl.slice(-40));
        // Re-générer le plan IA avec la description complète (async, non-bloquant)
        if (detail.description && detail.description.length > 100) {
          _reEnrichPlan(existing[0].id, patch, detail).catch(e =>
            console.warn('[mybuilding BG] Re-enrich plan error (non-critical):', e.message)
          );
        }
      } else {
        const errText = await patchRes.text();
        console.warn('[mybuilding BG] PATCH FAILED:', patchRes.status, errText);
      }
    } catch (e) {
      console.warn('[mybuilding BG] Detail PATCH failed:', e.message);
    }
    chrome.storage.local.set({ mb_last_check: new Date().toISOString(), mb_last_detail_mode: 'patched', mb_last_count: 0, mb_last_snipers: 0, mb_last_golds: 0 });
  } else {
    // INSERT new job with full description
    // Guard: don't insert if title is a generic page title (extraction failed)
    const GENERIC_TITLES = ['search freelance jobs', 'find freelance jobs', 'best matches', 'find work on upwork'];
    if (!detail.title || GENERIC_TITLES.some(g => detail.title.toLowerCase().includes(g))) {
      console.warn('[mybuilding BG] Detail INSERT aborted — generic title:', detail.title);
      return;
    }
    const budgetParsed = parseBudget(detail.budget);
    const base = {
      title: detail.title,
      description: detail.description || '',
      description_full: detail.description && detail.description.length > 50 ? detail.description : null,
      url: detail.url,
      country: detail.country,
      scraped_at: new Date().toISOString(),
      budget_min: budgetParsed.min,
      budget_max: budgetParsed.max,
      budget_type: budgetParsed.type,
      skills: detail.skills || [],
      source: 'extension',
      status: 'new'
    };
    const scores = scoreJob(base);
    const row = { ...base, ...scores };
    const result = await supabaseInsert('upwork_jobs', [row]);
    if (!result.error) {
      await addSeenIds([detail.id]);
      console.log('[mybuilding BG] Detail INSERTED:', detail.title?.slice(0, 50));
      chrome.notifications.create({
        type: 'basic', iconUrl: 'icon48.png',
        title: `mybuilding — Nouveau job ajouté`,
        message: `${detail.title?.slice(0, 60)}\nScore : ${row.worth_score}/10`
      });
    }
    chrome.storage.local.set({
      mb_last_check: new Date().toISOString(),
      mb_last_count: result.error ? 0 : 1,
      mb_last_snipers: row.sniper_mode ? 1 : 0,
      mb_last_golds: (row.worth_score >= 8 && !row.sniper_mode) ? 1 : 0,
      mb_last_detail_mode: result.error ? 'error' : 'inserted'
    });
  }
}

// ── Message handlers ──
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'CHECK_NOW') {
    const handleTab = async (tab) => {
      if (!tab) { sendResponse({ ok: false }); return; }
      const url = tab.url || '';
      const isChat = url.includes('/messages/rooms/') || url.includes('/ab/messages/') || url.includes('/nx/messages/');
      const isDetailByUrl = /\/jobs\/~[a-zA-Z0-9]+/.test(url) || /\/nx\/search\/jobs\/details\/~[a-zA-Z0-9]+/.test(url);
      if (isChat) await checkChatPage(tab);
      else if (isDetailByUrl) await checkDetailPage(tab);
      else {
        // URL ne matche pas — side panel peut être ouvert sans changement d'URL (ex: Best Matches)
        // Probe le content script : s'il trouve un job panel dans le DOM, on enrich ce job
        let probe = null;
        try { probe = await chrome.tabs.sendMessage(tab.id, { type: 'GET_JOB_DETAIL' }); } catch (e) {}
        if (probe?.id) await checkDetailPage(tab);
        else await checkForNewJobs();
      }
      sendResponse({ ok: true });
    };
    if (msg.tabId) {
      chrome.tabs.get(msg.tabId, handleTab);
    } else {
      chrome.tabs.query({ active: true, lastFocusedWindow: true }, (tabs) => handleTab(tabs[0]));
    }
    return true;
  }
  if (msg.type === 'UPDATE_SETTINGS') {
    chrome.storage.local.set({ mb_settings: msg.settings }, () => {
      sendResponse({ ok: true });
    });
    return true;
  }
  if (msg.type === 'GET_STATUS') {
    chrome.storage.local.get(['mb_last_check', 'mb_last_count', 'mb_last_snipers', 'mb_last_golds', 'mb_settings'], (data) => {
      sendResponse(data);
    });
    return true;
  }
  if (msg.type === 'JOB_DETAIL_UPDATE') {
    const { detail } = msg;
    if (!detail?.url || !detail?.description) return false;
    getSupabase().then(({ url: sbUrl, key: sbKey }) => {
      if (!sbUrl || !sbKey) return;
      // PATCH by URL — update description + skills if richer than what we have
      const patch = { description_full: detail.description };
      if (detail.skills?.length) patch.skills = detail.skills;
      if (detail.country) patch.country = detail.country;
      fetch(`${sbUrl}/rest/v1/upwork_jobs?url=eq.${encodeURIComponent(detail.url)}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'apikey': sbKey,
          'Authorization': `Bearer ${sbKey}`,
          'Prefer': 'return=minimal'
        },
        body: JSON.stringify(patch)
      }).then(r => {
        if (r.ok) console.log('[mybuilding BG] Detail updated:', detail.url.slice(-30));
        else r.text().then(t => console.warn('[mybuilding BG] Detail PATCH failed:', t));
      }).catch(e => console.warn('[mybuilding BG] Detail PATCH error:', e.message));
    });
    return false;
  }
  if (msg.type === 'UNREAD_MESSAGES') {
    chrome.storage.local.set({ mb_unread: msg.count });
    if (msg.count > 0) {
      chrome.action.setBadgeText({ text: '💬' });
      chrome.action.setBadgeBackgroundColor({ color: '#f59e0b' });
    }
    return false;
  }
  if (msg.type === 'SET_COVER') {
    chrome.storage.local.set({ mb_last_cover: msg.cover });
    return false;
  }
  return false;
});
