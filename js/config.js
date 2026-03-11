// ============================================================
// mybuilding.dev — Config Supabase (globals)
// ============================================================

var SUPABASE_URL = 'https://hjcdshafjkzzjaztqhte.supabase.co';
var SUPABASE_KEY = 'sb_publishable_EJChtqZR5pRHHGmU8oF9fg_WH9Rqf19';

var sb = supabase.createClient(SUPABASE_URL, SUPABASE_KEY);

var PROFILE = {
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
