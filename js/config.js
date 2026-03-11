// ============================================================
// mybuilding.dev — Config Supabase
// ============================================================

const SUPABASE_URL  = 'https://hjcdshafjkzzjaztqhte.supabase.co';
const SUPABASE_KEY  = 'sb_publishable_EJChtqZR5pRHHGmU8oF9fg_WH9Rqf19';

// Init client Supabase (CDN chargé dans chaque page HTML)
const sb = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

// Profil Paul Annes — utilisé par l'Upwork analyzer
const PROFILE = {
  name: 'Paul Annes',
  skills: ['React', 'Next.js', 'Claude API', 'n8n', 'automation', 'Full-stack', 'Supabase', 'Python'],
  keywords: ['AI integration', 'Claude API', 'n8n automation', 'automation'],
  redLines: ['< $500 budget', 'scraping illégal', 'crypto/NFT'],
  safeWords: [
    'proven track record',
    'I work with my own AI agent system',
    'I can deliver a working prototype in 48h'
  ],
  minBudget: 1000,
  currency: 'EUR'
};

export { sb, PROFILE };
