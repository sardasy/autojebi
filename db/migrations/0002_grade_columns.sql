-- M3: 3축 그레이딩 + SKU 매칭 결과를 위한 bid_pipeline 컬럼 확장.
--
-- score_total은 analysis JSONB의 'grade.breakdown.total'을 위로 끌어올린 인덱싱용.
-- fit_score는 grade 엔드포인트에서 int(score_total*100)으로 동기화된다.
--
-- 기존 db/bid_pipeline_schema.sql + 0001_collect_columns.sql 적용된 환경에서 ALTER 한다.

ALTER TABLE bid_pipeline
  ADD COLUMN IF NOT EXISTS score_spec      NUMERIC(4, 3),
  ADD COLUMN IF NOT EXISTS score_qual      NUMERIC(4, 3),
  ADD COLUMN IF NOT EXISTS score_price     NUMERIC(4, 3),
  ADD COLUMN IF NOT EXISTS score_total     NUMERIC(4, 3),
  ADD COLUMN IF NOT EXISTS grade_reason    TEXT,
  ADD COLUMN IF NOT EXISTS risk_note       TEXT,
  ADD COLUMN IF NOT EXISTS top_sku         TEXT,
  ADD COLUMN IF NOT EXISTS top_sku_name    TEXT,
  ADD COLUMN IF NOT EXISTS sku_match_score NUMERIC(4, 3),
  ADD COLUMN IF NOT EXISTS graded_at       TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS bid_pipeline_score_total_idx ON bid_pipeline (score_total DESC);
CREATE INDEX IF NOT EXISTS bid_pipeline_top_sku_idx     ON bid_pipeline (top_sku);
