"""
mybuilding.dev — Upwork Analyzer API
FastAPI + Anthropic SDK (claude-haiku-4-5, key depuis /root/morpheus/.env)
Port : 3002 (localhost only, nginx proxie /api/)
"""
import json, sys, os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

app = FastAPI(title="mybuilding-api", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://mybuilding.dev", "https://www.mybuilding.dev", "http://localhost"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


class JobRequest(BaseModel):
    description: str
    profile: dict = {}


SYSTEM = """Tu es GUS, analyste Upwork expert. Tu analyses des jobs pour Paul Annes (Full-stack, Claude API, n8n, automation, React, Supabase, Python).

CRITÈRES GO: Budget >= $1000, stack match, client sérieux (rating > 4.5, payment verified).
RED LINES: Budget < $500 → SKIP. Scraping illégal / crypto / NFT → SKIP.
SCORING: 80-100=GO | 60-79=MAYBE | 0-59=SKIP

Réponds UNIQUEMENT en JSON valide, sans texte avant ou après."""

SCHEMA = """{
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
  "keywords_hit": ["keyword1"]
}"""


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "mybuilding-api"}


@app.post("/api/analyze")
async def analyze(req: JobRequest):
    if not req.description.strip():
        raise HTTPException(400, "Description vide")

    prompt = f"Schema JSON obligatoire:\n{SCHEMA}\n\nJOB DESCRIPTION:\n{req.description.strip()}"

    try:
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        output = msg.content[0].text.strip()

        start = output.find("{")
        end = output.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON in response")

        return json.loads(output[start:end])

    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e} | output: {output[:300]}", file=sys.stderr)
        raise HTTPException(500, "Erreur parsing réponse Claude")
    except Exception as e:
        print(f"analyze error: {e}", file=sys.stderr)
        raise HTTPException(500, str(e))
