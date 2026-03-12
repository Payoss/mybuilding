"""
mybuilding.dev — Upwork Telegram Gold Alerts
Envoie des alertes Telegram pour les jobs sniper/gold détectés.

Usage:
    python upwork_telegram_alerts.py              Check & alert (cron)
    python upwork_telegram_alerts.py --dry-run    Preview sans envoyer

Intégration: Cron toutes les 10 min via Hetzner ou Windows Task Scheduler.
Utilise le bot Telegram Morpheus existant.
"""

import sys
import os
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ── Config ──
PROJECT_ROOT = Path(__file__).parent.parent
MORPHEUS_ROOT = PROJECT_ROOT.parent / "MORPHEUS"

# Load .env from MORPHEUS (Telegram token lives there)
for env_path in [MORPHEUS_ROOT / ".env", PROJECT_ROOT / ".env"]:
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Supabase — try env, fallback to js/config.js
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

if not SUPABASE_URL:
    config_js = PROJECT_ROOT / "js" / "config.js"
    if config_js.exists():
        import re
        text = config_js.read_text(encoding="utf-8")
        m_url = re.search(r"SUPABASE_URL\s*=\s*['\"]([^'\"]+)", text)
        m_key = re.search(r"SUPABASE_KEY\s*=\s*['\"]([^'\"]+)", text)
        if m_url:
            SUPABASE_URL = m_url.group(1)
        if m_key:
            SUPABASE_KEY = m_key.group(1)

# Track file to avoid duplicate alerts
SENT_FILE = PROJECT_ROOT / ".tmp" / "telegram_alerts_sent.json"


def supabase_get(table, query=""):
    """GET from Supabase REST API."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?{query}"
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"[ERROR] Supabase GET: {e}", file=sys.stderr)
        return []


def send_telegram(text, parse_mode="HTML"):
    """Send message via Telegram Bot API."""
    if not BOT_TOKEN or not CHAT_ID:
        print("[ERROR] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]

    for chunk in chunks:
        payload = {"chat_id": CHAT_ID, "text": chunk}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                if not result.get("ok"):
                    print(f"[ERROR] Telegram: {result}", file=sys.stderr)
                    return False
        except Exception as e:
            if parse_mode == "HTML":
                return send_telegram(chunk, parse_mode=None)
            print(f"[ERROR] Telegram send: {e}", file=sys.stderr)
            return False
    return True


def load_sent_ids():
    """Load previously alerted job IDs."""
    if SENT_FILE.exists():
        try:
            data = json.loads(SENT_FILE.read_text(encoding="utf-8"))
            # Prune entries older than 7 days
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            return {k: v for k, v in data.items() if v > cutoff}
        except Exception:
            return {}
    return {}


def save_sent_ids(sent):
    """Save alerted job IDs."""
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SENT_FILE.write_text(json.dumps(sent, indent=2), encoding="utf-8")


def format_sniper_alert(jobs):
    """Format sniper jobs for Telegram."""
    lines = ["🎯 <b>SNIPER ALERT — Upwork</b>", ""]
    for j in jobs[:5]:
        worth = j.get("worth_score", 0)
        feas = j.get("feasibility", 0)
        budget = ""
        if j.get("budget_min") or j.get("budget_max"):
            bmin = j.get("budget_min", 0)
            bmax = j.get("budget_max", bmin)
            budget = f"${bmin}" if bmin == bmax else f"${bmin}-${bmax}"
        fr_tag = " 🇫🇷" if j.get("is_french") else ""
        title = (j.get("title") or "—")[:60]
        url = j.get("url") or ""

        lines.append(f"<b>{title}</b>{fr_tag}")
        lines.append(f"  💎 {worth}/10 · {feas}% feas · {budget}")
        if url:
            lines.append(f"  → {url}")
        lines.append("")

    lines.append(f"<i>mybuilding.dev · {datetime.now().strftime('%H:%M')}</i>")
    return "\n".join(lines)


def format_gold_alert(jobs):
    """Format gold jobs for Telegram."""
    lines = [f"⭐ <b>GOLD JOBS — {len(jobs)} worth ≥ 8/10</b>", ""]
    for j in jobs[:5]:
        worth = j.get("worth_score", 0)
        feas = j.get("feasibility", 0)
        title = (j.get("title") or "—")[:55]
        fr_tag = " 🇫🇷" if j.get("is_french") else ""
        lines.append(f"• <b>{title}</b>{fr_tag} — {worth}/10 · {feas}%")

    lines.append(f"\n<i>mybuilding.dev · {datetime.now().strftime('%H:%M')}</i>")
    return "\n".join(lines)


def main():
    dry_run = "--dry-run" in sys.argv

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[ERROR] Supabase not configured", file=sys.stderr)
        sys.exit(1)

    # Fetch recent jobs (last 30 min to catch new scrapes)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    jobs = supabase_get(
        "upwork_jobs",
        f"source=eq.extension&scraped_at=gte.{cutoff}&order=worth_score.desc"
    )

    if not jobs:
        print(f"[{datetime.now().strftime('%H:%M')}] No recent jobs")
        return

    # Filter already alerted
    sent = load_sent_ids()
    new_jobs = [j for j in jobs if j.get("id") and j["id"] not in sent]

    if not new_jobs:
        print(f"[{datetime.now().strftime('%H:%M')}] All jobs already alerted")
        return

    snipers = [j for j in new_jobs if j.get("sniper_mode")]
    golds = [j for j in new_jobs if j.get("worth_score", 0) >= 8 and not j.get("sniper_mode")]

    alerts_sent = 0

    if snipers:
        msg = format_sniper_alert(snipers)
        if dry_run:
            print("=== SNIPER ALERT ===")
            print(msg)
        else:
            if send_telegram(msg):
                alerts_sent += len(snipers)
                for j in snipers:
                    sent[j["id"]] = datetime.now(timezone.utc).isoformat()

    if golds:
        msg = format_gold_alert(golds)
        if dry_run:
            print("=== GOLD ALERT ===")
            print(msg)
        else:
            if send_telegram(msg):
                alerts_sent += len(golds)
                for j in golds:
                    sent[j["id"]] = datetime.now(timezone.utc).isoformat()

    if not dry_run:
        save_sent_ids(sent)

    print(f"[{datetime.now().strftime('%H:%M')}] {alerts_sent} alerts sent ({len(snipers)} sniper, {len(golds)} gold)")


if __name__ == "__main__":
    main()
