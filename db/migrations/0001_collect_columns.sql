-- M1: G2B 수집을 위한 bid_pipeline 컬럼 확장.
--
-- 기존 단일 PK `notice_no`는 유지. abb-bid-pipeline의 (bid_no, bid_seq) 복합키는
-- `notice_no = f"{bid_no}-{bid_seq}"` 규칙으로 합성된 뒤 별도 컬럼에도 분해 저장.
--
-- 기존 db/bid_pipeline_schema.sql을 먼저 적용한 환경에서 ALTER 한다.

ALTER TABLE bid_pipeline
  ADD COLUMN IF NOT EXISTS bid_no       TEXT,
  ADD COLUMN IF NOT EXISTS bid_seq      TEXT,
  ADD COLUMN IF NOT EXISTS bid_type     TEXT,
  ADD COLUMN IF NOT EXISTS org_code     TEXT,
  ADD COLUMN IF NOT EXISTS org_name     TEXT,
  ADD COLUMN IF NOT EXISTS base_price   NUMERIC(18, 2),
  ADD COLUMN IF NOT EXISTS open_date    TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS close_date   TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS collected_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS bid_pipeline_bid_type_idx   ON bid_pipeline (bid_type);
CREATE INDEX IF NOT EXISTS bid_pipeline_org_code_idx   ON bid_pipeline (org_code);
CREATE INDEX IF NOT EXISTS bid_pipeline_close_date_idx ON bid_pipeline (close_date);
