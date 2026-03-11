// ============================================================
// mybuilding.dev — Config Supabase
// ============================================================
// Ces valeurs seront remplacées par les vraies clés Supabase
// NE PAS committer le vrai .env — utiliser .env.example

const SUPABASE_URL  = 'REPLACE_WITH_SUPABASE_URL';
const SUPABASE_KEY  = 'REPLACE_WITH_SUPABASE_ANON_KEY';

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
