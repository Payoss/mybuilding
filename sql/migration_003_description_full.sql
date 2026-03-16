-- Migration 003 — Add description_full column to upwork_jobs
-- Run in Supabase SQL Editor
-- 2026-03-16

ALTER TABLE upwork_jobs
  ADD COLUMN IF NOT EXISTS description_full text;

COMMENT ON COLUMN upwork_jobs.description_full IS
  'Full job description scraped from detail page (/jobs/~XXX). '
  'Populated automatically when user opens a job on Upwork. '
  'Takes priority over description (snippet from search list) for LLM enrichment.';
