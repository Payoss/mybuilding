// mybuilding.dev — Content Script (TOS-Safe Mode)
// Human-initiated only: reads visible DOM when user clicks "Scan This Page"
// Cover letter auto-fill: assists human writing on proposal pages
// Badge messages: reads unread count for notification badge
// NO auto-refresh, NO polling for new jobs, NO DOM manipulation on search pages

(function() {
  console.log('[mybuilding] Content script actif sur', window.location.href);

  // ── Cover Letter Auto-Fill ──
  const COVER_SELECTORS = [
    'textarea[data-cy="cover-letter-text"]',
    'textarea[name="cover_letter"]',
    'textarea[name="coverLetter"]',
    '[data-test="cover-letter"] textarea',
    '[data-cy="cover-letter"] textarea',
    'textarea[placeholder*="cover" i]',
    'textarea[id*="cover" i]'
  ].join(',');

  let _injected = false;
  let _proposalObserver = null;

  function _findCoverTextarea() {
    const ta = document.querySelector(COVER_SELECTORS);
    if (ta) return ta;
    const all = Array.from(document.querySelectorAll('textarea'));
    if (!all.length) return null;
    return all.reduce((best, t) => {
      const rows = parseInt(t.getAttribute('rows') || '0');
      const bestRows = parseInt(best.getAttribute('rows') || '0');
      return rows > bestRows ? t : best;
    });
  }

  function _tryFillCover(cover) {
    const ta = _findCoverTextarea();
    if (!ta) return false;
    if (ta.value && ta.value.trim().length > 20) return true;
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
    nativeSetter.call(ta, cover);
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    ta.dispatchEvent(new Event('change', { bubbles: true }));
    ta.focus();
    setTimeout(() => ta.dispatchEvent(new Event('blur', { bubbles: true })), 100);
    _showToast('mybuilding — Cover letter injectée. Vérifie et Submit.');
    return true;
  }

  function _startProposalWatcher() {
    if (_proposalObserver) { _proposalObserver.disconnect(); _proposalObserver = null; }
    _injected = false;
    chrome.storage.local.get('mb_last_cover', ({ mb_last_cover: cover }) => {
      if (!cover) return;
      if (_tryFillCover(cover)) { _injected = true; return; }
      _proposalObserver = new MutationObserver(() => {
        if (_injected) { _proposalObserver.disconnect(); return; }
        if (_tryFillCover(cover)) {
          _injected = true;
          _proposalObserver.disconnect();
        }
      });
      _proposalObserver.observe(document.body, { childList: true, subtree: true });
      setTimeout(() => { if (_proposalObserver) _proposalObserver.disconnect(); }, 120000);
    });
  }

  function _isProposalPage() {
    const url = window.location.href;
    return url.includes('/proposals/') || url.includes('/freelance-jobs/apply/') || url.includes('/job/apply/');
  }

  function _showToast(msg) {
    document.getElementById('mb-toast')?.remove();
    const div = document.createElement('div');
    div.id = 'mb-toast';
    div.textContent = msg;
    div.style.cssText = 'position:fixed;top:16px;right:16px;z-index:2147483647;background:#0d9488;color:#fff;padding:14px 22px;border-radius:10px;font-size:13px;font-weight:700;font-family:Inter,sans-serif;box-shadow:0 4px 20px rgba(13,148,136,.5);transition:opacity .3s';
    document.body.appendChild(div);
    setTimeout(() => { div.style.opacity = '0'; setTimeout(() => div.remove(), 300); }, 5000);
  }

  // ── DOM Job Extraction ──
  function _extractJobsFromDOM() {
    const jobs = [];
    const cards = document.querySelectorAll(
      '[data-test="job-tile-list"] section, ' +
      '[data-test="JobTile"], ' +
      'article[data-ev-label="search_results_impression"], ' +
      '[class*="job-tile"], ' +
      'section.up-card-section'
    );

    cards.forEach(card => {
      try {
        const titleEl = card.querySelector(
          '[data-test="job-tile-title-link"], h2 a, h3 a, ' +
          'a[data-test="UpLink"], [class*="job-title"] a, a[href*="/jobs/"]'
        );
        const title = titleEl?.textContent?.trim();
        if (!title) return;

        let url = titleEl?.href || '';
        if (url && !url.startsWith('http')) url = 'https://www.upwork.com' + url;
        url = url.split('?')[0];
        // Normalize to canonical /jobs/~XXX regardless of page context
        const idMatch = url.match(/~([a-zA-Z0-9]+)/) || url.match(/jobs\/([a-zA-Z0-9]+)/);
        if (idMatch) url = `https://www.upwork.com/jobs/~${idMatch[1]}`;
        const id = idMatch ? idMatch[1] : btoa(title).slice(0, 16);

        // Description — ordered from most specific to least, never fall back to bare `p`
        const descEl =
          card.querySelector('[data-test="job-description-text"]') ||
          card.querySelector('[data-test="UpCLineClamp"]') ||
          card.querySelector('[data-test="job-description"]') ||
          card.querySelector('.air3-line-clamp') ||
          card.querySelector('[class*="JobDescription"]') ||
          card.querySelector('[class*="job-description"]');
        const description = descEl?.textContent?.trim()?.slice(0, 2000) || '';

        const budgetEl = card.querySelector(
          '[data-test="budget"], [data-test="is-fixed-price"], ' +
          '[class*="budget"], strong[data-test="budget"]'
        );
        const budget = budgetEl?.textContent?.trim() || '';

        const locEl = card.querySelector(
          '[data-test="client-country"], [data-test="location"], ' +
          '[class*="client-location"], [class*="location"]'
        );
        const country = locEl?.textContent?.trim() || '';

        // Skills — filter out client badges (Verified, Payment verified, etc.)
        const SKILL_NOISE = /^(verified|payment verified|payment unverified|unverified|rising talent|top rated|expert-vetted|enterprise|location|united states|france|\$\d)/i;
        const skillEls = card.querySelectorAll(
          '[data-test="token"], [class*="skill-tag"], a[data-test="attr-item"]'
        );
        const skills = Array.from(skillEls)
          .map(s => s.textContent.trim())
          .filter(s => s && !SKILL_NOISE.test(s));

        jobs.push({ id, title, url, description, budget, country, skills, scraped_at: new Date().toISOString() });
      } catch (e) {}
    });
    return jobs;
  }

  // ── Job Detail Page Extraction ──
  function _isJobDetailPage() {
    return /\/jobs\/~[a-zA-Z0-9]+/.test(window.location.href) ||
           /\/nx\/search\/jobs\/details\/~[a-zA-Z0-9]+/.test(window.location.href);
  }

  function _extractJobDetail() {
    // Title — h1 on full page, specific selectors on side panel
    // Bare h1/h2 avoided — too risky on side panel (match search page headings)
    const titleEl =
      document.querySelector('h1[data-test="job-title"]') ||
      document.querySelector('[data-test="job-title"]') ||
      document.querySelector('h2[class*="job-title"]') ||
      document.querySelector('h2[class*="JobTitle"]') ||
      document.querySelector('h2.m-0') ||
      document.querySelector('h1.m-0') ||
      document.querySelector('[class*="JobTitle"]') ||
      document.querySelector('[class*="job-title"]');
    let rawTitle = titleEl?.textContent?.trim() || '';
    // Fallback: document.title — Upwork sets it to "Job Title | Upwork" on detail pages
    if (!rawTitle || rawTitle.length >= 200) {
      const docTitle = document.title || '';
      const parts = docTitle.split('|');
      const candidate = parts[0].trim();
      if (candidate && candidate.toLowerCase() !== 'upwork' && candidate.length < 200) {
        rawTitle = candidate;
      }
    }
    const title = rawTitle;

    // Full description — p.text-body-sm works on both full page and side panel
    const descEl =
      document.querySelector('p.text-body-sm') ||
      document.querySelector('p[data-test="Description"]') ||
      document.querySelector('p.text-body-sm.multiline-text') ||
      document.querySelector('[data-test="Description"]') ||
      document.querySelector('[data-test="description"]') ||
      document.querySelector('.air3-rich-text') ||
      document.querySelector('[data-cy="job-description"]');
    const description = descEl?.innerText?.trim() || descEl?.textContent?.trim() || '';

    // Skills — filter out client badges
    const SKILL_NOISE_DETAIL = /^(verified|payment verified|payment unverified|unverified|rising talent|top rated|expert-vetted|enterprise|location|united states|france|\$\d)/i;
    const skillEls = document.querySelectorAll(
      '[data-test="attr-item"], [data-test="token"], ' +
      '[class*="skill-tag"], a[href*="/o/jobs/browse/"] .air3-token'
    );
    const skills = Array.from(skillEls)
      .map(s => s.textContent.trim())
      .filter(s => s && !SKILL_NOISE_DETAIL.test(s));

    // Budget
    const budgetEl =
      document.querySelector('[data-test="budget"]') ||
      document.querySelector('[data-test="is-fixed-price"]') ||
      document.querySelector('[data-test="hourly-rate"]') ||
      document.querySelector('[class*="BudgetAmount"]');
    const budget = budgetEl?.textContent?.trim() || '';

    // Country
    const countryEl =
      document.querySelector('[data-test="client-location"] strong') ||
      document.querySelector('[data-qa="client-location"]') ||
      document.querySelector('[class*="ClientLocation"]');
    const country = countryEl?.textContent?.trim() || '';

    // Job ID from URL — normalize to canonical /jobs/~XXX regardless of side panel URL
    const idMatch = window.location.href.match(/~([a-zA-Z0-9]+)/);
    const id = idMatch ? idMatch[1] : null;
    const url = id ? `https://www.upwork.com/jobs/~${id}` : window.location.href.split('?')[0];

    return { id, title, url, description, skills, budget, country };
  }

  function _sendDetailUpdate() {
    if (!_isJobDetailPage()) return;
    const detail = _extractJobDetail();
    if (!detail.id || !detail.description) return;
    chrome.runtime.sendMessage({ type: 'JOB_DETAIL_UPDATE', detail }).catch(() => {});
  }

  // ── Initialisation ──

  // Proposal page
  if (_isProposalPage()) setTimeout(_startProposalWatcher, 500);

  // Badge messages
  let _lastMsgCount = 0;
  function _readMsgBadge() {
    const el =
      document.querySelector('[data-test="unread-messages-count"]') ||
      document.querySelector('[aria-label*="message" i] [class*="badge" i]') ||
      document.querySelector('a[href*="/messages"] [class*="badge"]') ||
      document.querySelector('a[href*="/messages"] sup');
    const count = el ? parseInt(el.textContent.trim()) || 0 : 0;
    if (count !== _lastMsgCount) {
      chrome.runtime.sendMessage({ type: 'UNREAD_MESSAGES', count }).catch(() => {});
    }
    _lastMsgCount = count;
  }
  new MutationObserver(_readMsgBadge).observe(document.body, { childList: true, subtree: true, characterData: true });
  setTimeout(_readMsgBadge, 3000);

  // SPA navigation (unified — proposal + detail + badge)
  let _pollHref = location.href;
  setInterval(() => {
    if (location.href !== _pollHref) {
      _pollHref = location.href;
      if (_isProposalPage()) _startProposalWatcher();
    }
  }, 1000);

  window.addEventListener('popstate', () => {
    if (_isProposalPage()) setTimeout(_startProposalWatcher, 600);
  });

  // ── Message Handler ──
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.type === 'GET_JOBS_FROM_DOM') {
      const url = window.location.href;
      if (!url.includes('/search/jobs') && !url.includes('/nx/find-work') && !url.includes('/nx/search')) {
        sendResponse({ jobs: [] });
        return true;
      }
      sendResponse({ jobs: _extractJobsFromDOM() });
      return true;
    }
    if (msg.type === 'GET_JOB_DETAIL') {
      sendResponse(_isJobDetailPage() ? _extractJobDetail() : null);
      return true;
    }
    return true;
  });
})();
