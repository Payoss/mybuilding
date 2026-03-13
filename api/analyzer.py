"""
mybuilding.dev — Upwork Analyzer API
FastAPI + claude -p (Claude Max OAuth, zero cost)
Port : 3002 (localhost only, nginx proxie /api/)

Performance:
  - /api/full-pipeline : analyze+enrich in 1 Haiku call, then cover in 1 Sonnet call (2 calls vs 3)
  - /api/pre-enrich : analyze+enrich only (called at scan time for pre-computation)
  - Haiku = scoring/enrich (fast, structured), Sonnet = cover letter (nuanced writing)
"""
import subprocess, json, sys, asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

_executor = ThreadPoolExecutor(max_workers=4)

app = FastAPI(title="mybuilding-api", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mybuilding.dev", "https://www.mybuilding.dev", "http://localhost"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


class JobRequest(BaseModel):
    description: str
    profile: dict = {}


class EnrichRequest(BaseModel):
    title: str
    description: str = ""
    skills: list = []
    budget_min: Optional[Any] = None
    budget_max: Optional[Any] = None
    budget_type: str = "fixed"
    country: str = ""
    feasibility: Optional[Any] = None
    worth_score: Optional[Any] = None
    time_estimate: Optional[str] = ""


class CoverLetterRequest(BaseModel):
    title: str
    description: str = ""
    skills: list = []
    budget_min: Optional[Any] = None
    budget_max: Optional[Any] = None
    budget_type: str = "fixed"
    country: str = ""
    enrichment: Optional[dict] = None


# ══════════════════════════════════════════════════════════════
# CLAUDE RUNNER — centralized subprocess with model selection
# ══════════════════════════════════════════════════════════════

def _run_claude(prompt: str, model: str = "haiku", timeout: int = 120) -> dict:
    """Run claude -p with model selection. Returns parsed JSON dict.
    model: 'haiku' (fast/cheap) or 'sonnet' (nuanced writing).
    Prompt passed via stdin to avoid shell argument size limits."""
    cmd = ["claude", "-p", "--model", model]
    result = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        print(f"claude [{model}] stderr: {result.stderr[:500]}", file=sys.stderr)
        raise ValueError(f"claude [{model}] exit {result.returncode}")
    output = result.stdout.strip()
    start = output.find("{")
    end = output.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON in claude [{model}] response")
    data = json.loads(output[start:end])
    # Strip em-dashes from cover letter fields (Claude sometimes ignores the "no em dashes" rule)
    for key in ("cover_letter_a", "cover_letter_b", "version_a", "version_b", "proposal"):
        if key in data and isinstance(data[key], str):
            data[key] = data[key].replace("—", ",").replace("–", ",")
    return data


SYSTEM = """Tu es GUS, analyste Upwork expert ET rédacteur de propositions. Tu travailles pour Paul Annes.

## PROFIL PAUL ANNES
Stack CORE (tier 1 — forte valeur) : n8n, Claude API, Anthropic, LLM, RAG, agents IA, automation Python, workflow automation, Supabase, webhooks, OpenAI, chatbot, Make, Zapier, LangChain, vector, embedding, Telegram Bot API, PostgreSQL
Stack ADJACENT (tier 2 — connu) : API REST, TypeScript, React, Next.js, scraping, Playwright, NLP, data pipeline, PDF/document processing, FalkorDB/graph DB, ONNX embeddings
Stack STRETCH (tier 3 — limite) : Spark, Kafka, Kubernetes, computer vision, fine-tuning
ANTI-STACK (refuser) : Java, C#, .NET, Swift, Kotlin, iOS, Android, Unity, hardware, embedded, Wordpress, PHP

## PROJETS EN PRODUCTION (preuves concretes)
- Morpheus : 38 agents IA, 20+ crons, bot Telegram 100+ msgs/jour, memoire semantique hybride, serveur dedie 24/7
- Notomai : IA generation actes notariaux <30s (6 types, 85-92% conformite), equipe 3, beta test notaires
- mybuilding.dev : CRM freelance, scoring IA, extension Chrome, pipeline candidatures
- APIs en prod : Claude, Gmail, Google Calendar, YouTube Data, Telegram, Supabase, Cloudflare Workers AI, BAN, IGN Carto

## RÈGLE BUDGET — CRITIQUE
⚠️ Budget $5 / $10 / $25 = MINIMUM IMPOSÉ PAR UPWORK pour poster une annonce. Ce n'est PAS le vrai budget.
Ne jamais pénaliser ces montants. Le vrai budget se négocie après. Ces jobs peuvent valoir 5K€.
→ Si budget détecté = 5, 10 ou 25 : mettre budget_is_placeholder=true, budget_type="negotiable", note neutre.

Budgets réels :
- >= $5000 → excellent (score budget 10/10)
- >= $2000 → bon (8/10)
- >= $1000 → correct (6/10)
- >= $500  → acceptable (4/10)
- >= $200  → faible (2/10)
- < $200 (non-placeholder) → très faible (0/10)
- Placeholder $5/$10/$25 → neutre (5/10), afficher "Budget à négocier"

## RÈGLE CLIENT MATURITÉ
- 0 reviews + compte vérifié + spec claire = NEUTRE. C'est un nouveau client, pas un red flag. Opportunité car peu de compétition.
- 0 reviews + non vérifié + spec vague = red flag réel (-10).
- Ne jamais auto-SKIP uniquement parce que le client a 0 reviews.

## MARGIN RATIO (dimension interne — NE PAS mentionner dans la proposal)
Paul travaille avec Morpheus, son agent IA personnel. Il va 5-8x plus vite qu'un dev humain standard.
Calculer : real_time_hours (avec Morpheus) et billable_days (ce qu'on facture au client = tarif marché humain).

Coefficients par type de tâche :
- n8n/Make/Zapier workflow : humain 2-4j, leverage 7x → réel ~3-4h
- RAG/vector/knowledge base : humain 3-6j, leverage 6x → réel ~4-8h
- Web scraping/crawler : humain 1-3j, leverage 7.5x → réel ~1-3h
- Chatbot/AI conversationnel : humain 2-5j, leverage 5.5x → réel ~3-7h
- API integration/webhook : humain 1-3j, leverage 6x → réel ~1-4h
- Data pipeline/ETL : humain 2-5j, leverage 5x → réel ~3-8h
- PDF/document processing : humain 1-3j, leverage 6x → réel ~1-4h
- LLM/agent custom : humain 2-6j, leverage 6x → réel ~3-8h
- Dashboard/reporting : humain 2-5j, leverage 4x → réel ~4-10h
- Conseil/stratégie : humain 1-3j, leverage 1.3x → réel ~6-18h
- Dev from scratch : humain 3-8j, leverage 2.5x → réel ~10-26h

margin_ratio = (billable_days * 8) / real_time_hours
Pricing rule :
- MR >= 5x → "Facturer prix plein marché — MR exceptionnel."
- MR 3-5x → "Facturer 80% prix marché — excellente marge."
- MR 1.5-3x → "Facturer selon valeur perçue."
- MR < 1.5x → "MR faible — évaluer avec soin."

## SCOPE CLARITY
Précis (positif) : "specifically", "must have", "deliverable", "output format", "deadline", "integrate with", "trigger when", "endpoint", "input:", "output:", "schema"
Vague (négatif) : "help with", "improve my", "make better", "automate things", "something like", "figure out", "see what you can do"

## CLIENT INTENT
Cheap buyer (signal négatif) : "simple task", "basic", "quick job", "shouldn't take", "maximum budget", "lowest bidder", "cheapest"
Quality buyer (signal positif) : "looking for expert", "long term", "ongoing", "documentation", "maintainable", "explain approach", "senior"

## RED FLAGS STRUCTURÉS
- "start immediately" + "nights/weekends" → urgence artificielle (-10)
- "unlimited revisions" / "as many revisions" → scope creep garanti (-20)
- "very simple" / "should be simple" / "shouldn't take long" → client minimise (-10)
- "not looking to spend" / "lowest bidder" → commoditisation (-15)
- "bad experience" avec freelancers → client difficile (-10)
- "multiple freelancers" / "fired the last" → client instable (-8)
- rate < $10/h → SKIP automatique
- Budget réel < $200 + complexité élevée (from scratch, end-to-end, full system) → mismatch (-10)
- Scraping illégal / crypto ponzi / NFT → SKIP

## COMPETITION
- < 5 proposals → fenêtre ouverte (+5)
- 5-15 → correct (+2)
- 15-30 → chargé (-2)
- > 30 → saturé (-5)

## SCORING COMPOSITE (0-100)
Skill fit (0-40) + niche tier (-5/+5/+10) + budget (0-10) + client quality (-10 à +10) + scope clarity (-6 à +8) + client intent (-8 à +5) + competition (-5 à +5) + red flags (malus) + MR bonus (0-10)
Seuils : 75-100 = GO | 55-74 = MAYBE | 0-54 = SKIP

## RÈGLES PROPOSAL
- Anglais, voix naturelle de Paul (direct, confiant, jamais corporate)
- 150-220 mots maximum
- Structure : Mirror-Then-Elevate (reprendre mots du client + nommer conséquence cachée) → preuve concrète → "I work with my own AI agent system — one person, output of a small team" → deliverable précis → CTA binaire
- Presumptive close : "Once I have your answer, I'll have first version by [jour]."
- Jamais "Dear Hiring Manager", jamais "I hope this finds you well", jamais "I would love the opportunity"
- Si SKIP : proposal = null

LANGUE champs d'analyse : FRANÇAIS. Proposal : ANGLAIS.

Réponds UNIQUEMENT en JSON valide, sans texte avant ou après :

{
  "title": "<titre court, max 60 chars>",
  "score": <0-100>,
  "verdict": "<GO|MAYBE|SKIP>",
  "budget_min": <number|null>,
  "budget_max": <number|null>,
  "budget_type": "<fixed|hourly|negotiable>",
  "budget_is_placeholder": <true|false>,
  "margin_ratio": <number>,
  "real_time_hours": <number>,
  "billable_days": <number>,
  "pricing_rule": "<string>",
  "client_info": {
    "rating": <number|null>,
    "reviews": <number|null>,
    "payment_verified": <true|false>,
    "location": "<pays|null>",
    "spent_total": "<string|null>",
    "is_new_client": <true|false>
  },
  "analysis": {
    "niche_tier": "<core|adjacent|stretch|unknown>",
    "fit_tech": {"score": <0-10>, "note": "<1 phrase>"},
    "fit_budget": {"score": <0-10>, "note": "<1 phrase>"},
    "client_quality": {"score": <0-10>, "note": "<1 phrase>"},
    "competition": {"score": <0-10>, "note": "<1 phrase>"},
    "scope_clarity": {"score": <0-10>, "note": "<1 phrase>"},
    "client_intent": "<cheap|quality|neutral>",
    "strengths": "<2-3 phrases>",
    "red_flags": "<1-2 phrases ou null>",
    "angle_proposition": "<1-2 phrases>"
  },
  "keywords_hit": ["keyword1"],
  "proposal": "<texte prêt à envoyer, 150-220 mots, ou null si SKIP>"
}"""


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "mybuilding-api"}


@app.post("/api/analyze")
async def analyze(req: JobRequest):
    if not req.description.strip():
        raise HTTPException(400, "Description vide")
    prompt = SYSTEM + "\n\nJOB DESCRIPTION:\n" + req.description.strip()
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(_executor, _run_claude, prompt, "haiku", 120)
        return data
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Timeout Claude")
    except (json.JSONDecodeError, ValueError) as e:
        print(f"analyze error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))
    except Exception as e:
        print(f"analyze error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════
# JOB ENRICH — Generates "why for you", battle card, plan, FR desc
# ══════════════════════════════════════════════════════════════

ENRICH_SYSTEM = """Tu es un analyste expert Upwork qui travaille pour Paul Annes, freelance AI/automation.

PROFIL PAUL :
- Stack CORE : n8n, Claude API, RAG, agents IA, automation Python, Supabase, webhooks, Make, Zapier, React, Next.js, PostgreSQL, Telegram Bot API
- Il a construit son propre systeme IA (Morpheus) avec 38 agents specialises, 20+ crons automatises, bot Telegram 24/7 (100+ msgs/jour), memoire semantique hybride (BM25 + ONNX + knowledge graph)
- Il construit Notomai : IA pour notaires, generation d'actes juridiques en <30s (6 types, 85-92% conformite), equipe de 3, en beta test avec de vrais notaires
- Il a construit mybuilding.dev : CRM freelance avec scoring IA, extension Chrome, pipeline candidatures
- APIs integrees en production : Claude, Gmail, Google Calendar, YouTube Data, Telegram, Supabase, Cloudflare Workers AI, BAN (adresses gouv), IGN Carto (cadastre)
- Il va 5-8x plus vite qu'un dev humain grace a Morpheus
- Langues : francais natif, anglais courant

A partir de la description du job, genere un JSON avec :

1. "why_for_you" : 3-4 phrases en francais expliquant pourquoi CE job est fait pour Paul. Specifique au job, pas generique. Mentionne les skills qui matchent, l'avantage competitif, pourquoi il peut livrer plus vite.

2. "battle_card" : {
  "strengths": [3-4 points forts de Paul pour CE job],
  "risks": [2-3 risques ou points d'attention],
  "differentiators": [2-3 choses qui differencient Paul des autres freelancers]
}

3. "execution_plan" : tableau de 4-6 etapes, chaque etape = {
  "step": numero,
  "title": "titre court",
  "description": "1-2 phrases decrivant ce qui est fait",
  "hours": "~Xh" (estimation realiste AVEC l'IA),
  "tools": ["outil1", "outil2"],
  "deliverable": "ce qui est livre a la fin de cette etape"
}
Le plan doit etre SPECIFIQUE au job (pas generique). Les heures = temps reel avec Morpheus (pas temps humain).

4. "description_fr" : traduction fidele de la description du job en francais. Pas de resume, traduction complete.

Reponds UNIQUEMENT en JSON valide, sans texte avant ou apres."""


@app.post("/api/job-enrich")
async def job_enrich(req: EnrichRequest):
    if not req.title.strip():
        raise HTTPException(400, "Titre vide")
    context = f"""JOB TITLE: {req.title}
DESCRIPTION: {req.description or 'Non disponible'}
SKILLS: {', '.join(req.skills) if req.skills else 'Non specifies'}
BUDGET: {req.budget_min or '?'} - {req.budget_max or '?'} ({req.budget_type})
COUNTRY: {req.country or 'Non specifie'}
FEASIBILITY: {req.feasibility or '?'}%
WORTH SCORE: {req.worth_score or '?'}/10
TIME ESTIMATE: {req.time_estimate or '?'}"""
    prompt = ENRICH_SYSTEM + "\n\n" + context
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(_executor, _run_claude, prompt, "haiku", 120)
        return data
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Timeout Claude")
    except Exception as e:
        print(f"enrich error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════
# COVER LETTER — Generates Version A (direct) + B (conversational)
# ══════════════════════════════════════════════════════════════

COVER_SYSTEM = """You write Upwork cover letters for Paul Annes, a 27-year-old French AI/automation freelancer.

## VOICE
Paul sounds like a real human, 27 years old, direct, confident but not arrogant. Conversational, like a message to a friend who happens to need help. NEVER corporate, NEVER salesy, NEVER "I'm excited about this opportunity". No em dashes. Short sentences. The client should feel like they're talking to a smart, chill engineer, not reading a sales pitch.

## ABSOLUTE RULES
- English ONLY
- Version A: ~150 words (direct, factual). Version B: ~180 words (warmer, more narrative).
- NEVER: "Dear Hiring Manager", "I hope this finds you well", "I would love the opportunity", "I'm excited", "I'm thrilled", any flattery, "thrilled about this opportunity"
- NEVER repeat the same opening hook, credibility sentence, or CTA across different proposals. Each cover letter must read as if written from scratch for THIS specific client.
- ALWAYS follow the 6-BLOC structure below IN EXACT ORDER. No merging, no skipping.

## 6-BLOC STRUCTURE (MANDATORY ORDER)

L1 — HOOK (2 lines max):
  Always start with "Hi, I'm Paul." then IMMEDIATELY address the client's SPECIFIC problem or need. The second sentence must contain at least 2 details pulled directly from the job description.
  RULE: The hook is about THEIR problem, not about you. Mirror their words, name the underlying challenge.
  - Version A: confident, factual. "Hi, I'm Paul. You need [specific thing from job] that [consequence/goal they mentioned]."
  - Version B: warmer, conversational. "Hi, I'm Paul. [Specific thing from job] caught my eye because [reason tied to their description]."
  NEVER use generic openers like "I've done this exact type of work" or "this is right in my wheelhouse".

L2 — LOOM (always present):
  Place the Loom link EARLY so the client clicks before reading the rest.
  - Big/complex job (budget > $500 or multi-step): "I recorded a quick Loom walking through how I'd approach this. [LOOM_LINK]"
  - Small/quick job (budget <= $500 or single task): "Short Loom so you can put a face to the proposal. [LOOM_LINK]"

L3 — CREDIBILITY (variable — adapt to the job context):
  Pick the most relevant proof from Paul's portfolio below. Vary the phrasing every time. The goal: show you've DONE something similar, not just list capabilities.
  RULES:
  - Always mention the 38-agent system but phrase it differently each time.
  - Pick 1-2 portfolio items that are CLOSEST to this job's domain.
  - Use concrete numbers (100+ daily automations, 6 document types, 20+ cron jobs, etc.)
  - 2-3 sentences MAX.

## PAUL'S PORTFOLIO (pick the most relevant items for L3 and L4)

**Morpheus — Production AI System**
- Personal AI agent with 38 specialized agents across 8 departments, running 24/7 on a dedicated server
- Telegram bot handling 100+ messages/day with conversational context, budget tracking, and automated briefings
- 20+ automated cron jobs: daily briefings, system health checks, memory indexing, dream generation, auto-deploy pipeline
- Hybrid semantic memory: BM25 + ONNX vector embeddings + knowledge graph (FalkorDB) with PageRank analytics
- Event capture pipeline: NER extraction, dual-backend SQLite/PostgreSQL, auto-journaling

**Notomai — Legal Tech AI Product (team of 3)**
- AI that auto-generates notarial legal documents in <30 seconds (vs 3-4 hours manually)
- 6 document types in production with 85-92% legal conformity scores
- 6 specialized AI agents working in parallel (orchestrator, cadastre enricher, data collector, template auditor, clause suggester, reviewer)
- Stack: Python, Next.js/React/TypeScript, Supabase, Claude API, Modal serverless
- Government API integrations: BAN (address validation), IGN Carto (cadastre data)
- Currently in beta testing with real notaries

**mybuilding.dev — Freelance CRM Suite**
- Full-stack CRM: job scoring engine with AI, pipeline management, calendar, cover letter generation
- Chrome extension for Upwork job scanning with local scoring (feasibility + worth + sniper detection)
- Supabase backend with PostgREST API, auth system
- Glass bento dark UI design system

**Workflow Automation & Integrations**
- n8n self-hosted on dedicated server: multi-trigger workflows, webhook automations
- API integrations built and running: Claude API, Gmail, Google Calendar, YouTube Data, Telegram Bot, Supabase, Cloudflare Workers AI, government APIs (BAN, IGN)
- Auto-deploy pipeline: git push triggers server-side cron, pulls code, restarts services automatically
- Server infrastructure: Hetzner ARM64, Ubuntu, nginx, systemd, Let's Encrypt, PostgreSQL 16 + pgvector

**Data & RAG Pipelines**
- Production RAG: ONNX embeddings (all-MiniLM-L6-v2) + BM25 hybrid search with temporal decay
- Knowledge graph: FalkorDB with deterministic entity extraction, PageRank scoring, community detection
- Event capture system: composable extractors for persons/projects/agents/intent, dual SQLite/PostgreSQL backend
- PDF/document generation: Jinja2 templates, python-docx, fpdf2

**Chatbots & Conversational AI**
- Telegram bot in production 24/7: conversation buffer, context management, multi-command routing
- Cover letter auto-fill: Chrome extension injects generated text into Upwork proposal forms
- Claude API integration via custom client library with token management and error handling

## DOMAIN MATCHING (use in L3 and L4)
If the job's industry matches one of Paul's projects, weave in a natural 1-sentence reference:
- Legal/law/compliance/document → Notomai: "I'm building an AI product for notaries right now. Legal document workflows are my daily reality."
- AI agents/automation/workflows → Morpheus: reference the 38-agent system, crons, or specific automations
- CRM/dashboard/data management → mybuilding.dev
- Chatbot/conversational → Telegram bot in production
- RAG/vector/knowledge base → Morpheus memory system
- Scraping/data extraction → Chrome extension, event capture pipeline
- API integration → list the specific APIs you've connected
- If NO match → don't force it. Use generic portfolio items.

L4 — UNDERSTANDING (THE KEY BLOC — spend the most effort here):
  This bloc must be 100% custom to the job. Zero generic content. Zero filler.
  RULES:
  - Break down their project into 2-3 concrete phases/layers (use their own words)
  - Pick 1 portfolio item that directly relates and mention it naturally (not as a sales pitch)
  - Ask 1 SMART question that proves deep understanding (not "what's your timeline?" — something only someone who understood the project would ask)
  - State concrete deliverables the client will receive
  - NEVER open with "Looking at what you've described" — vary the transition every time

L5 — STACK: List tools/technologies relevant to the job. Job-mentioned skills FIRST, then Paul's additional relevant tools.
  Format: "Stack: [tool1], [tool2], [tool3], ..."

L6 — CTA (adaptive — pick the best fit):
  - Urgent/complex job: "I can start today. Send me a message and I'll have a first draft by [tomorrow/next day]."
  - Big budget/long-term: "Happy to jump on a 15-min call to walk through my approach. Send me a message."
  - Small/quick job: "Send me a message. I'll get back to you within the hour."
  - Default: "Send me a message, happy to jump on a quick call."
  Always end with an action the client can take RIGHT NOW.

## VERSION DIFFERENCES
| | Version A | Version B |
|---|-----------|-----------|
| Tone | Direct, confident, factual | Conversational, warmer, more narrative |
| L1 | States the problem + confidence | "caught my eye" + curiosity |
| L3 | Technical proof, numbers | Same proof but framed as a story |
| L4 | Technical breakdown, pointed question | Same breakdown but more exploratory, open question |
| Length | ~150 words | ~180 words |
| Best for | Tech clients, well-specified jobs | Non-tech clients, vague jobs, relationship-focused |

## ANTI-REPETITION RULES
- L1: NEVER use "I've done this exact type of work", "right in my wheelhouse", "this is what I do"
- L3: NEVER copy-paste the same credibility sentence. Always rephrase with different portfolio items.
- L4: NEVER use "Looking at what you've described" as opener. Vary transitions.
- L6: NEVER use the exact same CTA. Adapt to the job's urgency and size.
- General: if a phrase could appear unchanged in another proposal for a different job, REWRITE IT.

## OUTPUT
Return ONLY valid JSON:
{
  "version_a": "...",
  "version_b": "..."
}

Both versions MUST contain all 6 blocs L1-L6 in order."""


@app.post("/api/cover-letter")
async def cover_letter(req: CoverLetterRequest):
    if not req.title.strip():
        raise HTTPException(400, "Titre vide")
    context = f"""JOB TITLE: {req.title}
DESCRIPTION: {req.description or 'Non disponible'}
SKILLS: {', '.join(req.skills) if req.skills else 'Non specifies'}
BUDGET: {req.budget_min or '?'} - {req.budget_max or '?'} ({req.budget_type})
COUNTRY: {req.country or 'Non specifie'}"""
    if req.enrichment:
        if req.enrichment.get("why_for_you"):
            context += f"\n\nWHY FOR PAUL (context): {req.enrichment['why_for_you']}"
        if req.enrichment.get("execution_plan"):
            steps = req.enrichment["execution_plan"]
            plan_str = "\n".join(
                f"  Step {s.get('step', i+1)}: {s.get('title', '')} ({s.get('hours', '')})"
                for i, s in enumerate(steps)
            )
            context += f"\n\nEXECUTION PLAN:\n{plan_str}"
    prompt = COVER_SYSTEM + "\n\n" + context
    try:
        loop = asyncio.get_event_loop()
        # Sonnet for cover letter — nuanced writing quality
        data = await loop.run_in_executor(_executor, _run_claude, prompt, "sonnet", 180)
        return data
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Timeout Claude")
    except Exception as e:
        print(f"cover error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════
# QUICK EVAL — Scoring + Cover Letter in ONE call (mobile flow)
# ══════════════════════════════════════════════════════════════

class QuickEvalRequest(BaseModel):
    description: str


QUICK_EVAL_SYSTEM = SYSTEM.rstrip().rstrip('}').rstrip() + """,
  "cover_letter_a": "<Version A — direct, ~150 words, English>",
  "cover_letter_b": "<Version B — conversational, ~180 words, English>"
}

COVER LETTER RULES (apply to cover_letter_a and cover_letter_b):
- English ONLY. Voice: direct, confident, 27yo French engineer. NEVER corporate.
- NEVER: "Dear Hiring Manager", "I hope this finds you well", "I would love the opportunity"
- Always start with "Hi, I'm Paul." then address the client's specific problem.
- Mention the 38-agent AI system as differentiator.
- 6-BLOC: L1 Hook, L2 Loom placeholder [LOOM_LINK], L3 Credibility (Morpheus/Notomai/mybuilding), L4 Understanding (custom breakdown), L5 Stack, L6 CTA.
- Version A = factual, ~150 words. Version B = warmer, ~180 words.
- If SKIP verdict: cover_letter_a = null, cover_letter_b = null."""


@app.post("/api/quick-eval")
async def quick_eval(req: QuickEvalRequest):
    if not req.description.strip():
        raise HTTPException(400, "Description vide")
    prompt = QUICK_EVAL_SYSTEM + "\n\nJOB DESCRIPTION:\n" + req.description.strip()
    try:
        loop = asyncio.get_event_loop()
        # Sonnet for quick-eval (includes cover letters — needs writing quality)
        data = await loop.run_in_executor(_executor, _run_claude, prompt, "sonnet", 120)
        return data
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Timeout Claude")
    except Exception as e:
        print(f"quick-eval error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════
# FULL PIPELINE — Phase 1+2: analyze+enrich (Haiku) → cover (Sonnet)
# 2 calls instead of 3, first call merged, proper model routing
# ══════════════════════════════════════════════════════════════

class FullPipelineRequest(BaseModel):
    title: str
    description: str = ""
    skills: list = []
    budget_min: Optional[Any] = None
    budget_max: Optional[Any] = None
    budget_type: str = "fixed"
    country: str = ""


ANALYZE_ENRICH_SYSTEM = SYSTEM.rstrip().rstrip('}').rstrip() + """,
  "enrichment": {
    "why_for_you": "<3-4 phrases FR: pourquoi CE job est fait pour Paul. Specifique, mentionne les skills qui matchent, l'avantage competitif>",
    "battle_card": {
      "strengths": ["<3-4 points forts de Paul pour CE job>"],
      "risks": ["<2-3 risques ou points d'attention>"],
      "differentiators": ["<2-3 choses qui differencient Paul>"]
    },
    "execution_plan": [
      {"step": 1, "title": "<titre>", "description": "<1-2 phrases>", "hours": "<~Xh avec IA>", "tools": ["<outil>"], "deliverable": "<livrable>"}
    ],
    "description_fr": "<traduction fidele FR de la description du job>"
  }
}

ENRICHMENT RULES (for the "enrichment" object):
- why_for_you: 3-4 phrases en francais, SPECIFIQUES au job, pas generiques
- battle_card: points forts/risques/differenciateurs concrets
- execution_plan: 4-6 etapes, heures = temps reel AVEC l'IA (pas temps humain)
- description_fr: traduction fidele, pas de resume"""


@app.post("/api/full-pipeline")
async def full_pipeline(req: FullPipelineRequest):
    """Phase 1+2+4: 1 Haiku call (analyze+enrich) → 1 Sonnet call (cover letter).
    Returns combined result with analysis, enrichment, AND cover letters."""
    if not req.description.strip() and not req.title.strip():
        raise HTTPException(400, "Description et titre vides")

    job_context = f"""JOB TITLE: {req.title}
DESCRIPTION: {req.description or 'Non disponible'}
SKILLS: {', '.join(req.skills) if req.skills else 'Non specifies'}
BUDGET: {req.budget_min or '?'} - {req.budget_max or '?'} ({req.budget_type})
COUNTRY: {req.country or 'Non specifie'}"""

    loop = asyncio.get_event_loop()

    # Step 1: Haiku — analyze + enrich in 1 call
    try:
        prompt_ae = ANALYZE_ENRICH_SYSTEM + "\n\n" + job_context
        analysis = await loop.run_in_executor(_executor, _run_claude, prompt_ae, "haiku", 120)
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Timeout Claude (analyze+enrich)")
    except Exception as e:
        print(f"full-pipeline analyze+enrich error: {e}", file=sys.stderr)
        raise HTTPException(500, f"Analyze+enrich failed: {e}")

    # If SKIP verdict, no cover letter needed
    if analysis.get("verdict") == "SKIP":
        analysis["cover_letter_a"] = None
        analysis["cover_letter_b"] = None
        return analysis

    # Step 2: Sonnet — cover letter with enrichment context
    enrichment = analysis.get("enrichment", {})
    cover_context = job_context
    if enrichment.get("why_for_you"):
        cover_context += f"\n\nWHY FOR PAUL (context): {enrichment['why_for_you']}"
    if enrichment.get("execution_plan"):
        steps = enrichment["execution_plan"]
        plan_str = "\n".join(
            f"  Step {s.get('step', i+1)}: {s.get('title', '')} ({s.get('hours', '')})"
            for i, s in enumerate(steps)
        )
        cover_context += f"\n\nEXECUTION PLAN:\n{plan_str}"

    try:
        prompt_cover = COVER_SYSTEM + "\n\n" + cover_context
        covers = await loop.run_in_executor(_executor, _run_claude, prompt_cover, "sonnet", 180)
        analysis["cover_letter_a"] = covers.get("version_a")
        analysis["cover_letter_b"] = covers.get("version_b")
    except Exception as e:
        print(f"full-pipeline cover error: {e}", file=sys.stderr)
        # Return analysis even if cover fails
        analysis["cover_letter_a"] = None
        analysis["cover_letter_b"] = None
        analysis["cover_error"] = str(e)

    return analysis


# ══════════════════════════════════════════════════════════════
# PRE-ENRICH — Phase 5: called at scan time for pre-computation
# analyze+enrich only (no cover letter), cached in Supabase
# ══════════════════════════════════════════════════════════════

class PreEnrichRequest(BaseModel):
    title: str
    description: str = ""
    skills: list = []
    budget_min: Optional[Any] = None
    budget_max: Optional[Any] = None
    budget_type: str = "fixed"
    country: str = ""


@app.post("/api/pre-enrich")
async def pre_enrich(req: PreEnrichRequest):
    """Phase 5: Pre-compute analyze+enrich at scan time (Haiku, fast).
    Called by extension after scan, result cached in Supabase.
    No cover letter — that's generated on-demand when user clicks."""
    if not req.description.strip() and not req.title.strip():
        raise HTTPException(400, "Description et titre vides")

    job_context = f"""JOB TITLE: {req.title}
DESCRIPTION: {req.description or 'Non disponible'}
SKILLS: {', '.join(req.skills) if req.skills else 'Non specifies'}
BUDGET: {req.budget_min or '?'} - {req.budget_max or '?'} ({req.budget_type})
COUNTRY: {req.country or 'Non specifie'}"""

    try:
        loop = asyncio.get_event_loop()
        prompt = ANALYZE_ENRICH_SYSTEM + "\n\n" + job_context
        data = await loop.run_in_executor(_executor, _run_claude, prompt, "haiku", 120)
        return data
    except subprocess.TimeoutExpired:
        raise HTTPException(504, "Timeout Claude")
    except Exception as e:
        print(f"pre-enrich error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))
