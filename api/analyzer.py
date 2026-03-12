"""
mybuilding.dev — Upwork Analyzer API
FastAPI + claude -p (Claude Max OAuth, zero cost)
Port : 3002 (localhost only, nginx proxie /api/)
"""
import subprocess, json, sys
from typing import Optional, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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


SYSTEM = """Tu es GUS, analyste Upwork expert ET rédacteur de propositions. Tu travailles pour Paul Annes.

## PROFIL PAUL ANNES
Stack CORE (tier 1 — forte valeur) : n8n, Claude API, Anthropic, LLM, RAG, agents IA, automation Python, workflow automation, Supabase, webhooks, OpenAI, chatbot, Make, Zapier, LangChain, vector, embedding
Stack ADJACENT (tier 2 — connu) : API REST, TypeScript, React, Next.js, PostgreSQL, scraping, Playwright, NLP, data pipeline, PDF/document processing
Stack STRETCH (tier 3 — limite) : Spark, Kafka, Kubernetes, computer vision, fine-tuning
ANTI-STACK (refuser) : Java, C#, .NET, Swift, Kotlin, iOS, Android, Unity, hardware, embedded, Wordpress, PHP

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
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=90,
        )
        output = result.stdout.strip()

        if result.returncode != 0:
            print(f"claude stderr: {result.stderr[:500]}", file=sys.stderr)
            raise ValueError(f"claude exit {result.returncode}")

        start = output.find("{")
        end = output.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON in response")

        return json.loads(output[start:end])

    except subprocess.TimeoutExpired:
        print("claude timeout", file=sys.stderr)
        raise HTTPException(504, "Timeout Claude")
    except json.JSONDecodeError as e:
        print(f"JSON error: {e} | output: {output[:300]}", file=sys.stderr)
        raise HTTPException(500, "Erreur parsing réponse Claude")
    except Exception as e:
        print(f"analyze error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))


# ══════════════════════════════════════════════════════════════
# JOB ENRICH — Generates "why for you", battle card, plan, FR desc
# ══════════════════════════════════════════════════════════════

ENRICH_SYSTEM = """Tu es un analyste expert Upwork qui travaille pour Paul Annes, freelance AI/automation.

PROFIL PAUL :
- Stack : n8n, Claude API, RAG, agents IA, automation Python, Supabase, webhooks, Make, Zapier, React, Next.js
- Il a construit son propre systeme IA avec 38 agents specialises sur 4 applications en production
- Il va 5-8x plus vite qu'un dev humain grace a son agent IA Morpheus
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
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=90,
        )
        output = result.stdout.strip()

        if result.returncode != 0:
            print(f"claude enrich stderr: {result.stderr[:500]}", file=sys.stderr)
            raise ValueError(f"claude exit {result.returncode}")

        start = output.find("{")
        end = output.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON in enrich response")

        return json.loads(output[start:end])

    except subprocess.TimeoutExpired:
        print("claude enrich timeout", file=sys.stderr)
        raise HTTPException(504, "Timeout Claude")
    except json.JSONDecodeError as e:
        print(f"Enrich JSON error: {e} | output: {output[:300]}", file=sys.stderr)
        raise HTTPException(500, "Erreur parsing reponse Claude")
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
- NEVER: "Dear Hiring Manager", "I hope this finds you well", "I would love the opportunity", "I'm excited", "I'm thrilled", any flattery
- ALWAYS follow the 6-BLOC structure below IN EXACT ORDER. No merging, no skipping.

## 6-BLOC STRUCTURE (MANDATORY ORDER)

L1 — INTRO + HOOK: Start with "Hi! I'm Paul" then a confidence phrase adapted to the job type.
  - Version A example: "Hi! I'm Paul — I've done this exact type of work and I can start right away."
  - Version B example: "Hi! I'm Paul — this one caught my eye because it's right in my wheelhouse."
  Then 1-2 sentences rephrasing what the client REALLY needs (the underlying problem, not just what they wrote).

L2 — LOOM: Place the Loom link EARLY so the client clicks before reading the rest.
  - Big job (budget > $500 or complex): "I recorded a quick Loom walking through how I'd tackle your project specifically. [LOOM_LINK]"
  - Small job (budget <= $500 or quick fix): "Short Loom so you can see who you'd be working with. [LOOM_LINK]"

L3 — CREDIBILITY: Use this EXACT sentence, no changes: "I've built my own AI system with 38 specialized agents across 4 production applications. One person, output of a small team."

L4 — UNDERSTANDING (THE KEY BLOC — spend the most effort here):
  - Open with "Looking at what you've described" or similar natural transition
  - Break down the job scope into 2-3 concrete layers/phases
  - Ask 1 smart question that proves you actually read and understood the job (not a generic question)
  - List what the client will concretely receive as deliverables
  - Close with something like "so you're not left guessing what comes next"
  This bloc must be 100% custom to the job. Zero generic content.

L5 — STACK: List tools/technologies relevant to the job. Put the skills mentioned in the job FIRST, then Paul's additional relevant tools.
  Format: "Stack: [tool1], [tool2], [tool3], ..."

L6 — CTA: Use this EXACT sentence: "Send me a message — I'm online now and happy to jump on a quick call."

## VERSION DIFFERENCES
| | Version A | Version B |
|---|-----------|-----------|
| Tone | Direct, confident, factual | Conversational, warmer |
| L1 | Confident assertion | "caught my eye" vibe |
| L4 | Technical breakdown, pointed question | Same breakdown but more narrative, open question |
| Length | ~150 words | ~180 words |
| Best for | Tech clients, well-specified jobs | Non-tech clients, vague jobs |

## OUTPUT
Return ONLY valid JSON:
{
  "version_a": "...",
  "version_b": "..."
}

Both versions MUST contain all 6 blocs L1-L6 in order. L3 and L6 are VERBATIM, no modifications."""


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
        result = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True, text=True, timeout=90,
        )
        output = result.stdout.strip()

        if result.returncode != 0:
            print(f"claude cover stderr: {result.stderr[:500]}", file=sys.stderr)
            raise ValueError(f"claude exit {result.returncode}")

        start = output.find("{")
        end = output.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON in cover response")

        return json.loads(output[start:end])

    except subprocess.TimeoutExpired:
        print("claude cover timeout", file=sys.stderr)
        raise HTTPException(504, "Timeout Claude")
    except json.JSONDecodeError as e:
        print(f"Cover JSON error: {e} | output: {output[:300]}", file=sys.stderr)
        raise HTTPException(500, "Erreur parsing reponse Claude")
    except Exception as e:
        print(f"cover error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))
