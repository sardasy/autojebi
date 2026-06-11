# M13 G2B 라이브 검색 — 실 PostgreSQL e2e (2026-06-07)

이전 [search_e2e_20260606.md](search_e2e_20260606.md)는 SQLite 우회 검증이었다. .env DATABASE_URL을 실 컨테이너 (autojebi-postgres:5434)에 맞추고 `alembic upgrade head` + `python -m api.ontology seed` 완료 후 동일 시나리오 재실측.

백엔드: 로컬 `uvicorn api.main:app --port 8005`, DB는 docker `autojebi-postgres` (autojebi/autojebi@localhost:5434/autojebi).
G2B 키: `.env`의 `DATA_GO_KR_API_KEY`.

| 시나리오 | 요청 | 응답 시간 | status | total | total_pages | page | items | 첫 항목 | 비고 |
|---|---|---|---|---|---|---|---|---|---|
| S1 좁은 키워드 | `ABB 차단기`, ±30일, page=1/page_size=50 | 10.8s | 200 | 0 | 0 | 1 | 0 | (empty) | 메타 정상 |
| S2 넓은 키워드 page=1 | `전력`, 60일, page=1/page_size=50 | 13.0s | 200 | 116 | 3 | 1 | 50 | R26BK01507766-000 | |
| S3 page=2 | 동일, page=2 | 11.4s | 200 | 116 | 3 | 2 | 50 | R26BK01511254-000 | S2와 다름 ✓ |
| S4 page=3 (last) | 동일, page=3 | 9.0s | 200 | 116 | 3 | 3 | 16 | R26BK01556178-000 | 50+50+16=116 ✓ |
| S5 page=999 (beyond) | 동일, page=999 | 8.5s | 200 | 116 | 3 | 999 | 0 | (empty) | 422 아닌 정상 응답 |
| S6 upsert → 재검색 | S2 첫 항목 저장 후 page_size=1로 재검색 | — | 200/200 | 116 | 116 | 1 | 1 | R26BK01507766-000 | `already_exists` False → True ✓ |

## SQLite 우회 결과와 일관성

| 메트릭 | SQLite (20260606) | PostgreSQL (20260607) | 일관성 |
|---|---|---|---|
| S2 total | 116 | 116 | ✓ |
| S2 first | R26BK01507766-000 | R26BK01507766-000 | ✓ |
| S3 first | R26BK01511254-000 | R26BK01511254-000 | ✓ |
| S4 items | 16 | 16 | ✓ |
| upsert 토글 | ✓ | ✓ | ✓ |

응답 시간은 PG가 약간 느림 (전 시나리오 평균 9~13s vs SQLite 4~6s) — 첫 호출에 콜드 캐시·네트워크 라운드트립 영향. 페이지네이션·dedup·G2B 병렬 페치 로직 자체는 동일.

## 결론

- 실 PostgreSQL 운영 환경에서 M13 라이브 검색·페이지네이션·upsert 토글 전부 정상.
- `0003_ontology` 마이그레이션 적용 후에도 기존 `bid_pipeline` 동작 회귀 없음.
- M13 코드의 dialect-agnostic 설계가 PG/SQLite 양쪽에서 동일 결과 보장 확인.

## 부수

- 컨테이너 `autojebi-api`는 6/5 이전 빌드라 자동 alembic 부팅이 실패 중이었음. 이 1차 e2e는 로컬 `uvicorn --port 8005`로 검증.
- **6/7 후속**: `docker compose build api && docker compose --env-file .env up -d api`로 이미지 재빌드 후 컨테이너 측(`http://localhost:8001`)에서 동일 6 시나리오 재실측 → totals/total_pages/items/first 모두 1차와 정확히 일치. 컨테이너 동선 정상 회복.
- IPv4 localhost(`127.0.0.1`)에 stale 좀비 소켓(PID 5256)이 남아 있어 PowerShell 호출은 `[::1]`(IPv6)로 우회 — 추후 OS 재기동 시 자연 해소.
