-- Phase 1 MVP schema: bid_pipeline status machine

CREATE TABLE IF NOT EXISTS bid_pipeline (
  notice_no TEXT PRIMARY KEY,
  title TEXT,
  source TEXT,
  raw JSONB,

  category TEXT NOT NULL DEFAULT '비관련',
  fit_score INTEGER NOT NULL DEFAULT 0 CHECK (fit_score >= 0 AND fit_score <= 100),
  assignee TEXT NOT NULL DEFAULT '미배정',
  analysis JSONB NOT NULL DEFAULT '{}'::jsonb,
  status TEXT NOT NULL DEFAULT 'collected',

  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS bid_pipeline_status_idx ON bid_pipeline (status);
CREATE INDEX IF NOT EXISTS bid_pipeline_fit_score_idx ON bid_pipeline (fit_score);
CREATE INDEX IF NOT EXISTS bid_pipeline_updated_at_idx ON bid_pipeline (updated_at);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS bid_pipeline_set_updated_at ON bid_pipeline;
CREATE TRIGGER bid_pipeline_set_updated_at
BEFORE UPDATE ON bid_pipeline
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

