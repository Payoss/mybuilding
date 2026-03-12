-- ============================================================
-- mybuilding.dev — Migration 002 : UpEarth Ingestion
-- 2026-03-12 — Enrichit le schema pour absorber les features UpEarth
-- ============================================================

-- ============================================================
-- UPWORK_JOBS : colonnes manquantes pour scoring UpEarth
-- ============================================================
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS url              text;
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS country          text;
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS posted_at        timestamptz;
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS scraped_at       timestamptz DEFAULT now();
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS feasibility      int;         -- 0-100 (UpEarth style)
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS worth_score      numeric(3,1); -- 0-10 (UpEarth style)
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS sniper_mode      boolean DEFAULT false;
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS is_french        boolean DEFAULT false;
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS time_estimate    text;        -- ex: "4h", "2j"
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS cover_letter     text;
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS cover_letter_b   text;        -- variant B
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS source           text DEFAULT 'manual';
  -- 'manual' | 'extension' | 'rss'
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS proposals_count  int;
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS skills           text[] DEFAULT '{}';
ALTER TABLE upwork_jobs ADD COLUMN IF NOT EXISTS budget_is_placeholder boolean DEFAULT false;

-- Index pour le scoring engine
CREATE INDEX IF NOT EXISTS idx_upwork_feasibility ON upwork_jobs(feasibility DESC);
CREATE INDEX IF NOT EXISTS idx_upwork_worth       ON upwork_jobs(worth_score DESC);
CREATE INDEX IF NOT EXISTS idx_upwork_source      ON upwork_jobs(source);
CREATE INDEX IF NOT EXISTS idx_upwork_posted      ON upwork_jobs(posted_at DESC);

-- ============================================================
-- CALENDAR_EVENTS : calendrier intégré
-- ============================================================
CREATE TABLE IF NOT EXISTS calendar_events (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title       text NOT NULL,
  description text,
  event_date  date NOT NULL,
  event_time  time,
  duration_min int DEFAULT 60,
  type        text DEFAULT 'task',
  -- 'task' | 'meeting' | 'deadline' | 'followup' | 'reminder'
  contact_id  uuid REFERENCES contacts(id) ON DELETE SET NULL,
  deal_id     uuid REFERENCES deals(id) ON DELETE SET NULL,
  status      text DEFAULT 'pending',
  -- 'pending' | 'done' | 'cancelled'
  color       text,  -- override couleur (hex)
  recurrence  text,  -- null | 'daily' | 'weekly' | 'monthly'
  metadata    jsonb DEFAULT '{}',
  created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cal_date    ON calendar_events(event_date);
CREATE INDEX IF NOT EXISTS idx_cal_contact ON calendar_events(contact_id);
CREATE INDEX IF NOT EXISTS idx_cal_status  ON calendar_events(status);

-- ============================================================
-- CHECKINS : daily accountability (inspiré UpEarth)
-- ============================================================
CREATE TABLE IF NOT EXISTS checkins (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id  uuid REFERENCES contacts(id) ON DELETE CASCADE,
  question    text NOT NULL,
  answer      text,
  status      text DEFAULT 'pending',
  -- 'pending' | 'done' | 'skipped'
  due_date    date DEFAULT CURRENT_DATE,
  answered_at timestamptz,
  created_at  timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_checkins_date    ON checkins(due_date);
CREATE INDEX IF NOT EXISTS idx_checkins_contact ON checkins(contact_id);

-- ============================================================
-- PROPOSAL_STATS : analytics cumulées (inspiré UpEarth Memory Bank)
-- ============================================================
CREATE TABLE IF NOT EXISTS proposal_stats (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period       text NOT NULL,          -- '2026-03', '2026-W12'
  period_type  text DEFAULT 'month',   -- 'month' | 'week'
  total_sent   int DEFAULT 0,
  total_views  int DEFAULT 0,
  total_replied int DEFAULT 0,
  total_hired  int DEFAULT 0,
  connects_used int DEFAULT 0,
  best_niche   text,
  best_hour    int,   -- 0-23 heure avec le meilleur taux
  avg_score    numeric(5,2),
  metadata     jsonb DEFAULT '{}',
  -- {by_template: {}, by_keyword: {}, hourly_distribution: []}
  created_at   timestamptz DEFAULT now(),
  UNIQUE(period, period_type)
);

-- ============================================================
-- BEST_HOURS : tracking heure par heure (UpEarth Best Hours)
-- ============================================================
CREATE TABLE IF NOT EXISTS job_hour_stats (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  hour        int NOT NULL CHECK (hour >= 0 AND hour <= 23),
  day_of_week int CHECK (day_of_week >= 0 AND day_of_week <= 6),
  -- 0=Sunday, 6=Saturday
  jobs_count  int DEFAULT 0,
  avg_score   numeric(5,2),
  avg_worth   numeric(3,1),
  gold_count  int DEFAULT 0,  -- sniper/mercer jobs
  updated_at  timestamptz DEFAULT now(),
  UNIQUE(hour, day_of_week)
);

-- ============================================================
-- VIEWS enrichies
-- ============================================================

-- Sniper jobs (gold alerts)
CREATE OR REPLACE VIEW v_sniper_jobs AS
  SELECT *
  FROM upwork_jobs
  WHERE sniper_mode = true
    AND status = 'new'
  ORDER BY posted_at DESC;

-- Proposal conversion funnel
CREATE OR REPLACE VIEW v_proposal_funnel AS
  SELECT
    COUNT(*) FILTER (WHERE status = 'new')          as new_count,
    COUNT(*) FILTER (WHERE status = 'applied')      as applied_count,
    COUNT(*) FILTER (WHERE status = 'interviewing') as interview_count,
    COUNT(*) FILTER (WHERE status = 'won')          as won_count,
    COUNT(*) FILTER (WHERE status = 'lost')         as lost_count,
    COUNT(*) FILTER (WHERE status = 'skipped')      as skipped_count,
    CASE WHEN COUNT(*) FILTER (WHERE status = 'applied') > 0
      THEN ROUND(100.0 * COUNT(*) FILTER (WHERE status IN ('interviewing','won'))
           / COUNT(*) FILTER (WHERE status = 'applied'), 1)
      ELSE 0
    END as response_rate,
    CASE WHEN COUNT(*) FILTER (WHERE status = 'applied') > 0
      THEN ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'won')
           / COUNT(*) FILTER (WHERE status = 'applied'), 1)
      ELSE 0
    END as win_rate
  FROM upwork_jobs;

-- Today's checkins
CREATE OR REPLACE VIEW v_today_checkins AS
  SELECT c.*, ct.name as contact_name
  FROM checkins c
  LEFT JOIN contacts ct ON c.contact_id = ct.id
  WHERE c.due_date = CURRENT_DATE
  ORDER BY c.status, ct.name;

-- This week's calendar
CREATE OR REPLACE VIEW v_week_events AS
  SELECT ce.*, ct.name as contact_name
  FROM calendar_events ce
  LEFT JOIN contacts ct ON ce.contact_id = ct.id
  WHERE ce.event_date >= date_trunc('week', CURRENT_DATE)
    AND ce.event_date < date_trunc('week', CURRENT_DATE) + interval '7 days'
  ORDER BY ce.event_date, ce.event_time;
