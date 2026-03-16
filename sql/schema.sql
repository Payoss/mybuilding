-- ============================================================
-- mybuilding.dev — Schema Supabase
-- Version : 1.0 — 2026-03-11
-- ============================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- CONTACTS
-- ============================================================
CREATE TABLE contacts (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL,
  email       text,
  phone       text,
  company     text,
  website     text,
  source      text DEFAULT 'direct',
  -- 'upwork' | 'referral' | 'direct' | 'other'
  stage       text DEFAULT 'lead',
  -- 'lead' | 'proposal' | 'active' | 'inactive' | 'churned'
  mrr         numeric DEFAULT 0,
  notes       text,
  tags        text[] DEFAULT '{}',
  avatar_url  text,
  created_at  timestamptz DEFAULT now(),
  updated_at  timestamptz DEFAULT now()
);

-- ============================================================
-- DEALS — Pipeline
-- ============================================================
CREATE TABLE deals (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id  uuid REFERENCES contacts(id) ON DELETE CASCADE,
  title       text NOT NULL,
  description text,
  value       numeric DEFAULT 0,
  value_type  text DEFAULT 'fixed',
  -- 'fixed' | 'monthly' | 'hourly'
  currency    text DEFAULT 'EUR',
  stage       text DEFAULT 'prospect',
  -- 'prospect' | 'proposal' | 'negotiation' | 'active' | 'won' | 'lost' | 'paused'
  probability int DEFAULT 50,
  started_at  date,
  closed_at   date,
  notes       text,
  created_at  timestamptz DEFAULT now(),
  updated_at  timestamptz DEFAULT now()
);

-- ============================================================
-- INVOICES — Factures
-- ============================================================
CREATE SEQUENCE invoice_seq START 1;

CREATE TABLE invoices (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id     uuid REFERENCES contacts(id),
  deal_id        uuid REFERENCES deals(id),
  invoice_number text UNIQUE DEFAULT 'INV-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('invoice_seq')::text, 3, '0'),
  status         text DEFAULT 'draft',
  -- 'draft' | 'sent' | 'viewed' | 'paid' | 'overdue' | 'cancelled'
  line_items     jsonb DEFAULT '[]',
  -- [{label, qty, unit_price, total}]
  subtotal       numeric DEFAULT 0,
  tax_rate       numeric DEFAULT 20,
  tax_amount     numeric DEFAULT 0,
  total          numeric DEFAULT 0,
  currency       text DEFAULT 'EUR',
  due_date       date,
  notes          text,
  created_at     timestamptz DEFAULT now(),
  sent_at        timestamptz,
  paid_at        timestamptz
);

-- ============================================================
-- QUOTES — Devis
-- ============================================================
CREATE SEQUENCE quote_seq START 1;

CREATE TABLE quotes (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id     uuid REFERENCES contacts(id),
  deal_id        uuid REFERENCES deals(id),
  quote_number   text UNIQUE DEFAULT 'DV-' || to_char(now(), 'YYYY') || '-' || lpad(nextval('quote_seq')::text, 3, '0'),
  status         text DEFAULT 'draft',
  -- 'draft' | 'sent' | 'viewed' | 'accepted' | 'declined' | 'expired'
  line_items     jsonb DEFAULT '[]',
  subtotal       numeric DEFAULT 0,
  tax_rate       numeric DEFAULT 20,
  total          numeric DEFAULT 0,
  currency       text DEFAULT 'EUR',
  valid_until    date,
  notes          text,
  converted_to   uuid REFERENCES invoices(id),
  created_at     timestamptz DEFAULT now(),
  sent_at        timestamptz,
  accepted_at    timestamptz
);

-- ============================================================
-- INTERACTIONS — Historique unifié
-- ============================================================
CREATE TABLE interactions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id  uuid REFERENCES contacts(id) ON DELETE CASCADE,
  type        text NOT NULL,
  -- 'note' | 'email' | 'call' | 'meeting'
  -- | 'invoice_sent' | 'invoice_paid' | 'quote_sent' | 'quote_accepted'
  -- | 'deal_won' | 'deal_lost' | 'upwork_applied'
  title       text,
  content     text,
  metadata    jsonb DEFAULT '{}',
  -- {invoice_id, amount, score, ...} selon le type
  created_at  timestamptz DEFAULT now()
);

-- ============================================================
-- UPWORK_JOBS — Analyzer
-- ============================================================
CREATE TABLE upwork_jobs (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title         text NOT NULL,
  description      text,        -- snippet extrait de la liste (300-500 chars)
  description_full text,        -- description complète extraite de la page détail
  client_info   jsonb DEFAULT '{}',
  -- {name, rating, reviews, location, payment_verified, spent_total}
  budget_min    numeric,
  budget_max    numeric,
  budget_type   text DEFAULT 'fixed',
  -- 'fixed' | 'hourly'
  score         int,
  -- 0-100 (Claude analysis)
  analysis      jsonb DEFAULT '{}',
  -- {fit_tech, fit_budget, client_quality, competition,
  --  strengths, red_flags, angle_proposition, verdict}
  keywords_hit  text[] DEFAULT '{}',
  status        text DEFAULT 'new',
  -- 'new' | 'applied' | 'skipped' | 'interviewing' | 'won' | 'lost'
  contact_id    uuid REFERENCES contacts(id),
  -- NULL jusqu'au closing, puis lié au contact créé
  analyzed_at   timestamptz DEFAULT now(),
  applied_at    timestamptz
);

-- ============================================================
-- VIEWS — Métriques calculées
-- ============================================================

-- MRR : retainers actifs
CREATE OR REPLACE VIEW v_mrr AS
  SELECT COALESCE(SUM(value), 0) as mrr
  FROM deals
  WHERE stage = 'active' AND value_type = 'monthly';

-- Pipeline pondéré
CREATE OR REPLACE VIEW v_pipeline AS
  SELECT
    COUNT(*) as deals_count,
    COALESCE(SUM(value), 0) as total_value,
    COALESCE(SUM(value * probability / 100), 0) as weighted_value
  FROM deals
  WHERE stage NOT IN ('won', 'lost');

-- Receivables (factures en attente)
CREATE OR REPLACE VIEW v_receivables AS
  SELECT
    COALESCE(SUM(CASE WHEN status = 'sent' THEN total ELSE 0 END), 0) as sent,
    COALESCE(SUM(CASE WHEN status = 'overdue' THEN total ELSE 0 END), 0) as overdue,
    COALESCE(SUM(CASE WHEN status IN ('sent','overdue') THEN total ELSE 0 END), 0) as total
  FROM invoices;

-- Revenue ce mois
CREATE OR REPLACE VIEW v_revenue_month AS
  SELECT COALESCE(SUM(total), 0) as revenue
  FROM invoices
  WHERE status = 'paid'
    AND paid_at >= date_trunc('month', now());

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX idx_contacts_stage     ON contacts(stage);
CREATE INDEX idx_deals_contact      ON deals(contact_id);
CREATE INDEX idx_deals_stage        ON deals(stage);
CREATE INDEX idx_invoices_contact   ON invoices(contact_id);
CREATE INDEX idx_invoices_status    ON invoices(status);
CREATE INDEX idx_quotes_contact     ON quotes(contact_id);
CREATE INDEX idx_interactions_contact ON interactions(contact_id);
CREATE INDEX idx_upwork_status      ON upwork_jobs(status);
CREATE INDEX idx_upwork_score       ON upwork_jobs(score DESC);

-- ============================================================
-- TRIGGERS — updated_at auto
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER contacts_updated_at BEFORE UPDATE ON contacts
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER deals_updated_at BEFORE UPDATE ON deals
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
