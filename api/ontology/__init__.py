"""M14 — 입찰업무 온톨로지 레이어 (Stage 1: 스키마 + 통제어휘 시드 + 읽기 API).

서브모듈:
  - tables: SQLAlchemy Core Table 8개 + 별도 MetaData.
  - seed:   초기 통제어휘 시드 함수와 데이터 상수 (멱등 upsert).

CLI:
  python -m api.ontology seed            # 시드 upsert (멱등)
  python -m api.ontology seed --dry-run  # 변경 없이 SeedReport만 출력
"""
