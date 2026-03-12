"""
Run migration_002_upearth.sql against Supabase.

Usage:
    python sql/run_migration.py                    Execute via psycopg2 (if available)
    python sql/run_migration.py --check            Check which columns/tables exist
    python sql/run_migration.py --rest             Try statement-by-statement via REST

Requires either:
  - psycopg2 + SUPABASE_DB_PASSWORD in env
  - Or: copy-paste into Supabase Dashboard SQL Editor
"""

import sys
import os
import json
import urllib.request
from pathlib import Path

MIGRATION_FILE = Path(__file__).parent / "migration_002_upearth.sql"
PROJECT_REF = "hjcdshafjkzzjaztqhte"
DB_HOST = f"db.{PROJECT_REF}.supabase.co"
DB_PORT = 5432
DB_NAME = "postgres"
DB_USER = "postgres"

# Try to find credentials
MYBUILDING_ROOT = Path(__file__).parent.parent
MORPHEUS_ROOT = MYBUILDING_ROOT.parent / "MORPHEUS"

SB_URL = f"https://{PROJECT_REF}.supabase.co"
SB_KEY = ""

# Load keys from config.js
config_js = MYBUILDING_ROOT / "js" / "config.js"
if config_js.exists():
    import re
    text = config_js.read_text(encoding="utf-8")
    m = re.search(r"SUPABASE_KEY\s*=\s*['\"]([^'\"]+)", text)
    if m:
        SB_KEY = m.group(1)


def check_columns():
    """Check which columns/tables exist."""
    print("Checking existing schema...\n")

    # Check upwork_jobs columns
    new_columns = [
        "url", "country", "posted_at", "scraped_at", "feasibility",
        "worth_score", "sniper_mode", "is_french", "time_estimate",
        "cover_letter", "source", "skills", "budget_is_placeholder"
    ]

    for col in new_columns:
        url = f"{SB_URL}/rest/v1/upwork_jobs?select={col}&limit=0"
        req = urllib.request.Request(url, headers={
            "apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"
        })
        try:
            urllib.request.urlopen(req, timeout=5)
            print(f"  ✓ upwork_jobs.{col} exists")
        except urllib.error.HTTPError:
            print(f"  ✗ upwork_jobs.{col} MISSING")
        except Exception as e:
            print(f"  ? upwork_jobs.{col} error: {e}")

    # Check new tables
    for table in ["calendar_events", "checkins", "proposal_stats", "job_hour_stats"]:
        url = f"{SB_URL}/rest/v1/{table}?select=id&limit=0"
        req = urllib.request.Request(url, headers={
            "apikey": SB_KEY, "Authorization": f"Bearer {SB_KEY}"
        })
        try:
            urllib.request.urlopen(req, timeout=5)
            print(f"  ✓ table {table} exists")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"  ✗ table {table} MISSING")
            else:
                body = e.read().decode()[:100]
                print(f"  ? table {table}: {e.code} {body}")
        except Exception as e:
            print(f"  ? table {table}: {e}")


def run_psycopg2():
    """Execute migration via psycopg2."""
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 not installed. Install with: pip install psycopg2-binary")
        return False

    db_password = os.environ.get("SUPABASE_DB_PASSWORD", "")
    if not db_password:
        # Try to read from MORPHEUS .env
        env_file = MORPHEUS_ROOT / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("SUPABASE_DB_PASSWORD="):
                    db_password = line.split("=", 1)[1].strip()

    if not db_password:
        print("No SUPABASE_DB_PASSWORD found.")
        return False

    sql = MIGRATION_FILE.read_text(encoding="utf-8")
    print(f"Connecting to {DB_HOST}:{DB_PORT}/{DB_NAME}...")

    try:
        conn = psycopg2.connect(
            host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
            user=DB_USER, password=db_password,
            sslmode="require"
        )
        conn.autocommit = True
        cur = conn.cursor()

        # Split by statement
        statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]

        for i, stmt in enumerate(statements):
            try:
                cur.execute(stmt + ";")
                print(f"  [{i+1}/{len(statements)}] OK")
            except Exception as e:
                print(f"  [{i+1}/{len(statements)}] WARN: {e}")

        cur.close()
        conn.close()
        print("\n✅ Migration complete!")
        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False


def print_dashboard_instructions():
    """Print instructions for manual execution via Supabase Dashboard."""
    print("\n" + "=" * 60)
    print("MANUAL MIGRATION — Supabase Dashboard SQL Editor")
    print("=" * 60)
    print(f"\n1. Open: https://supabase.com/dashboard/project/{PROJECT_REF}/sql/new")
    print("2. Paste the contents of: sql/migration_002_upearth.sql")
    print("3. Click 'Run' (Ctrl+Enter)")
    print("4. Verify with: python sql/run_migration.py --check")
    print(f"\nFile: {MIGRATION_FILE}")
    print(f"Size: {MIGRATION_FILE.stat().st_size} bytes")
    print(f"Tables created: calendar_events, checkins, proposal_stats, job_hour_stats")
    print(f"Columns added to upwork_jobs: 14 new columns")
    print(f"Views created: v_sniper_jobs, v_proposal_funnel, v_today_checkins, v_week_events")


def main():
    if "--check" in sys.argv:
        check_columns()
        return

    print("mybuilding.dev — Migration 002: UpEarth Ingestion\n")

    # Try psycopg2 first
    if run_psycopg2():
        print("\nVerifying...")
        check_columns()
        return

    # Fallback: instructions
    print_dashboard_instructions()


if __name__ == "__main__":
    main()
