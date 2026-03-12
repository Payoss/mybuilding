"""
mybuilding.dev — Upwork Job Scorer v1
Ported from UpEarth scoring engine + Morpheus upwork_analyzer.py

Scores unscored jobs in Supabase upwork_jobs table:
  - Feasibility (0-100) via keyword FEAS_B/FEAS_P dictionaries
  - Worth Score (0-10) composite
  - Sniper Mode detection
  - France/FR detection
  - Time estimate
  - Optional Claude enrichment (cover letter + analysis)

Usage:
    python execution/upwork_scorer.py                  # Score all unscored jobs
    python execution/upwork_scorer.py --enrich 5       # Score + Claude enrich top 5
    python execution/upwork_scorer.py --rescore        # Re-score ALL jobs
    python execution/upwork_scorer.py --dry-run        # Preview without writing to DB

Runs on Hetzner via cron or manually. Reads MORPHEUS/.env for credentials.
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─── ENV LOADING ──────────────────────────────────────────────────────────────

def _load_env():
    """Load .env from MORPHEUS project root or mybuilding root."""
    for env_path in [
        Path(__file__).resolve().parent.parent / ".env",          # mybuilding/.env
        Path(__file__).resolve().parent.parent.parent / "MORPHEUS" / ".env",  # MORPHEUS/.env
        Path.home() / "IA" / "VSCode" / "MORPHEUS" / ".env",
    ]:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip().strip("'\""))
            break

_load_env()

# ─── SUPABASE CONFIG ─────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://hjcdshafjkzzjaztqhte.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get("SUPABASE_KEY", "")

# Fallback: read from js/config.js if env vars not set
if not SUPABASE_KEY:
    config_js = Path(__file__).resolve().parent.parent / "js" / "config.js"
    if config_js.exists():
        m = re.search(r"SUPABASE_KEY\s*=\s*['\"]([^'\"]+)", config_js.read_text(encoding="utf-8"))
        if m:
            SUPABASE_KEY = m.group(1)

if not SUPABASE_KEY:
    print("[ERREUR] Supabase key introuvable (.env ou js/config.js)", file=sys.stderr)
    sys.exit(1)


# ─── HTTP HELPERS (no dependencies beyond stdlib) ────────────────────────────

import urllib.request
import urllib.error

def _supabase_headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

def supabase_get(table: str, query: str = "") -> list:
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
    req = urllib.request.Request(url, headers=_supabase_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"[Supabase GET] {e.code} {e.read().decode()[:300]}", file=sys.stderr)
        return []

def supabase_patch(table: str, match_query: str, data: dict) -> bool:
    url = f"{SUPABASE_URL}/rest/v1/{table}?{match_query}"
    headers = _supabase_headers()
    headers["Prefer"] = "return=minimal"
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers, method="PATCH")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 204)
    except urllib.error.HTTPError as e:
        print(f"[Supabase PATCH] {e.code} {e.read().decode()[:300]}", file=sys.stderr)
        return False


# ─── FEASIBILITY ENGINE (ported from UpEarth FEAS_BOOSTS + FEAS_PENALTIES) ──

FEAS_BOOSTS = {
    # Automation & workflow
    "n8n": 20, "make.com": 18, "zapier": 12, "integromat": 10,
    "workflow automation": 18, "workflow": 12, "automation": 14,
    "process automation": 14,
    # Messaging bots
    "telegram bot": 20, "telegram": 16,
    "whatsapp business": 20, "whatsapp": 16, "twilio": 16,
    # AI / LLM
    "claude": 20, "anthropic": 18, "claude api": 20,
    "ai agent": 18, "autonomous agent": 18, "agentic": 16,
    "multi-agent": 14, "multi agent": 14, "langgraph": 12, "crewai": 10,
    "llm integration": 14, "llm": 12, "gpt": 8, "openai": 10,
    "chatbot": 14, "customer support bot": 14, "conversational ai": 12,
    # RAG & vectors
    "rag": 16, "rag pipeline": 18, "retrieval": 14,
    "vector": 12, "embedding": 12, "pinecone": 14, "chroma": 12,
    "knowledge base": 14, "document qa": 16,
    # MCP
    "mcp": 16, "model context protocol": 18, "mcp server": 18,
    # Data tools
    "airtable": 14, "google sheets": 12, "notion": 8,
    "supabase": 12, "railway": 12, "vercel": 8,
    # Dev
    "python": 12, "fastapi": 12, "flask": 8,
    "webhook": 12, "api integration": 14, "rest api": 12,
    # Email
    "email automation": 16, "mailchimp": 12, "sendgrid": 12,
    # CRM & leads
    "crm automation": 16, "lead qualification": 14, "lead generation": 12,
    # Browser
    "browser automation": 14, "playwright": 12, "selenium": 10,
    # Voice
    "voice agent": 12, "voice ai": 12, "vapi": 10, "retell": 10,
    # Doc processing
    "invoice": 12, "pdf extraction": 14, "ocr": 10, "pdf": 10,
    # Social
    "social media automation": 12, "linkedin automation": 10,
    # Misc
    "news aggregator": 12, "newsletter": 10, "rss": 8,
    "retainer": 14, "ongoing": 10, "long term": 10,
    # Scraping
    "scraping": 12, "web scraping": 14, "data extraction": 12,
}

FEAS_PENALTIES = {
    "blockchain": -28, "solidity": -32, "web3": -25, "nft": -28, "defi": -28,
    "ios": -25, "swift": -25, "android": -22, "kotlin": -22,
    "react native": -18, "flutter": -18,
    "rust": -20, "c++": -20, "embedded": -22, "firmware": -28,
    "unity": -22, "unreal": -25, "game development": -18,
    "pytorch": -18, "tensorflow": -18, "fine-tuning": -12,
    "data science": -10, "machine learning model": -12,
    "kubernetes": -12, "terraform": -12,
    "volunteer": -30, "unpaid": -30,
    "wordpress": -15, "php": -15,
    "java ": -15, "c#": -15, ".net": -15,
}


def compute_feasibility(title: str, description: str) -> int:
    """Compute feasibility score 0-100 (UpEarth algorithm)."""
    text = f"{title} {description}".lower()
    score = 45  # Base UpEarth

    for kw, pts in FEAS_BOOSTS.items():
        if kw in text:
            score += pts

    for kw, pts in FEAS_PENALTIES.items():
        if kw in text:
            score += pts

    # Description quality bonus
    if len(description) > 300:
        score += 5
    if len(description) > 600:
        score += 5

    return min(99, max(5, round(score)))


# ─── WORTH SCORE ENGINE (ported from UpEarth computeWorthScore) ──────────────

TIER1_COUNTRIES = [
    "united states", "canada", "australia", "united kingdom", "germany",
    "netherlands", "switzerland", "denmark", "norway", "sweden",
    "france", "singapore", "ireland", "belgium", "austria",
]

def _extract_budget_avg(budget_min, budget_max, budget_type=None):
    """Get average budget from min/max."""
    if budget_min and budget_max:
        avg = (budget_min + budget_max) / 2
        if budget_type == "hourly":
            return avg * 40  # ~1 week equivalent
        return avg
    if budget_min:
        return budget_min
    if budget_max:
        return budget_max
    return 0


def compute_worth_score(
    title: str, description: str, feasibility: int,
    budget_min=None, budget_max=None, budget_type=None,
    country: str = "", posted_at: str = None, is_french: bool = False
) -> float:
    """Compute worth score 0-10 (UpEarth algorithm)."""
    text = f"{title} {description}".lower()
    score = 3.5  # Base

    # Feasibility impact
    if feasibility >= 90:
        score += 3.5
    elif feasibility >= 80:
        score += 2.5
    elif feasibility >= 70:
        score += 1.5
    elif feasibility >= 55:
        score += 0.5
    else:
        score -= 1.5

    # Budget impact
    budget = _extract_budget_avg(budget_min, budget_max, budget_type)
    if budget >= 5000:
        score += 3.5
    elif budget >= 3000:
        score += 3
    elif budget >= 1500:
        score += 2.5
    elif budget >= 800:
        score += 2
    elif budget >= 400:
        score += 1.5
    elif budget >= 200:
        score += 0.8
    elif 0 < budget < 50:
        score -= 2

    # Retainer / long-term signals
    if "retainer" in text or "ongoing" in text or "monthly" in text:
        score += 1.5
    if "long term" in text or "long-term" in text:
        score += 1
    if "urgent" in text or "asap" in text:
        score += 0.5

    # Early bird (age < 2h)
    if posted_at:
        try:
            posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            age_min = (now - posted_dt).total_seconds() / 60
            if age_min < 60:
                score += 1.5
            elif age_min < 120:
                score += 0.8
        except (ValueError, TypeError):
            pass

    # Country tier
    country_lower = (country or "").lower()
    if any(c in country_lower for c in TIER1_COUNTRIES):
        score += 1

    # France bonus
    if is_french:
        score += 0.5

    # Tech bonuses
    if "mcp" in text or "model context protocol" in text:
        score += 1
    if "rag" in text or "rag pipeline" in text:
        score += 0.8

    # Penalties
    if "volunteer" in text or "unpaid" in text:
        score -= 5
    if ("quick" in text or "simple" in text) and budget < 100:
        score -= 1.5

    return min(10.0, max(1.0, round(score * 2) / 2))


# ─── SNIPER MODE (UpEarth) ──────────────────────────────────────────────────

def compute_sniper_mode(
    feasibility: int, worth_score: float,
    posted_at: str = None, budget_min=None, budget_max=None, budget_type=None
) -> bool:
    """Sniper = feas >= 85, worth >= 8.5, age < 2h, budget >= $500."""
    budget = _extract_budget_avg(budget_min, budget_max, budget_type)

    age_minutes = 999
    if posted_at:
        try:
            posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
            age_minutes = (datetime.now(timezone.utc) - posted_dt).total_seconds() / 60
        except (ValueError, TypeError):
            pass

    return (
        feasibility >= 85
        and worth_score >= 8.5
        and age_minutes < 120
        and budget >= 500
    )


# ─── FRANCE DETECTION (ported from UpEarth detectFrench) ─────────────────────

FRENCH_WORDS = [
    "bonjour", "automatisation", "besoin", "développement", "nous recherchons",
    "notre", "système", "créer", "mise en place", "connexion", "traitement",
    "flux de travail", "projet", "société", "entreprise", "envoi",
    "gestion", "données", "service", "outil", "fonctionnalité", "interface",
    "francophone", "français", "france",
]

def detect_french(title: str, description: str, country: str) -> bool:
    """Detect French language or France-based client."""
    if re.search(r"\bfrance\b", country or "", re.IGNORECASE):
        return True
    text = f"{title} {description}".lower()
    if any(w in text for w in FRENCH_WORDS):
        return True
    # Accents heuristic
    if re.search(r"[àâäéèêëîïôùûüç]", f"{title} {description}", re.IGNORECASE):
        return True
    return False


# ─── TIME ESTIMATE (ported from UpEarth) ────────────────────────────────────

def compute_time_estimate(title: str, description: str, feasibility: int) -> str:
    """Return human-readable time estimate."""
    text = f"{title} {description}".lower()
    base_hours = 8

    if "landing" in text or "form" in text:
        base_hours = 4
    if "bot" in text or "telegram" in text or "whatsapp" in text:
        base_hours = 6
    if "workflow" in text or "n8n" in text or "automation" in text:
        base_hours = 8
    if "dashboard" in text or "crm" in text:
        base_hours = 12
    if "saas" in text or "auth" in text or "multi" in text:
        base_hours = 20
    if "agent" in text or "ai system" in text:
        base_hours = 16

    if feasibility < 60:
        base_hours = int(base_hours * 1.5)

    if base_hours <= 4:
        return "2-4h"
    elif base_hours <= 8:
        return "4-8h"
    elif base_hours <= 16:
        return "1-2j"
    else:
        return "2-4j"


# ─── CLAUDE ENRICHMENT (optional) ───────────────────────────────────────────

def enrich_with_claude(job: dict, api_key: str = None) -> dict | None:
    """Call Claude API to generate cover letter + analysis. Returns dict or None."""
    key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        return None

    title = job.get("title", "")
    desc = (job.get("description", "") or "")[:600]
    budget_min = job.get("budget_min") or 0
    budget_max = job.get("budget_max") or 0
    country = job.get("country", "")
    feas = job.get("feasibility", 50)
    worth = job.get("worth_score", 5)
    time_est = job.get("time_estimate", "?")

    prompt = f"""ROLE: Tu es GUS, analyste Upwork + rédacteur de cover letter pour Paul Annes — freelance AI/automation.

JOB: "{title}" | Budget: ${budget_min}-${budget_max} | Pays: {country} | Faisabilité: {feas}% | Score: {worth}/10 | Temps: {time_est}
DESCRIPTION: {desc}

PROFIL PAUL:
- Stack: n8n, Claude API, Python, RAG, agents IA, Supabase, automation, MCP, Playwright
- Edge: "I work with my own AI agent system — one person, output of a small team"

COVER LETTER RULES:
1. Start: "Hi! Confident [job-specific hook]."
2. 150-250 words, EN, prose (no bullets, no prices)
3. Show you READ this specific job (not generic)
4. End with short question or invitation
5. Include [LOOM_LINK] placeholder line 2

JSON ONLY:
{{"summary":"3 phrases FR résumé business","cover_letter":"full cover letter EN 150-250 words","cover_letter_b":"variant B different angle","key_reason":"GO/PASS + reason in 10 words"}}"""

    body = json.dumps({
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1200,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body, headers=headers, method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            text = data.get("content", [{}])[0].get("text", "")
            match = re.search(r"\{[\s\S]+\}", text)
            if match:
                parsed = json.loads(match.group(0))
                return {
                    "cover_letter": parsed.get("cover_letter"),
                    "cover_letter_b": parsed.get("cover_letter_b"),
                }
    except Exception as e:
        print(f"[Claude] Enrichment error: {e}", file=sys.stderr)

    return None


# ─── MAIN SCORER ─────────────────────────────────────────────────────────────

def score_jobs(rescore: bool = False, enrich_count: int = 0, dry_run: bool = False):
    """Fetch unscored jobs from Supabase, score them, update."""

    # Fetch jobs
    if rescore:
        query = "select=*&order=created_at.desc&limit=200"
    else:
        query = "select=*&feasibility=is.null&order=created_at.desc&limit=100"

    jobs = supabase_get("upwork_jobs", query)
    if not jobs:
        print("[Scorer] No jobs to score.")
        return

    print(f"[Scorer] {len(jobs)} jobs to process (rescore={rescore}, enrich={enrich_count})")

    scored = []
    for job in jobs:
        title = job.get("title", "")
        desc = job.get("description", "") or ""
        country = job.get("country", "") or ""
        posted_at = job.get("posted_at")
        budget_min = job.get("budget_min")
        budget_max = job.get("budget_max")
        budget_type = job.get("budget_type")

        # Compute scores
        is_french = detect_french(title, desc, country)
        feas = compute_feasibility(title, desc)
        worth = compute_worth_score(
            title, desc, feas,
            budget_min, budget_max, budget_type,
            country, posted_at, is_french
        )
        sniper = compute_sniper_mode(feas, worth, posted_at, budget_min, budget_max, budget_type)

        # Sniper bonus on worth
        if sniper:
            worth = min(10.0, worth + 2.5)

        time_est = compute_time_estimate(title, desc, feas)

        update = {
            "feasibility": feas,
            "worth_score": worth,
            "sniper_mode": sniper,
            "is_french": is_french,
            "time_estimate": time_est,
        }

        scored.append({**job, **update})

        if dry_run:
            label = "SNIPER" if sniper else ("GO" if worth >= 8 else "ok" if worth >= 6 else "meh")
            fr = " 🇫🇷" if is_french else ""
            print(f"  [{label:6s}] feas={feas:3d}% worth={worth:4.1f} {fr} | {title[:60]}")
        else:
            job_id = job.get("id")
            if job_id:
                ok = supabase_patch("upwork_jobs", f"id=eq.{job_id}", update)
                status = "✓" if ok else "✗"
                print(f"  {status} feas={feas:3d}% worth={worth:4.1f} | {title[:50]}")

    # Claude enrichment for top jobs
    if enrich_count > 0 and not dry_run:
        top_jobs = sorted(scored, key=lambda j: (j.get("worth_score", 0), j.get("feasibility", 0)), reverse=True)
        enriched = 0
        for job in top_jobs[:enrich_count]:
            if job.get("cover_letter"):
                continue  # Already has cover letter
            result = enrich_with_claude(job)
            if result:
                job_id = job.get("id")
                if job_id:
                    ok = supabase_patch("upwork_jobs", f"id=eq.{job_id}", result)
                    status = "✓" if ok else "✗"
                    print(f"  {status} Claude enriched: {job['title'][:50]}")
                    enriched += 1
        print(f"[Scorer] {enriched}/{enrich_count} jobs enriched with Claude.")

    # Summary
    snipers = [j for j in scored if j.get("sniper_mode")]
    golds = [j for j in scored if j.get("worth_score", 0) >= 8 and not j.get("sniper_mode")]
    french = [j for j in scored if j.get("is_french")]

    print(f"\n[Scorer] Done: {len(scored)} scored | {len(snipers)} snipers | {len(golds)} gold | {len(french)} FR")
    if snipers:
        print("  🎯 SNIPERS:")
        for s in snipers[:5]:
            print(f"     {s['worth_score']}/10 — {s['title'][:60]}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    rescore = "--rescore" in sys.argv
    dry_run = "--dry-run" in sys.argv

    enrich_count = 0
    if "--enrich" in sys.argv:
        idx = sys.argv.index("--enrich")
        if idx + 1 < len(sys.argv):
            try:
                enrich_count = int(sys.argv[idx + 1])
            except ValueError:
                enrich_count = 5
        else:
            enrich_count = 5

    print(f"[mybuilding Scorer] Starting... (rescore={rescore}, enrich={enrich_count}, dry_run={dry_run})")
    score_jobs(rescore=rescore, enrich_count=enrich_count, dry_run=dry_run)


if __name__ == "__main__":
    main()
