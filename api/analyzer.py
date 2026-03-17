"""
mybuilding.dev — Upwork Analyzer API
FastAPI + Groq (enrich/analyze) + claude -p Sonnet streaming (cover letters)
Port : 3002 (localhost only, nginx proxie /api/)

Performance:
  - ALL endpoints → Groq Llama 70B (~1-2s). Subprocess/claude CLI eliminated (was 250s+).
  - /api/cover-letter → Groq JSON (single chunk, frontend parses as before)
  - /api/full-pipeline → Groq step1+step2, combined <5s
  - worth_score >= 8 → pre-generation triggered by frontend at job open
"""
import json, sys, asyncio, os, pathlib, re, subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Any

# ── Proof points (static — loaded once at startup)
_PROOF_POINTS_PATH = pathlib.Path(__file__).parent / "proof_points.json"
_PROOF_POINTS = json.loads(_PROOF_POINTS_PATH.read_text())["facts"] if _PROOF_POINTS_PATH.exists() else []

def _select_proof_points(text: str, n: int = 2) -> list[str]:
    """Pick top-n proof points whose keywords appear in the job text."""
    text_lower = text.lower()
    scored = []
    for p in _PROOF_POINTS:
        score = sum(1 for kw in p["keywords"] if kw.lower() in text_lower)
        scored.append((score, p["fact"]))
    scored.sort(key=lambda x: -x[0])
    return [fact for _, fact in scored[:n]]

def _extract_client_signals(title: str, description: str) -> dict:
    """Heuristic extraction of human signals from job posting."""
    text = f"{title} {description}".lower()
    # Tone
    formal_signals = ["we are looking for", "requirements:", "must have", "responsibilities"]
    casual_signals = ["hey", "looking for someone", "quick", "asap", "love", "awesome", "great fit"]
    tone = "casual" if any(s in text for s in casual_signals) else "formal" if any(s in text for s in formal_signals) else "neutral"
    # Urgency
    urgency_signals = ["asap", "urgent", "immediately", "right away", "today", "quickly", "fast"]
    urgency = "high" if any(s in text for s in urgency_signals) else "normal"
    # Emotion
    stress_signals = ["struggling", "stuck", "frustrated", "overwhelmed", "drowning", "behind", "failing", "broken"]
    excited_signals = ["excited", "thrilled", "can't wait", "dream", "vision", "opportunity", "launch"]
    tired_signals = ["tired of", "sick of", "wasting time", "manually", "hours", "tedious", "repetitive"]
    if any(s in text for s in stress_signals):
        emotion = "stressed"
    elif any(s in text for s in excited_signals):
        emotion = "excited"
    elif any(s in text for s in tired_signals):
        emotion = "tired_of_manual_work"
    else:
        emotion = "neutral"
    return {"tone": tone, "urgency": urgency, "emotion": emotion}
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq as GroqClient
from pydantic import BaseModel

_executor = ThreadPoolExecutor(max_workers=4)

# ── Groq client (enrich/analyze — fast structured JSON)
_groq = GroqClient(api_key=os.environ.get("GROQ_API_KEY", ""))

# haiku routes → Groq Llama 70B (~1s). sonnet routes → Claude subprocess (streaming).
GROQ_MODEL = "llama-3.3-70b-versatile"

app = FastAPI(title="mybuilding-api", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mybuilding.dev", "https://www.mybuilding.dev", "http://localhost", "http://localhost:3000", "http://127.0.0.1"],
    allow_origin_regex=r"^chrome-extension://.*$",
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
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

def _format_cover_letter(text: str) -> str:
    """Format cover letter with proper paragraph breaks between blocks.
    Ensures L1-L6 blocks are visually separated even if LLM outputs a wall of text."""
    if not text:
        return text
    # Replace em-dashes
    text = text.replace("—", ",").replace("–", ",")
    # If already has paragraph breaks (2+ newlines), leave it
    if "\n\n" in text:
        return text.strip()
    # Insert breaks before known block starters
    block_starters = [
        "I recorded a quick Loom", "I recorded a Loom", "Short Loom", "Here's a quick Loom",
        "I've built", "I run", "My setup", "I work with",
        "Looking at", "The way I see", "Breaking this down", "Your project", "You need", "Here's how",
        "What's the current", "One question", "Quick question", "How do you",
        "Built on", "Stack:", "Tools:",
        "Send me a message", "Happy to jump", "I can start", "Let's set up",
    ]
    for starter in block_starters:
        if starter in text:
            # Insert double newline before the starter (if not at beginning)
            idx = text.find(starter)
            if idx > 0 and text[idx-1] != '\n':
                text = text[:idx] + "\n\n" + text[idx:]
    return text.strip()


def _parse_json_from_output(output: str) -> dict:
    """Extract and parse JSON from LLM output. Formats cover letters with paragraph breaks."""
    output = output.strip()
    start = output.find("{")
    end = output.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON in LLM response: {output[:200]}")
    data = json.loads(output[start:end])
    for key in ("cover_letter_a", "cover_letter_b", "version_a", "version_b", "proposal"):
        if key in data and isinstance(data[key], str):
            data[key] = _format_cover_letter(data[key])
    return data


def _run_groq(prompt: str, timeout: int = 30) -> dict:
    """Groq Llama 70B — structured JSON tasks (enrich, analyze, pre-enrich). ~1s."""
    response = _groq.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        timeout=timeout,
    )
    raw = response.choices[0].message.content
    return _parse_json_from_output(raw)


def _run_claude(prompt: str, model: str = "haiku", timeout: int = 120) -> dict:
    """All routes → Groq Llama 70B (~1-2s). Subprocess eliminated — was timing out at 250s+."""
    return _run_groq(prompt, timeout=min(timeout, 55))


def _stream_sonnet(prompt: str, timeout: int = 55):
    """Cover letters via Groq (~1-2s). Returns JSON as single chunk.
    StreamingResponse kept for frontend compat — client parses the JSON chunk as before."""
    data = _run_groq(prompt, timeout=timeout)
    yield json.dumps(data)


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

## RÈGLES PROPOSAL (FORMAT ALEX — OBLIGATOIRE)
- Anglais, voix naturelle de Paul (direct, confiant, jamais corporate)
- 150-180 mots maximum
- STRUCTURE EXACTE en 4 blocs séparés par des lignes vides :

BLOC 1 HOOK (3 lignes) :
  "Hi! [cite UN DÉTAIL SPÉCIFIQUE de la description, pas le titre]."
  "Here's a quick video presentation of me: [LOOM_URL]"
  "I've built [projet similaire exact] for [type client similaire] — [résultat chiffré]."

BLOC 2 PROOF (identique à chaque fois) :
  "My setup is different: I run ZERO ONE — an autonomous AI system of 38 specialized agents covering debugging, architecture, quality control and delivery. It means I ship 2-4x faster than a solo dev."

BLOC 3 PLAN (numéroté 1-2-3) :
  "Here's how I'd approach this:"
  "1. [Action technique spécifique liée au brief]"
  "2. [Deuxième action — montre la profondeur]"
  "3. [Livrable final + timeline réaliste]"

BLOC 4 CTA (1 ligne) :
  "Happy to jump on a quick call to map out the architecture."

- JAMAIS de question à la fin. JAMAIS "Dear Hiring Manager". JAMAIS "I can do it easily".
- Presumptive close dans le step 3 : timeline concrète.
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

4. "description_fr" : traduction fidele et COMPLETE de la description du job en francais.
   REGLES STRICTES :
   - Traduire UNIQUEMENT ce qui est present dans DESCRIPTION. Jamais inventer, jamais completer.
   - Si DESCRIPTION est vide ou < 50 chars : description_fr = "<Description non disponible — ouvrir le job sur Upwork pour l'extraire>"
   - Ne JAMAIS utiliser les champs SKILLS pour construire la description. Ce sont des metadata, pas du contenu.
   - Traduction mot-a-mot. Pas de resume. Pas de paraphrase.

Reponds UNIQUEMENT en JSON valide, sans texte avant ou apres."""


@app.post("/api/job-enrich")
async def job_enrich(req: EnrichRequest):
    if not req.title:
        req.title = "Untitled"
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

COVER_SYSTEM = """You write Upwork cover letters for Paul Annes using the ALEX METHOD.
Generate TWO versions (A=direct, B=conversational) following the EXACT SAME 4-bloc structure.

## PAUL'S PROFILE
- AI automation specialist, 38 AI agents system (ZERO ONE)
- Expert n8n/Make/Telegram bots, Claude API native, bilingual FR/EN
- Built Notomai: legal AI SaaS, documents in <30s, team of 3, beta with real notaries
- Telegram bot 24/7: 100+ msgs/day, automated briefings
- 50+ production n8n workflows, 12+ API integrations live

## EXACT 4-BLOC STRUCTURE (BOTH VERSIONS MUST FOLLOW THIS)

═══ BLOC 1 — HOOK (3 lines) ═══
"Hi! [Cite ONE SPECIFIC DETAIL from the job description — NOT the title]."
"Here's a quick video presentation of me: [LOOM_URL]"
"I've built [exact similar project] for [similar client type] — [concrete numbered result]."

═══ BLOC 2 — PROOF (constant) ═══
"My setup is different: I run ZERO ONE — an autonomous AI system of 38 specialized agents covering debugging, architecture, quality control and delivery. It means I ship 2-4x faster than a solo dev."

═══ BLOC 3 — PLAN (numbered 1-2-3) ═══
"Here's how I'd approach this:"
"1. [Specific action from the brief]"
"2. [Second action — technical depth]"
"3. [Final deliverable + timeline]"

═══ BLOC 4 — CTA (1 line) ═══
"Happy to jump on a quick call to map out the architecture."

## VERSION DIFFERENCES
- Version A (~150 words): More direct, factual hook, technical plan steps
- Version B (~170 words): Warmer hook (acknowledge client pain), slightly more narrative plan

## RULES
- English ONLY. 150-180 words per version.
- NEVER: "Dear Hiring Manager", "I hope this finds you", "I'm excited", "I would love to", "I can do it easily"
- NEVER end with a question. NEVER mention price.
- Each bloc separated by blank line. Do NOT label blocs.
- BLOC 2 is IDENTICAL in both versions.
- BLOC 3 steps must be SPECIFIC to this job.

## OUTPUT — valid JSON only:
{
  "version_a": "full cover letter A with \\n\\n between blocs",
  "version_b": "full cover letter B with \\n\\n between blocs"
}"""


def _build_cover_context(req) -> str:
    """Build cover letter prompt context from request."""
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
    # Inject human signals + selected proof points
    full_text = f"{req.title} {req.description or ''}"
    signals = _extract_client_signals(req.title, req.description or "")
    context += f"\n\nCLIENT_SIGNALS:\n- tone: {signals['tone']}\n- urgency: {signals['urgency']}\n- emotion: {signals['emotion']}"
    proof_points = _select_proof_points(full_text)
    if proof_points:
        context += "\n\nSELECTED_PROOF_POINTS (use these in L3, rephrase naturally):\n"
        context += "\n".join(f"- {p}" for p in proof_points)
    return context


@app.post("/api/cover-letter")
async def cover_letter(req: CoverLetterRequest):
    """Sonnet streaming — tokens arrive live, perceived as instant."""
    if not req.title.strip():
        raise HTTPException(400, "Titre vide")
    context = _build_cover_context(req)
    prompt = COVER_SYSTEM + "\n\n" + context

    def stream_gen():
        accumulated = []
        for chunk in _stream_sonnet(prompt):
            accumulated.append(chunk)
            # Stream raw text chunks — frontend reassembles JSON
            yield chunk
        # After stream ends, ensure em-dashes stripped (best-effort on full text)
        # Frontend handles JSON parsing from accumulated stream

    return StreamingResponse(stream_gen(), media_type="text/plain; charset=utf-8")


# ══════════════════════════════════════════════════════════════
# QUICK EVAL — Scoring + Cover Letter in ONE call (mobile flow)
# ══════════════════════════════════════════════════════════════

class QuickEvalRequest(BaseModel):
    description: str


QUICK_EVAL_SYSTEM = SYSTEM.rstrip().rstrip('}').rstrip() + """,
  "cover_letter_a": "<Version A — direct, ~150 words, FORMAT ALEX>",
  "cover_letter_b": "<Version B — conversational, ~170 words, FORMAT ALEX>"
}

COVER LETTER FORMAT ALEX (BOTH versions MUST follow this 4-bloc structure):

BLOC 1 HOOK (3 lines):
  "Hi! [cite UN DETAIL SPECIFIQUE de la description, PAS le titre]."
  "Here's a quick video presentation of me: [LOOM_URL]"
  "I've built [projet similaire] for [client similaire] — [resultat chiffre]."

BLOC 2 PROOF (identique dans toutes les proposals):
  "My setup is different: I run ZERO ONE — an autonomous AI system of 38 specialized agents covering debugging, architecture, quality control and delivery. It means I ship 2-4x faster than a solo dev."

BLOC 3 PLAN (numerote 1-2-3):
  "Here's how I'd approach this:"
  "1. [Action specifique liee au brief]"
  "2. [Deuxieme action]"
  "3. [Livrable final + timeline]"

BLOC 4 CTA (1 ligne):
  "Happy to jump on a quick call to map out the architecture."

RULES: NEVER question at end. NEVER "Dear Hiring Manager". Each bloc separated by blank line.
Version A = more direct. Version B = warmer tone, acknowledge client pain.
If SKIP verdict: cover_letter_a = null, cover_letter_b = null."""


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
- description_fr: traduction fidele mot-a-mot. Si DESCRIPTION < 50 chars ou absente → "<Description non disponible — ouvrir le job sur Upwork>". JAMAIS utiliser les SKILLS pour construire la description."""


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

    # Step 2: Sonnet streaming — cover letter with enrichment context
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

    prompt_cover = COVER_SYSTEM + "\n\n" + cover_context

    # Stream: send analysis JSON first, then stream cover tokens
    def full_pipeline_stream():
        # First chunk: analysis JSON (enrich data for frontend to cache)
        yield "ANALYSIS:" + json.dumps(analysis) + "\n"
        # Then stream cover letter tokens live
        yield "COVER:"
        for chunk in _stream_sonnet(prompt_cover):
            yield chunk

    return StreamingResponse(full_pipeline_stream(), media_type="text/plain; charset=utf-8")


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


# ══════════════════════════════════════════════════════════════
# SPY — Méthode Alex Step 1: Espionnage du job avant rédaction
# Analyse les besoins cachés, frustration, vrai budget, angle d'attaque
# ══════════════════════════════════════════════════════════════

class SpyRequest(BaseModel):
    title: str
    description: str = ""
    skills: list = []
    budget_min: Optional[Any] = None
    budget_max: Optional[Any] = None
    budget_type: str = "fixed"
    country: str = ""


# Load hooks library for niche matching
_HOOKS_LIBRARY_PATH = pathlib.Path(__file__).parent / "hooks_library.json"
_HOOKS_LIBRARY = json.loads(_HOOKS_LIBRARY_PATH.read_text()) if _HOOKS_LIBRARY_PATH.exists() else {}


def _match_niche(title: str, description: str) -> tuple[str, list[str]]:
    """Match job to a niche from hooks_library.json. Returns (niche_id, hooks)."""
    text = f"{title} {description}".lower()
    best_niche = "generic"
    best_score = 0
    for niche_id, niche_data in _HOOKS_LIBRARY.get("niches", {}).items():
        score = sum(1 for kw in niche_data.get("keywords", []) if kw.lower() in text)
        if score > best_score:
            best_score = score
            best_niche = niche_id
    hooks = _HOOKS_LIBRARY.get("niches", {}).get(best_niche, {}).get("hooks", [])
    return best_niche, hooks


SPY_SYSTEM = """Tu es un espion qui analyse les job posts Upwork pour Paul Annes.
Tu ne rédiges PAS de cover letter. Tu fais le TRAVAIL D'ESPIONNAGE — lire entre les lignes.

Analyse ce job post et donne-moi en JSON :

{
  "real_need": "<Ce que le client veut VRAIMENT — pas ce qu'il dit, ce qu'il veut au fond. 2-3 phrases>",
  "frustration": "<Sa frustration probable : mauvaise expérience passée ? deadline ratée ? dev incompétent ? scope qui dérive ? Ou rien de détecté. 1-2 phrases>",
  "real_budget": "<Le vrai budget : est-il flexible ? sous-estimé ? placeholder Upwork ($5/$10/$25) ? Estimation réaliste en $. 1 phrase>",
  "attack_angle": "<L'angle d'attaque UNIQUE pour la cover letter de Paul — ce qui va le différencier. 2 phrases>",
  "red_flags": "<Red flags éventuels : time-waster, scope creep, client difficile, budget irréaliste. Ou 'Aucun red flag détecté.' 1-2 phrases>",
  "hook_opening": "<Le hook d'ouverture parfait en 1 phrase — cite un DÉTAIL PRÉCIS du brief, pas le titre>",
  "niche_detected": "<chatbot|n8n_automation|telegram_whatsapp|lead_generation|api_integration|rag_knowledge|generic>",
  "emotion": "<stressed|excited|tired_of_manual_work|neutral|urgent>",
  "tone_recommended": "<casual|direct|technical|empathetic>"
}

RÈGLES :
- Analyse en FRANÇAIS
- Sois SPÉCIFIQUE — pas de phrases génériques
- Le hook_opening doit citer un détail PRÉCIS du brief (pas le titre)
- Si le budget est $5/$10/$25, c'est un placeholder Upwork — le signaler
- Ne jamais inventer des informations non présentes dans le brief

Réponds UNIQUEMENT en JSON valide."""


@app.post("/api/spy")
async def spy_job(req: SpyRequest):
    """Méthode Alex Step 1 — Espionnage du job.
    Analyse besoins cachés, frustration, vrai budget, angle d'attaque, red flags."""
    if not req.title.strip() and not req.description.strip():
        raise HTTPException(400, "Titre et description vides")

    # Match niche + get hooks
    niche, hooks = _match_niche(req.title, req.description or "")
    client_signals = _extract_client_signals(req.title, req.description or "")

    context = f"""JOB TITLE: {req.title}
DESCRIPTION: {req.description or 'Non disponible'}
SKILLS: {', '.join(req.skills) if req.skills else 'Non specifies'}
BUDGET: {req.budget_min or '?'} - {req.budget_max or '?'} ({req.budget_type})
COUNTRY: {req.country or 'Non specifie'}"""

    prompt = SPY_SYSTEM + "\n\n" + context
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(_executor, _run_groq, prompt, 30)
        # Enrich with local analysis
        data["niche_matched"] = niche
        data["hooks_available"] = hooks
        data["client_signals"] = client_signals
        data["proof_points"] = _select_proof_points(f"{req.title} {req.description or ''}", n=3)
        return data
    except Exception as e:
        print(f"spy error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════
# COVER ALEX — Méthode Alex cover letter (Hook→Proof→Plan→CTA)
# 150-180 mots, prose pure, jamais de question, Loom à la fin
# ══════════════════════════════════════════════════════════════

class CoverAlexRequest(BaseModel):
    title: str
    description: str = ""
    skills: list = []
    budget_min: Optional[Any] = None
    budget_max: Optional[Any] = None
    budget_type: str = "fixed"
    country: str = ""
    spy_data: Optional[dict] = None  # Output from /api/spy


ALEX_SYSTEM = """You write Upwork cover letters for Paul Annes using the ALEX METHOD.
Your output must follow the EXACT structure below. No deviation. No creativity on the structure.

## PAUL'S PROFILE
- AI automation specialist, 38 AI agents system (ZERO ONE)
- Expert n8n/Make/Telegram bots, Claude API native, bilingual FR/EN
- Built Notomai: legal AI SaaS, documents in <30s, team of 3, beta with real notaries
- Built mybuilding.dev: freelance CRM with AI scoring, Chrome extension
- 50+ production n8n workflows, 12+ API integrations live
- Telegram bot 24/7: 100+ msgs/day, automated briefings, budget tracking

## EXACT STRUCTURE (FOLLOW THIS CHARACTER BY CHARACTER)

═══ BLOC 1 — HOOK (3 lines) ═══

Line 1: "Hi! [Phrase that PROVES you read the brief — cite ONE SPECIFIC DETAIL from the description, NOT the title. Something only someone who read it would mention]."
Line 2: "Here's a quick video presentation of me: [LOOM_URL]"
Line 3: "I've built [exact similar project] for [similar client type] — [concrete numbered result]."

HOOK RULES:
- Line 1 starts with "Hi!" (not "Hi, I'm Paul")
- Line 1 MUST cite a specific detail FROM THE DESCRIPTION (a feature, a tool, a pain point)
- Line 2 is ALWAYS the Loom link — identical every time
- Line 3 is a proof of similar work with a NUMBER (300 leads, 7 articles/day, <30s generation, etc.)
- NEVER say "I'm excited", "this caught my eye", "I'd love to"

═══ BLOC 2 — PROOF (constant — same every time) ═══

"My setup is different: I run ZERO ONE — an autonomous AI system of 38 specialized agents covering debugging, architecture, quality control and delivery. It means I ship 2-4x faster than a solo dev."

PROOF RULES:
- This paragraph is IDENTICAL in every single proposal
- Always say "ZERO ONE" (the name of the system)
- Always say "38 specialized agents"
- Always say "2-4x faster"
- NEVER change the structure of this paragraph — only minor word variations allowed

═══ BLOC 3 — PLAN (numbered 1-2-3) ═══

"Here's how I'd approach this:"
"1. [Specific technical action tied to the brief — use their words/tools]"
"2. [Second action — shows technical depth]"
"3. [Final deliverable + realistic timeline: 'first version by Thursday', 'ready in 3 days']"

PLAN RULES:
- Start with "Here's how I'd approach this:" on its own line
- Exactly 3 numbered steps (1. 2. 3.)
- Steps must be SPECIFIC to THIS job — not generic
- Use the client's own words and tools from the brief
- Step 3 MUST include a concrete timeline
- Presumptive close: write as if the project already started
- If SPY_DATA provides an execution plan, use those steps as inspiration

═══ BLOC 4 — CTA (1 line — confident) ═══

"Happy to jump on a quick call to map out the architecture."

CTA RULES:
- ONE line only
- Confident affirmation — NOT a question
- NEVER end with "?" — NEVER ask "What do you think?", "Does that work?", "Interested?"
- NEVER mention price
- Can vary slightly: "Happy to jump on a quick call to walk through this." or "Happy to discuss the details on a quick call."

## ABSOLUTE RULES
- English ONLY
- 150-180 words TOTAL
- Tone: direct, human, like a message to a friend who's an expert. NOT corporate. NOT salesy.
- NEVER: "Dear Hiring Manager", "I hope this finds you well", "I would love the opportunity"
- NEVER: "I can do it easily", "simple task for me", "this is right in my wheelhouse"
- NEVER end with a question
- Each BLOC separated by a blank line (\\n\\n)
- Do NOT label the blocs — they flow naturally
- The numbered list in BLOC 3 is the ONLY formatting — rest is prose

## SPY DATA (injected dynamically)
If SPY_DATA is provided:
- Use hook_opening as inspiration for BLOC 1 line 1
- Use attack_angle to sharpen BLOC 3 steps
- If emotion = stressed → be calm and solution-first in tone
- If emotion = excited → match the energy
- If frustration detected → briefly acknowledge it in BLOC 1

## OUTPUT
Return ONLY valid JSON:
{
  "cover_alex": "the full cover letter with \\n\\n between blocs and \\n between lines within blocs"
}"""


@app.post("/api/cover-alex")
async def cover_alex(req: CoverAlexRequest):
    """Méthode Alex cover letter — 4 blocs, 150-180 mots, prose pure."""
    if not req.title.strip():
        raise HTTPException(400, "Titre vide")

    context = f"""JOB TITLE: {req.title}
DESCRIPTION: {req.description or 'Non disponible'}
SKILLS: {', '.join(req.skills) if req.skills else 'Non specifies'}
BUDGET: {req.budget_min or '?'} - {req.budget_max or '?'} ({req.budget_type})
COUNTRY: {req.country or 'Non specifie'}"""

    # Inject spy data if available
    if req.spy_data:
        spy = req.spy_data
        context += f"\n\nSPY_DATA:"
        if spy.get("hook_opening"):
            context += f"\n- hook_opening: {spy['hook_opening']}"
        if spy.get("attack_angle"):
            context += f"\n- attack_angle: {spy['attack_angle']}"
        if spy.get("real_need"):
            context += f"\n- real_need: {spy['real_need']}"
        if spy.get("tone_recommended"):
            context += f"\n- tone_recommended: {spy['tone_recommended']}"
        if spy.get("emotion"):
            context += f"\n- emotion: {spy['emotion']}"
        if spy.get("frustration"):
            context += f"\n- frustration: {spy['frustration']}"

    # Inject proof points
    proof_points = _select_proof_points(f"{req.title} {req.description or ''}", n=2)
    if proof_points:
        context += "\n\nRELEVANT_PROOF_POINTS (use in BLOC 3 if helpful):\n"
        context += "\n".join(f"- {p}" for p in proof_points)

    prompt = ALEX_SYSTEM + "\n\n" + context
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(_executor, _run_groq, prompt, 30)
        # Format the cover letter
        if "cover_alex" in data and isinstance(data["cover_alex"], str):
            data["cover_alex"] = _format_cover_letter(data["cover_alex"])
        return data
    except Exception as e:
        print(f"cover-alex error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))
