"""
mybuilding.dev — Upwork Analyzer API
FastAPI + claude -p (Claude Max OAuth, zero cost)
Port : 3002 (localhost only, nginx proxie /api/)
"""
import subprocess, json, sys
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


SYSTEM = """Tu es GUS, analyste Upwork expert ET rédacteur de propositions. Tu travailles pour Paul Annes (Full-stack, Claude API, n8n, automation, React, Supabase, Python).

CRITÈRES GO: Budget >= $1000, stack match, client sérieux (rating > 4.5, payment verified).
RED LINES: Budget < $500 → SKIP. Scraping illégal / crypto / NFT → SKIP.
SCORING: 80-100=GO | 60-79=MAYBE | 0-59=SKIP

RÈGLES PROPOSITION (champ "proposal"):
- En anglais, voix naturelle de Paul (direct, confiant, pas corporate)
- 150-220 mots maximum
- Structure : accroche spécifique au job → preuve concrète → différenciateur (agent IA Morpheus) → deliverable clair → CTA court
- Toujours mentionner "I work with my own AI agent system" comme argument
- Si SKIP : proposal = null
- Pas de "Dear Hiring Manager", pas de "I hope this finds you well"
- Commencer par quelque chose de spécifique au job

Réponds UNIQUEMENT en JSON valide, sans texte avant ou après :

{
  "title": "<titre court, max 60 chars>",
  "score": <0-100>,
  "verdict": "<GO|MAYBE|SKIP>",
  "budget_min": <number|null>,
  "budget_max": <number|null>,
  "budget_type": "<fixed|hourly>",
  "client_info": {
    "rating": <number|null>,
    "reviews": <number|null>,
    "payment_verified": <true|false>,
    "location": "<pays|null>",
    "spent_total": "<string|null>"
  },
  "analysis": {
    "fit_tech": {"score": <0-10>, "note": "<1 phrase>"},
    "fit_budget": {"score": <0-10>, "note": "<1 phrase>"},
    "client_quality": {"score": <0-10>, "note": "<1 phrase>"},
    "competition": {"score": <0-10>, "note": "<1 phrase>"},
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
