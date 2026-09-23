# autojebi — 미림씨스콘 입찰 자동화

**2026-09-09 OpenAI 실호출:** 독립 가상 공고에서 `gpt-4.1-mini` 원문 분석·제안서 생성 각 1회가 성공했다. 비교 초안 저장, 누락 검사, Excel/검토 패키지 다운로드와 파일 검증을 완료했다. HWP 템플릿·필수값이 없어 HWP 생성 및 실공고 제출 준비 완료는 미검증이다. [실제 E2E 결과](docs/openai-live-e2e-2026-09-09.md), [구현 및 설정](docs/openai-test-readiness-2026-09-09.md).

**2026-09-09 Gemini 실호출:** 사용자 승인 키로 실제 공고 분석 2회를 실행했으나 미완료 응답/공급자 오류로 실패했다. 기존 자료는 보존했고 Excel 다운로드·경고 검토 패키지를 확인했다. 전체 실연동 통과가 아니다. [실제 버튼 E2E 결과 및 남은 조건](docs/gemini-live-e2e-2026-09-09.md).

**2026-09-09 Gemini 추가:** v2 작업대의 원문 분석·근거 기반 제안서 생성에 `WORKSPACE_LLM_PROVIDER=gemini`를 지원한다. `/v2/settings`는 선택 공급자·모델·키 등록 여부를 반환하며 실제 연결 성공과 구분한다. 기존 API는 Claude를 유지한다. [설정 방법 및 검증 범위](docs/gemini-workspace-2026-09-09.md). 실제 Google 호출은 아직 검증하지 않았다.

**2026-09-08 HWP 검사 작업:** v2 jobs에 `hwp_inspect`를 추가했다. 템플릿 필드 조회를 영속 큐로 실행하고 파일/매핑 해시에 연결한다. 제안서 전체 본문 필수 매핑과 생성 전 실제 필드 대조를 추가했다. [실행 결과와 복구 대기 사항](docs/hwp-template-recovery-progress-2026-09-08.md). 실제 HWP 템플릿 제작과 배치 검증은 미완료다.

**2026-09-08 필수조건 점검:** `/v2/notices/{notice_no}/prerequisites`와 작업대 점검 패널을 추가했다. 자격·증빙, 템플릿 파일, Worker 인증·복구 조건을 구분하고 미충족 HWP 요청을 차단한다. [구현 및 실제 버튼 검증](docs/workspace-prerequisites-2026-09-08.md). 조건 점검 통과는 제출 준비 승인이나 실제 HWP 배치 검증을 의미하지 않는다.

**2026-09-08 실제 PLECS 공고 준비:** 신규 공고 원본 2개, 인용 기반 확인 항목 18개, 경고 상태의 Excel/검토 패키지를 확보했다. 검색 마감 필터와 서버 제출 준비 마감 검증을 추가했다. [준비 기록과 미완료 조건](docs/plecs-R26BK01706511-preparation-2026-09-08.md)을 참고한다. 실제 참가 승인·최종 서류·HWP 검증은 미완료다.

**2026-09-08 작업대 개선:** 원문 PDF·요구사항 나란히 보기, 기존 작성자료 수치 비교, 초안 저장·승인·반려 분리, 변경 없는 본문 재추출 시 검토 보존을 적용했다. PDF 페이지 API와 실제 테스트 결과는 [UX 개선 검증 기록](docs/document-workbench-ux-2026-09-08.md)을 참고한다. HWP 실파일 검증 및 운영 전환은 아직 완료되지 않았다.

**2026-09-07 동선 축소:** 검증 환경은 **공고 찾기 → 공고 서류 검토 → 기존 작성자료와 비교·작성 → 서류 확인**만 기본 동선으로 사용한다. 기존 작성자료는 증빙과 분리하며, 비교 초안 API와 검증 결과는 [서류 작성 루프](docs/document-loop-2026-09-07.md)를 참고한다. 아래의 그레이딩·알림 등은 기존 기능 설명이며 새 기본 화면에서는 제공하지 않는다.

> **2026-09-06: 실무용 v2 검증 중, 운영 전환 미완료.** `/workspace`는 독립 작업 큐·원문 근거·사람 검토를 사용하는 새 작업대다. 기존 완료 표기는 기능 구현 이력이며 실제 공고 3건/HWP 실파일 검증 완료를 뜻하지 않는다. 실행 방법, API, 제한과 검증 결과는 [v2 구현 및 전환 기록](docs/workspace-v2-implementation.md)을 따른다.

2026-09-07 실공고 보완: XLS/ZIP 첨부의 조용한 누락을 제거하고 전체 첨부 목록·원본 보관·미확인 차단·수동 변환본 연결을 추가했다. [실제 공고 리허설 결과](docs/real-rehearsal-2026-09-07.md)를 참고한다. HWP 실제 생성 및 운영 전환은 별도 미완료 조건이다.

G2B(나라장터)·KJEBI 메일로 들어오는 전력기기 입찰공고를 실시간 검색/등록 → Claude 분석 → 3축 그레이딩 → Slack/Teams 알림 → HWP 입찰양식 자동 작성 → 서류 체크리스트/업로드/Excel·HWP 내보내기까지 한 파이프라인으로 처리한다. M1~M11·M13 마일스톤 완료, M14(HWP 제안서)·v2 작업대는 구현 후 운영 전환 검증 중 (FastAPI + PostgreSQL + Next.js 15 + Qdrant + in-repo HWP Worker). 현재 상태와 잔여 조건은 [AGENTS.md](AGENTS.md) §1 마일스톤 표를 따른다.

이 문서는 **신규 유저(영업·검토자·운영자) 매뉴얼** + **API 레퍼런스**다.

## 목차

1. [한눈에 보기](#1-한눈에-보기)
2. [빠른 시작](#2-빠른-시작)
3. [시스템 구성](#3-시스템-구성)
4. [상태머신 — 공고의 일생](#4-상태머신--공고의-일생)
5. [자동화 vs 수동](#5-자동화-vs-수동)
6. [화면 사용법 (Next.js 콘솔)](#6-화면-사용법-nextjs-콘솔)
7. [API / CLI 레퍼런스](#7-api--cli-레퍼런스)
8. [점수 체계 — 3축 그레이딩](#8-점수-체계--3축-그레이딩)
9. [HWP 양식 자동 작성](#9-hwp-양식-자동-작성)
10. [운영](#10-운영)
11. [환경변수 레퍼런스](#11-환경변수-레퍼런스)
12. [인증 (M9)](#12-인증-m9)
13. [트러블슈팅](#13-트러블슈팅)
14. [핵심 파일 맵](#14-핵심-파일-맵)

---

## 1. 한눈에 보기

### 무엇을 해주는가
- G2B에서 키워드 매칭 공고를 실시간 검색하고, 사용자가 확인한 건만 저장 (`POST /notices/search` → `POST /notices/upsert`)
- 공고 제목 + G2B 첫 첨부(HWP/PDF)를 Claude로 분석해 **전기 사양(ElecSpec)** 추출 → 카테고리·담당자 자동 라우팅
- ABB SKU 카탈로그(Qdrant)와 임베딩 매칭 → 3축(사양·자격·예가) 그레이딩 → 0.6 이상 자동 Slack 알림
- 적합 공고는 [milim-hwp-agent](../../Desktop/milim-hwp-agent)에 위임해 HWP 입찰양식의 회사정보/공고메타 placeholder 자동 채움
- 사용자는 Next.js 콘솔(`/notices`, `/notices/[noticeNo]`, `/admin`)에서 조회·트리거·상태 확정

### 토폴로지
```
KJEBI 메일 (콘솔 /admin 수동 upsert만 지원, n8n 자동화는 placeholder) / 나라장터 OpenAPI (data.go.kr)
            │
            ▼
   autojebi (FastAPI + Postgres + Qdrant)   ──HTTP──▶  milim-hwp-agent (Windows + HWP COM)
   • bid_pipeline 상태머신                              • /bid-form/autofill
   • Claude tool-use 분석 / 3축 그레이딩                • /document/analyze-file
   • Slack / Teams 알림                                 • /rag/search (FTS5 BM25)
   • Next.js 콘솔 (조회 + 액션 + 어드민)
```

autojebi는 OS-무관한 **중앙 파이프라인 서버**, milim-hwp-agent는 **Windows 데스크톱 로컬 에이전트**(HWP COM 필요).

### 마일스톤 (M1~M14)
| M# | 영역 | 핵심 산출물 |
|----|------|------------|
| M1 | 수집 | G2B OpenAPI 클라이언트, 실시간 검색/사용자 저장, `POST /notices/search`, `POST /notices/upsert` |
| M2 | 분석 | Claude tool-use(ElecSpec 추출), G2B 첫 첨부 자동 다운, 카테고리 라우팅 |
| M3 | 그레이딩 기반 | 3축 점수 컬럼, Qdrant SKU 인제스트(`POST /skus/ingest`), Slack 알림 |
| M4 | 알림+양식 | Teams 알림(`/notify`), HWP autofill(`/autofill-form`), 상태머신 |
| M5 | 라이브 자격 | G2B 자격 API(라이브 호출) + 자동 grade 스케줄러(30분) |
| M6 | 캐싱 | 자격 API 응답 in-memory 24h 캐시 |
| M7 | 프론트 | Next.js 15 콘솔, CORS, server-side fetch |
| M8 | UI 일원화 | Streamlit 제거, 모든 액션 Server Action으로 통합, `/admin` 추가 |
| M9 | 보안 | API 키 인증 (`X-API-Key`), 프론트 server-side 주입 |
| M10 | 서류 자동화 v1 | 룰+LLM 체크리스트, 초안(기술대응표·요약·HWP 보강), 제출 전 검증 (`POST /notices/{notice_no}/documents/analyze` 외) |
| M11 | 서류 자동화 v2 | 파일 업로드/삭제/다운로드, Excel·HWP 내보내기 (`POST /notices/{notice_no}/documents/uploads`, `.../exports/{kind}`) |
| M13 | G2B 라이브 검색 | `POST /notices/search` 페이지네이션(`page`/`page_size`/`total_pages`), 등록 전 `already_exists` 확인, 5엔드포인트×30일윈도우 병렬 페치 |
| M14 (Stage 1) | 온톨로지 기반 | `0003_ontology` 마이그레이션 8 테이블 + `GET /ontology/*` 읽기 API + 통제어휘 시드(`python -m api.ontology seed`) |
| M14 (Stage 2) | HWP 제안서 자동 생성 | 공고 메타·규격 항목·서류 분석·SKU 추천을 모아 필드 매핑 기반 `POST /document/put-fields`로 HWP 제안서 작성 |

---

## 2. 빠른 시작

### 풀스택 docker-compose (권장)

```bash
cp .env.example .env   # ANTHROPIC_API_KEY, DATA_GO_KR_API_KEY 등 채움
docker compose --env-file .env -f infra/docker-compose.yml up -d
# `--env-file .env`는 compose 변수 치환(${DATA_GO_KR_API_KEY:-} 등)에 필요
# → Postgres + Qdrant + autojebi API + Next.js 프론트 동시 기동
# → API 컨테이너 부팅 시 `alembic upgrade head` 자동 실행 (0001→…→0003_ontology)

curl http://localhost:8001/healthz
# → {"ok": true, "checks": {"db": "ok"}}

# (M14) 통제어휘 시드 (멱등 — 신규 환경 1회)
python -m api.ontology seed
```

기본 포트 (docker-compose.override.yml 기준):
- API: `http://localhost:8001`
- 콘솔: `http://localhost:3001` (compose 외부) / `http://localhost:3000` (dev 서버)
- Postgres: `localhost:5434` (override 포트 — 5433 충돌 회피)
- Qdrant: `localhost:6333`

> 포트가 이미 다른 컨테이너에 점유돼 있다면 [§ 10 운영 / 포트 충돌](#포트-충돌-override) 참고. `infra/docker-compose.override.yml`이 dev 표준이고 5434를 사용. base 매핑(5433)으로 돌리려면 override 파일을 비활성화.

### 로컬 개발 (도커 없이)

```bash
# 의존성
pip install -e ".[dev]"

# DB 마이그레이션
export DATABASE_URL=postgresql+psycopg://autojebi:autojebi@localhost:5434/autojebi
alembic upgrade head
# 기존 운영 DB(raw SQL로 셋업된 경우): alembic stamp head

# M14 통제어휘 시드 (멱등 — 신규 환경 부트스트랩 시 1회)
python -m api.ontology seed

# API (스케줄러 자동 시작 — SCHEDULER_ENABLED=false 로 끌 수 있음)
uvicorn api.main:app --reload --port 8001

# 프론트
cd frontend && npm install && npm run dev   # :3000

# 테스트
python -m pytest -v        # 백엔드 262 tests (인증 8개 포함)
# (호스트에 typhoon HIL 등 외부 pytest 플러그인이 깔려 있어 collection이 막히면:
#  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -v)
cd frontend && npm test    # Vitest 단위
# Playwright e2e — docker 풀스택 선행 + override 표준 포트(:3001)
cd frontend && E2E_BASE_URL=http://localhost:3001 E2E_API_BASE=http://localhost:8001 \
  E2E_API_KEY="${API_KEY:-}" npm run e2e

# Windows 로컬에서 기존 3000/8001 프로그램을 유지한 채 E2E만 분리 실행
# 1) 새 Postgres DB에 alembic upgrade head
# 2) python -m api.ontology seed && python -m api.hwp_fields seed
# 3) API=:8002, frontend=:3002로 실행
# 4) cd frontend; $env:E2E_BASE_URL='http://127.0.0.1:3002'; $env:E2E_API_BASE='http://127.0.0.1:8002'; npm run e2e

# 운영 근접 live smoke — 실제 G2B/Claude/Qdrant/HWP agent 준비 시에만 opt-in
cd frontend && E2E_OPS_LIVE=1 E2E_BASE_URL=http://localhost:3001 E2E_API_BASE=http://localhost:8001 \
  E2E_API_KEY="${API_KEY:-}" npm run e2e -- --project=chromium-ops-live
```

> **HWP 서류 처리(에이전트 연동) 권장 구성**: HWP 에이전트는 Windows 데스크톱 로컬 프로세스라
> 컨테이너에서 파일 경로가 어긋난다. 따라서 **API는 호스트에서 실행**(`uvicorn api.main:app --host 0.0.0.0 --port 8001`),
> Postgres/Qdrant만 Docker로 둔다(`HWP_AGENT_BASE_URL=http://127.0.0.1:8000`).
> 이때 `UPLOAD_DIR`/`EXPORT_DIR`는 **Docker 바인드마운트가 아닌 별도 호스트 폴더**(예
> `C:\Users\<you>\autojebi-data\uploads`)로 지정한다. 리포의 `data\uploads`는 compose의
> 바인드마운트 대상이라 Docker Desktop이 디렉터리를 점유해 **호스트 프로세스의 새 파일 쓰기가
> `[Errno 2] No such file or directory`로 실패**할 수 있다(읽기/목록은 됨). 별도 폴더면 호스트 API가
> 자유롭게 쓰고, 같은 호스트의 에이전트가 그 경로를 그대로 열 수 있다.
> 프론트엔드를 **Docker로 유지**한 채 호스트 API를 쓰려면 `frontend` 서비스에
> `INTERNAL_API_BASE=http://host.docker.internal:8001` + `extra_hosts: host.docker.internal:host-gateway`를
> 설정한다(이미 `infra/docker-compose.override.yml`에 반영됨).

---

## 3. 시스템 구성

### 백엔드 (FastAPI, :8001)
- 엔트리: [api/main.py](api/main.py) — 라이프스팬에서 스케줄러 start/stop, CORS 미들웨어, `/healthz`
- 라우터: [api/routers/notices.py](api/routers/notices.py), [api/routers/skus.py](api/routers/skus.py), [api/routers/ontology.py](api/routers/ontology.py)
- 모든 라우터에 `Depends(verify_api_key)` 적용 ([api/auth.py](api/auth.py)) — `API_KEY` 빈값이면 인증 비활성

### 프론트엔드 (Next.js 15, :3000)
- App Router (`frontend/src/app/`)
- 페이지: [`/notices`](frontend/src/app/notices/page.tsx), [`/notices/[noticeNo]`](frontend/src/app/notices/[noticeNo]/page.tsx), [`/admin`](frontend/src/app/admin/page.tsx)
- Server Action으로 모든 API 호출 ([frontend/src/lib/actions.ts](frontend/src/lib/actions.ts))
- API 클라이언트: [frontend/src/lib/api.ts](frontend/src/lib/api.ts) (서버에서 `INTERNAL_API_KEY` server-side 주입)

### 데이터베이스 (PostgreSQL 16)
- 단일 테이블 `bid_pipeline` ([db/bid_pipeline_schema.sql](db/bid_pipeline_schema.sql), [db/migrations/](db/migrations/))
- PK: `notice_no` (형식 `{bid_no}-{bid_seq}`)
- 마이그레이션 도구: Alembic ([alembic/](alembic/))

### Qdrant
- 컬렉션: `abb_skus` (기본, `QDRANT_COLLECTION_NAME` 변경 가능)
- ABB SKU 카탈로그 임베딩 인덱스 — grade 단계에서 ElecSpec → 유사 SKU 매칭에 사용
- 미가동이어도 grade는 spec=0.0으로 silent fallback (전체는 계속 동작)

### 외부 의존
| 시스템 | 역할 | 인증 변수 | 미가동 시 동작 |
|--------|------|----------|---------------|
| Claude API (Anthropic) | 사양 추출 + 적합 사유 요약 | `ANTHROPIC_API_KEY` | 분석 단계 실패 → category=비관련, fit_score=0 |
| data.go.kr (G2B OpenAPI) | 공고 수집 + 자격 API | `DATA_GO_KR_API_KEY` | 수집 0건 / 자격 점수 raw_json 휴리스틱 폴백 |
| Qdrant | SKU 벡터 매칭 | `QDRANT_API_KEY` (선택) | spec=0.0 silent fallback |
| Slack | 적합공고 자동 알림 | `SLACK_WEBHOOK_URL` | 발송 안 함 (grade는 정상) |
| Teams | `/notify` 액션 알림 | `TEAMS_WEBHOOK_URL` | dry-run으로 상태만 전이 |
| milim-hwp-agent | HWP 양식 자동 입력 | `HWP_AGENT_TOKEN` (선택) | `/autofill-form` 호출 실패 → HTTPException |

---

## 4. 상태머신 — 공고의 일생

[api/services/status.py:4-32](api/services/status.py) — `FINAL_STATUSES`, `can_transition`, `compute_notify_status`.

API 식별자와 route의 정합성 기준은 [docs/api-spec-v0.2.md](docs/api-spec-v0.2.md)를 따른다. 공고 path parameter는 `notice_no`만 사용한다.

```
(없음)
   │ POST /notices/search 확인 후 /notices/upsert
   ▼
collected ──────────────┐
   │ POST /notices/{notice_no}/analyze
   ▼
analyzed ──────────────┐
   │ attachments/documents/spec/HWP   │ POST /notify (또는 fit_score 기반 자동)
   ▼                                  │
attachments_fetched → documents_analyzed → spec_extracted → hwp_composed
   │
   ▼
form_filled ───────────────────────► (분기)
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
        notified                 digest_queued               archived_low
       (fit ≥ 70)                (40 ≤ fit < 70)              (fit < 40)
       FINAL — read-only         FINAL — read-only           FINAL — read-only
```

### 전이 규칙 (요약)
| from | 허용 to |
|------|---------|
| (없음) | `collected` |
| `collected` | `analyzed` |
| `analyzed` | `attachments_fetched`, `documents_analyzed`, `spec_extracted`, `hwp_composed`, `form_filled`, FINAL 3종 |
| `attachments_fetched` | 이후 처리 상태 또는 FINAL 3종 |
| `documents_analyzed` | 이후 처리 상태 또는 FINAL 3종 |
| `spec_extracted` | `hwp_composed`, `form_filled`, FINAL 3종 |
| `hwp_composed` | `form_filled`, FINAL 3종 |
| `form_filled` | FINAL 3종 |
| FINAL 3종 | (전이 불가) |

### 자동 분기 임계치 ([status.py:11-16](api/services/status.py))
- `fit_score ≥ 70` → `notified` (즉시 연락)
- `40 ≤ fit_score < 70` → `digest_queued` (주간 다이제스트 대기)
- `fit_score < 40` → `archived_low` (보관, 수동 검토 가능)

> 상태 다운그레이드 금지 — G2B 검색 결과를 다시 저장해도 `analyzed`/`form_filled`/FINAL은 유지된다 ([collector/pipeline.py](api/collector/pipeline.py)).

---

## 5. 자동화 vs 수동

### 스케줄러가 자동으로 하는 일 ([api/collector/scheduler.py](api/collector/scheduler.py))

| 잡 | 기본 스케줄 | 끄는 법 |
|----|-----------|--------|
| **자동 그레이딩 배치** | 30분 간격, `analyzed` & `graded_at IS NULL` 공고 최대 50건 | `SCHEDULER_GRADE_ENABLED=false` 또는 `GRADE_INTERVAL_MINUTES=0` |
| **자동 Slack 알림** | grade 결과 `score_total ≥ 0.6` 시 (`GRADE_ALERT_THRESHOLD`) | `SLACK_WEBHOOK_URL` 빈값 |
| **자격 API 24h 캐시** | grade 중 자동 (`QUAL_CACHE_TTL_HOURS=24`) | `QUAL_CACHE_ENABLED=false` |

### 유저가 수동 트리거하는 일
| 작업 | 어디서 | 언제 |
|------|--------|------|
| G2B 신규 검색/저장 | 콘솔 `/notices?mode=g2b` 또는 `POST /notices/search` 후 `POST /notices/upsert` | 특정 키워드/기간의 공고를 확인하고 저장할 때 |
| 단건 Claude 분석 | 콘솔 공고 상세 [분석] | `collected` 공고를 즉시 분석 |
| 단건 그레이딩 | 콘솔 공고 상세 [Grade] | 스케줄러 대기 싫을 때, 단건 평가 |
| Teams 알림 발송 | 콘솔 공고 상세 [Notify] | 의사결정 후 최종 상태 확정 |
| G2B 첨부 가져오기 | 콘솔 공고 상세 [첨부 서류 가져오기] | 저장된 G2B raw 첨부 PDF/HWP/HWPX를 내려받아 서류 준비 목록에 연결 |
| HWP 양식 자동 작성 | 콘솔 공고 상세 [HWP Autofill] | 입찰 준비 단계 |
| KJEBI 수동 등록 | 콘솔 `/admin` → 공고 수동 Upsert | 메일 시스템 미연동 또는 보강 |
| SKU 카탈로그 인제스트 | 콘솔 `/admin` → SKU 인제스트 | 초기 셋업, ABB 라인 갱신 |

---

## 6. 화면 사용법 (Next.js 콘솔)

### `/notices` — 공고 목록 ([page.tsx](frontend/src/app/notices/page.tsx))

상단 동선:
- **G2B 실시간 검색** (`/notices?mode=g2b`) → 나라장터 OpenAPI를 즉시 조회하고, 필요한 공고만 저장

검색·필터 (M-search) — [NoticeFilterBar.tsx](frontend/src/components/NoticeFilterBar.tsx):
- **통합 검색** (`q`): 제목·공고번호·기관·담당자·카테고리·추천SKU·grade_reason·risk_note에 부분일치(대소문자 무시). 검색어·비교 대상 양쪽 모두 공백 제거 후 매칭 — 띄어쓰기 변형 무시(예: q `제어기시험장치` ↔ title `제 어기시험장치`)
- **진행 상태** (`lifecycle`): `active`(마감 전 또는 미확인 — **첫 진입 시 기본값**) / `closed` / `unknown` / `all`
- **상태 다중** (`status`): 수집/분석/첨부/서류/규격/HWP/완료/final 상태 체크박스 칩
- **마감 기간** (`close_from`/`close_to`)
- **정렬** (`sort`/`direction`): `close_date` / `updated_at` / `base_price` / `fit_score` / `score_total` × asc·desc. 기본 = 마감일 오름차순(NULL 뒤), 동률은 `updated_at desc`
- **고급 패널** — "▶ 고급 필터" 클릭 시 펼침:
  - 카테고리·공고유형·출처 다중 선택
  - 기관명 부분일치, 담당자 정확일치
  - 개시·마감 기간, 예가 범위, 적합도(0~100) 범위, 종합 점수(0~1) 범위
  - 존재 조건 — `has_grade`, `has_documents`, `has_uploads`, `ready_for_submission` 각 3-state (전체/있음/없음)
- **페이지네이션**: `page` / `page_size` (기본 20, 최대 100). 상·하단 양쪽에 표시, 페이지 이동 시 다른 모든 조건 유지
- **URL 보존**: 모든 조건이 `?status=a&status=b&q=…` 형태 쿼리스트링으로 보존 — 새로고침/링크 공유/뒤로가기 안전
- **전체 초기화**: 오른쪽 상단 "전체 초기화" 링크 (`/notices`로 이동)

테이블 컬럼:
| 컬럼 | 의미 |
|------|------|
| 종합 | `score_total` (0~1) — 3축 가중합 |
| 적합도 | `fit_score` (0~100) — `int(score_total*100)` |
| 제목 | 클릭하면 상세로 이동 |
| 카테고리 | HIL / SW / IGBT / SCR / 수동소자 / ABB장비 / 혼합 / 비관련 |
| 기관 | `org_name` |
| 예가 | `base_price` (G2B presmptPrce 또는 asignBdgtAmt) |
| 마감 | `close_date` |
| 추천SKU | `top_sku_name` (Qdrant 최상위) |
| 담당자 | `assignee` (카테고리 라우팅 결과 — [§ 8 점수 체계](#담당자-라우팅) 참고) |
| 상태 | StatusBadge |
| 업데이트 | `updated_at` |

배지 색 ([components/StatusBadge.tsx:10-26](frontend/src/components/StatusBadge.tsx)):
- 수집(slate) → 분석(cyan) → 양식(indigo) → 알림(emerald/초록=강조) / 다이제스트(amber) / 보류(slate-800)

### `/notices/[noticeNo]` — 공고 상세 ([page.tsx](frontend/src/app/notices/[noticeNo]/page.tsx))

상단: 공고 메타(기관·예가·마감·G2B 원문 링크) + 3축 점수 분해 + StatusBadge.

액션 바 ([components/NoticeActionsBar.tsx](frontend/src/components/NoticeActionsBar.tsx)) — 4개 버튼:

1. **분석** (`status==collected`일 때만 활성) → `POST /notices/{notice_no}/analyze`
   - Claude tool-use로 ElecSpec 추출 + 첫 첨부 자동 다운(`LLM_ATTACHMENT_FETCH=true`)
   - 응답: `{ category, fit_score, assignee, analysis, status }`
   - 상태: `collected → analyzed`

2. **Grade** (`status` ∈ {`analyzed`, `form_filled`}일 때) → 모달에서 "Slack 알림" 체크박스 선택 후 → `POST /notices/{notice_no}/grade`
   - 요청: `{ alert: true|false }`
   - 응답: `{ score_spec, score_qual, score_price, score_total, top_sku, top_sku_name, grade_reason, risk_note, slack_delivered, status }`
   - 상태: 변경 없음 (점수만 갱신, `fit_score = int(score_total*100)` 동기화)

3. **Notify** (`status` ∈ {`analyzed`, `form_filled`}) → 모달에서 "dry_run" 선택 후 → `POST /notices/{notice_no}/notify`
   - 요청: `{ dry_run: true|false }`
   - 응답: `{ status, delivered }`
   - 상태: `fit_score` 기준 자동 분기 ([§ 4 자동 분기 임계치](#자동-분기-임계치))

4. **HWP 작성** → 규격 대응 탭에서 템플릿 선택, 입력값 확인 후 수동 실행 → `POST /notices/{notice_no}/documents/hwp-compose`
   - JSON/파일 경로는 고급 설정에 있으며 기본 입력은 일반 폼이다.
   - 생성/검토 탭과 `/reviews`에서 생성 상태, 누락, 미입력 항목, 검토 의견을 확인한다.
   - 기존 `/autofill-form` API는 호환용으로 유지한다.

### 실무 작업대 (2026-09)

G2B 연결 진단: [서비스 문서 비교 및 연결 검사](docs/g2b-connection-diagnosis-2026-09-06.md). `G2B_API_SCHEME`는 `https` 기본이며 제공기관 계약에 따른 명시적 `http` 선택만 지원한다. HTTP는 인증키를 암호화하지 않으며 자동 전환하지 않는다. 현재 검색 클라이언트는 공공데이터개방표준서비스가 아닌 입찰공고정보서비스를 사용한다.

- 기본 주소는 `/notices`: 진행 중 공고, 마감일 오름차순(미확인 뒤), URL 검색/필터/페이지 유지.
- `/search`는 G2B 검색과 저장, `/reviews`는 HWP 작업 검토, `/admin`은 연결/회사정보/매핑/SKU 관리다.
- 상세는 `공고 검토`, `서류 준비`, `규격 대응`, `제안서`, `생성/검토` 탭으로 나눈다.
- `?tab=review|documents|spec|proposal|exports`와 기존 `#documents`, `#spec-items`, `#grading`, `#proposal-readiness`, `#exports`를 지원한다.
- 기존 `/notices/{noticeNo}/analyze`, `/compose`는 각각 서류 준비/규격 대응 탭으로 이동한다.
- 전체 후보 수 `spec_item_count`와 실제 요구값이 있는 수 `spec_value_count`는 동일 집계로 목록/상세에 반환한다.
- 검증 절차 및 실연동 차단 사항: [작업대 검증 기록](docs/workbench-ux-verification-2026-09-06.md).

### 서류 준비 패널 ([components/DocumentPreparationPanel.tsx](frontend/src/components/DocumentPreparationPanel.tsx)) — M10

공고 상세의 서류 준비 탭. 누락 서류를 먼저 표시하고 항목별 업로드/공통 서류 연결/준비 상태를 관리한다. 생성물과 HWP 검토 이력은 생성/검토 탭에 둔다.

- **서류 분석** (`status` ∈ {`analyzed`, `form_filled`}) → `POST /notices/{notice_no}/documents/analyze`
  - 룰 기반 9개 기본 체크리스트(입찰참가신청서·사업자등록증·법인등기/인감·제조사 공급확약서·카탈로그·규격대응표·실적증명·입찰보증·자격면허) + Claude 추가 제안 병합
  - drafts: `bid_form_values`(HWP autofill 보강 입력값), `technical_compliance`(규격대응표 Markdown 초안), `submission_summary`(요약 메모)
  - risks: 마감 임박/계약방식/자격 경고
- **첨부 서류 가져오기** → G2B raw의 `ntceSpecDocUrl*` / `ntceSpecFileNm*`를 순회해 PDF/HWP/HWPX를 저장·분석하고 업로드 목록에 `G2B 첨부`로 표시 (`POST /notices/{notice_no}/attachments/fetch`)
- **체크리스트 행 상태 변경** → `PATCH /notices/{notice_no}/documents/checklist/{item_id}` 자동 호출
  - 수동 수정값(`status`, `owner`, `note`)은 다음 분석 시에도 보존 (`_preserve_manual_updates`)
- **제출 전 검증** (서류 분석 결과가 있을 때) → `POST /notices/{notice_no}/documents/validate`
  - `ready_for_submission=true` → 토스트로 통과 알림
  - `false` → 필수 누락 항목 이름을 토스트에 표시
- **초안 복사** — 각 draft 카드의 복사 버튼으로 클립보드 복사
- **파일 업로드** (M11) — "파일 업로드" 버튼으로 사업자등록증·인감·실적증명 등을 첨부. 체크리스트 항목 매핑 시 해당 항목 상태가 자동으로 `ready`로 승격
- **Excel/HWP 내보내기** (M11) — 규격대응표 초안을 실제 `.xlsx`(autojebi에서 직접 생성)/`.hwp`(milim-hwp-agent 위임) 파일로 변환 후 다운로드. 다운로드는 Next.js API route가 `INTERNAL_API_KEY`를 서버사이드 주입하므로 브라우저 `<a download>`로 한 번에 받기 가능

점수 배지 색 ([components/ScoreBadge.tsx](frontend/src/components/ScoreBadge.tsx)):
- ≥0.8 emerald(초록), 0.6~0.8 amber(황색), 0.4~0.6 orange(주황), 0~0.4 red(적색)
- `fit_score`는 100 스케일이지만 100으로 나눠 동일 규칙 적용

카테고리 배지 색 ([components/CategoryBadge.tsx](frontend/src/components/CategoryBadge.tsx)):
- HIL/SW = 파랑(Sangjun 담당), IGBT/SCR/수동소자/ABB장비 = 주황(이용문), 혼합 = 보라, 비관련 = 회색

### `/admin` — 어드민 ([page.tsx](frontend/src/app/admin/page.tsx))

- **공고 수동 Upsert** ([components/UpsertNoticeForm.tsx](frontend/src/components/UpsertNoticeForm.tsx)) → `POST /notices/upsert`
  - 입력: `notice_no` (필수), `title`, `source` (기본 `KJEBI`), `raw` (JSON 원문)
  - 상태: `collected` (새 공고만), 기존이면 멱등 — 다운그레이드 없음
- **SKU 인제스트** ([components/SkuIngestButton.tsx](frontend/src/components/SkuIngestButton.tsx)) → `POST /skus/ingest`
  - 입력: `source` (선택, 비우면 [data/abb_catalog_sample.json](data/) 사용)
  - 응답: `{ ingested, collection }`
- **HWP 필드 매핑 관리** ([components/HwpMappingAdmin.tsx](frontend/src/components/HwpMappingAdmin.tsx)) → `/documents/hwp-templates`
  - 템플릿과 필드 매핑을 생성/수정하고, 삭제 대신 `active=false`로 비활성화
  - transform은 whitelist만 선택 가능하며 자유 코드 입력은 없음

> `/admin`은 별도 인증/권한이 없다 — 내부 네트워크 전용으로 가정. 외부 노출 금지.

---

## 7. API / CLI 레퍼런스

### 준비 사유 코드·실무 평가 (2026-09-22)

`GET /v2/notices/{notice_no}/workspace`는 `readiness_issues[]`와 `readiness_checked_at`을 추가 제공한다.
각 사유는 `code/scope/entity_id/blocking/message_params/message/next_action`을 포함하며 기존 `blockers`는 같은 결과의 한국어 투영이다.
verify 작업 결과와 검토 패키지 manifest에도 구조화된 사유·확인 시각·입력 버전을 보존한다. 조회는 승인이나 입력 버전을 변경하지 않는다.
`python -m tools.company_pilot init|freeze|lock-validation|report <폴더>`는 5건 실무 평가의 빈 양식 생성·목표 고정·검증 버전 고정·집계를 지원한다.
실무자와 실제 증빙은 아직 확보 전이며 합성 테스트 결과는 실무 성과가 아니다.
[측정 절차](docs/company-pilot-runbook.md)와 [ADR 0003](docs/adr/0003-readiness-issues-and-pilot-protocol.md)을 따른다.

`GET /v2/company-assets`에는 `category_catalog: {version, sha256, items:[{code,label,role}]}`가 추가된다.
기존 9개 분류의 코드·한국어 표시명·자료 역할은 이 카탈로그를 공유한다. 분류 조회는 증빙 검토나 공고 승인이 아니다.
새 화면에서 카탈로그를 가져오지 못하면 원본 조회/다운로드를 유지하고 등록·분류 수정은 재조회 후 진행한다.

### 문서 완결 흐름 (2026-09-13)

- `POST /v2/notices`는 선택 입력 `org_name`, 시간대가 포함된 `close_date`를 보존한다. 수동 등록 화면은 한국시간을 명시하며 마감 미확인·경과 상태는 제출 준비 완료를 허용하지 않는다.
- `PUT /v2/notices/{notice_no}/output-plan`은 `{version, template_keys, note}`를 받는다. 활성 HWP 서식을 선택하며 `inputs.output_plan`에 보존한다. 현재 원문에 대해 확인한 비어 있지 않은 작성 계획이 원본 첨부·전자 제출만 포함하면, 확인 의견과 함께 `template_keys: []`를 명시해 제안서 본문·HWP 생성을 생략할 수 있다. Excel·원문·증빙·작성 양식과 요구사항의 기존 검토 조건은 유지한다. 작성 계획이 오래됐거나 직접 작성 항목이 추가되면 빈 출력 계획은 무효다. 계획 변경 시 입력 버전이 올라가고 생성 파일을 다시 검토한다. 미설정 데이터는 기존 `bid_form/proposal` 요구를 유지한다.
- `GET /v2/notices/{notice_no}/requirement-candidates?version=...`는 현재 공고 원문에서 의무·수량·기한·제출 표현을 포함한 행을 읽기 전용 후보로 반환한다. `{version, items, scanned_characters, source_document_count, limited, warnings}`이며 후보에 원문 인용, 파일/본문 해시, 문자 위치와 행 위치를 포함한다. 최대 100개·150,000자 범위로 제한하고 문장을 잘라 제안하지 않는다. 화면에서 문맥 확인 후 기존 요구사항 API로 `pending/unassessed` 저장하며 승인하거나 LLM을 호출하지 않는다.
- 패키지는 선택한 최신 HWP와 Excel, 원문, 작성된 원본 양식을 포함한다. 입찰/기타 작성 대상은 실제 해당 원본 양식 작성·검토까지 확인하며 Markdown 초안만으로 제출 준비를 완료하지 않는다.
- `POST /v2/notices/{notice_no}/reviews`의 HWP `approved`에는 검토한 `output_sha256`과 `layout_confirmed=true`가 필요하다. 저장값 미검증·미입력·내용 경고는 승인으로 해소할 수 없다. 파일에 연결된 배치 승인은 새 패키지에서 배치 경고를 해소한다.
- `ready`는 현재 선택한 파일·해시·승인·패키지를 다시 대조한다. 파일 변경, 반려, 재생성, 입력 변경으로 기존 제출 준비 판정이 무효화되고 이력은 보존된다. `reviews[]`에는 `actor`, `output_sha256`, `layout_confirmed`가 노출된다.
- `GET /v2/worker/health`의 `runtime`은 API 및 실행기의 시작 지문/현재 지문과 `current/mismatch/unknown`, `restart_required`, 프로세스별 진단을 반환한다. 시작 시 지문은 고정하며 현재 파일은 5초 캐시·60초 전체 재해시로 비교한다. 상태 조회가 작업을 중단하거나 재시작하지 않는다.
- 개인 계정 로그인과 조회/작성/검토/최종승인 역할은 opt-in이다. `GET /v2/identity`와 [개인 인증 설정](docs/workspace-identity-2026-09-13.md)을 따른다. 기존 shared-key 환경은 개인 인증 완료로 간주하지 않는다.
- `GET /v2/hwp-templates`와 HWP 검사·생성 결과는 SHA에 연결된 `provenance`/`template_provenance`를 반환한다. 검증 골격과 출처 미확인 기본 서식은 생성 시험만 허용하고 출력 승인·최종 준비 완료를 차단한다. 실제 원본 등록과 기존 골격 이관은 [템플릿 출처 관리](docs/hwp-template-provenance-2026-09-20.md)를 따른다.
- ZIP 내부 HWP/HWPX와 깊이 제한 중첩 ZIP을 지원한다. 한국어 OCR은 검토 대기로 유지한다. [첨부 검증](docs/attachment-extraction-completion-2026-09-13.md)과 [완결 E2E 결과](docs/document-loop-completion-2026-09-13.md)에 실검증 범위를 기록한다.

모든 엔드포인트는 `API_KEY`가 설정돼 있으면 `X-API-Key: <키>` 헤더 필요.

### `POST /notices/search` — G2B 실시간 검색 (M13)
```bash
curl -X POST http://localhost:8001/notices/search \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"keyword":"ABB 차단기","start_date":"2026-05-01T00:00:00","end_date":"2026-05-31T23:59:59","page":1,"page_size":50}'
```
응답: `{"items":[...],"total":N,"page":1,"page_size":50,"total_pages":M}`. 각 item에는 `already_exists`가 포함된다. 검색은 DB write가 없으며, 저장은 선택한 결과를 `POST /notices/upsert`로 보낸다.

### `POST /notices/upsert` — 수동 등록 ([notices.py](api/routers/notices.py))
```bash
curl -X POST http://localhost:8001/notices/upsert \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"notice_no":"TEST-001","title":"...","source":"KJEBI","raw":{...}}'
```
멱등(`ON CONFLICT (notice_no)`). 기존 상태가 `analyzed` 이상이면 다운그레이드 안 됨.

### `POST /notices/{notice_no}/analyze` — Claude 분석 (M2)
```bash
curl -X POST http://localhost:8001/notices/R26BK01543282-000/analyze \
     -H "X-API-Key: $API_KEY"
```
응답:
```json
{
  "category": "ABB장비",
  "fit_score": 72,
  "assignee": "이용문",
  "analysis": {
    "elec_spec": { "product_category": "변압기", "rated_power_kva": 500, ... },
    "errors": [],
    "attachment_used": "input_form.hwp"
  },
  "status": "analyzed"
}
```
첫 G2B 첨부(HWP/PDF)를 자동 다운받아 Claude tool-use(`extract_electrical_specs`)에 같이 넘긴다. 끄려면 `LLM_ATTACHMENT_FETCH=false`.

### `POST /notices/{notice_no}/grade` — 3축 그레이딩 (M5)
```bash
curl -X POST http://localhost:8001/notices/R26BK01543282-000/grade \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"alert": true}'
```
응답:
```json
{
  "score_spec": 0.84, "score_qual": 1.0, "score_price": 0.93,
  "score_total": 0.91,
  "top_sku": "ABB-TR-500-22", "top_sku_name": "ABB 500kVA 22.9kV 변압기",
  "grade_reason": "사양 일치도 높음 ...",
  "risk_note": "자격등록 마감 임박",
  "slack_delivered": true,
  "status": "analyzed"
}
```
`alert=false`면 임계치를 넘겨도 Slack 발송 안 함. `fit_score = int(score_total*100)`로 DB 동기화.

### `POST /notices/{notice_no}/notify` — 최종 상태 확정
```bash
curl -X POST http://localhost:8001/notices/R26BK01543282-000/notify \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"dry_run": false}'
```
응답: `{ "status": "notified"|"digest_queued"|"archived_low", "delivered": true|false }`.  
`dry_run=true`면 Webhook 발송 없이 상태만 전이.

### `POST /notices/{notice_no}/autofill-form` — HWP 양식 (M4)
```bash
curl -X POST http://localhost:8001/notices/R26BK01543282-000/autofill-form \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{
    "template_path": "C:\\\\milim\\\\bid_template.hwp",
    "output_path": "C:\\\\milim\\\\out\\\\R26BK01543282-000.hwp",
    "values": { "custom_field": "override" },
    "visible": false
  }'
```
응답: `{ "replaced": ["회사명","사업자번호",...], "missing": [], "remaining_placeholders": [] }`.  
상태: `analyzed → form_filled`. 자세한 동작은 [§ 9 HWP 양식 자동 작성](#9-hwp-양식-자동-작성).

### `POST /notices/{notice_no}/documents/analyze` — 서류 자동화 분석 (M10)
```bash
curl -X POST http://localhost:8001/notices/R26BK01543282-000/documents/analyze \
     -H "X-API-Key: $API_KEY"
```
응답: `{ "notice_no": "...", "document_automation": { "checklist": [...], "drafts": {...}, "risks": [...], "generated_at": "...", "source": "rule+llm", "ready_for_submission": false, "missing_required": [...], "errors": [] } }`.
- 룰(9개 기본 서류) + Claude tool-use 제안 병합 후 `analysis.document_automation`에 저장.
- 호출 조건: `status` ∈ {`analyzed`, `form_filled`} (그 외는 409).
- LLM 실패 시 errors에 기록하고 룰 기반으로만 계속 진행.

### `PATCH /notices/{notice_no}/documents/checklist/{item_id}` — 체크리스트 항목 수정 (M10)
```bash
curl -X PATCH http://localhost:8001/notices/R26BK01543282-000/documents/checklist/bid_form \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"status":"ready","owner":"이용문","note":"확인 완료"}'
```
- 항목 `status`/`owner`/`note` 부분 수정. 다음 분석 시에도 보존 (`_preserve_manual_updates`).
- 항목 없으면 404, `document_automation` 자체가 없으면 409.

### `POST /notices/{notice_no}/documents/validate` — 제출 전 검증 (M10)
```bash
curl -X POST http://localhost:8001/notices/R26BK01543282-000/documents/validate \
     -H "X-API-Key: $API_KEY"
```
응답: `{ "notice_no": "...", "ready_for_submission": true|false, "missing_required": [...], "checklist": [...] }`. 필수 항목 중 `ready`/`generated`가 아닌 것을 누락으로 반환.

### `POST /notices/{notice_no}/attachments/fetch` — G2B 첨부 가져오기
```bash
curl -X POST http://localhost:8001/notices/R26BK01543282-000/attachments/fetch \
     -H "X-API-Key: $API_KEY"
```
응답: `{ "notice_no": "...", "job_id": 1, "status": "completed|completed_with_errors", "files": [...], "fetched": [UploadedDocument, ...], "errors": [...] }`.
- `raw.ntceSpecDocUrl*` / `raw.ntceSpecFileNm*`에서 PDF/HWP/HWPX만 저장하고 `source_ref="g2b_attachment"`로 `analysis.document_automation.uploads[]`에 연결.
- PDF는 텍스트 추출, HWP/HWPX는 milim-hwp-agent 분석을 best-effort로 수행한다.
- 파일별 다운로드/분석 실패는 `attachment_fetch_jobs` / `attachment_fetch_files`, `notice_errors`, `errors[]`, `document_automation.errors[]`에 기록하고 전체 흐름은 계속 진행한다.
- 같은 파일명/출처는 재호출해도 중복 저장하지 않는다.

### `POST /notices/{notice_no}/documents/uploads` — 사용자 파일 업로드 (M11)
```bash
curl -X POST http://localhost:8001/notices/R26BK01543282-000/documents/uploads \
  -H "X-API-Key: $API_KEY" \
  -F "file=@사업자등록증.pdf" \
  -F "item_id=business_registration"
```
응답: `{ "notice_no": "...", "uploaded": { "id", "name", "size", "mime", "item_id", "storage_path", "uploaded_at", "sha256" } }`.
- `item_id` 매핑 시 해당 체크리스트 항목 `status`가 자동으로 `ready` 승격 (수동으로 `generated/not_applicable` 등 다른 상태로 둔 경우는 존중).
- 허용 확장자/사이즈는 `UPLOAD_ALLOWED_EXTS` / `UPLOAD_MAX_BYTES` 환경변수. 위반 시 415/413.

### `GET /notices/{notice_no}/documents/uploads` — 업로드 목록
응답: `{ "notice_no": "...", "items": [UploadedDocument, ...] }`.

### `DELETE /notices/{notice_no}/documents/uploads/{upload_id}` — 업로드 삭제
디스크 파일 + 메타데이터 동시 삭제. 응답: `{ "notice_no": "...", "deleted": "<upload_id>" }`.

### `GET /notices/{notice_no}/documents/uploads/{upload_id}/download` — 업로드 다운로드
서버가 저장한 파일을 그대로 스트리밍. 프론트는 `/api/notices/{notice_no}/documents/uploads/{upload_id}/download` Next.js route로 프록시 호출.

### `POST /notices/{notice_no}/documents/exports/{kind}` — Excel/HWP 생성 (M11)
`kind` ∈ {`excel`, `hwp`}. `bid_form_hwp`와 `proposal_hwp`는 필드 매핑 기반 `POST /notices/{notice_no}/documents/hwp-put-fields` 또는 `proposal-compose`로 생성한다.
```bash
curl -X POST http://localhost:8001/notices/R26BK01543282-000/documents/exports/excel \
     -H "X-API-Key: $API_KEY"
```
응답: `{ "notice_no": "...", "export": { "id", "kind", "draft_id", "output_path", "mime", "generated_at", "version", "validation_status", "file_size", "sha256", ... } }`.
- Excel은 autojebi가 `openpyxl`로 직접 생성 — milim-hwp-agent 의존 없음. 기본 버전은 `compliance_excel_v2`, 요청 body `{"version":"compliance_excel_v1"}`로 기존 단일 시트 포맷 생성 가능.
- HWP는 생성 전 `validate_pre_compose()`로 규격 항목/필수 서류/필수 작성값을 확인하고, 통과 시 milim-hwp-agent의 `POST /document/insert-table` 호출을 위임한다.
- 낮은 confidence, `candidate`, `review_priority=high` 규격 항목은 생성 차단이 아니라 `validation_status=warning`과 `validation_errors[]`로 남긴다.
- `notice_exports`가 우선 저장소이며 `analysis.document_automation.exports[]`에는 프론트 호환 mirror를 유지한다. 동일 `(kind,draft_id)` 재호출 시 이전 active row는 soft-delete된다.

### `POST /notices/{notice_no}/documents/proposal-compose` — HWP 제안서 생성 (M14)
요청: `{ "template_path": "templates/제안서_양식.hwp", "values_override": {}, "visible": false }`.
응답: `{ "notice_no", "export", "proposal", "remaining_placeholders", "errors" }`.
- 입력 소스는 공고 정규 컬럼/raw, `analysis.document_automation`, `notice_spec_items`, grade/SKU 결과다.
- `notice_spec_items`가 없으면 409(`규격 항목 추출 필요`).
- HWP 필드 매핑이 seed되어 있으면 `template_key='proposal'`의 `document_field_mappings`를 통해 Windows HWP Worker `POST /document/put-fields`에 `{ template_path, output_path, values, visible }`를 위임한다.
- agent 실패 시 제안서 draft와 `errors[]`는 저장하고, HWP 파일이 생성된 경우에만 `proposal_hwp` export를 기록한다. `remaining_placeholders`가 남으면 export는 저장하되 `validation_status=warning`으로 표시한다.

### HWP 필드 매핑 기반 자동작성 (M14+)
`python -m api.hwp_fields seed`는 회사·템플릿·필드 매핑 중 없는 기본 항목만 추가한다. 기존 관리자 수정값, 메타데이터, 비활성 상태는 보존한다. 기존 회사정보를 로컬 설정의 비어 있지 않은 값으로 갱신하려면 `python -m api.hwp_fields seed --update-company-from-env`를 명시한다. HWP 양식에는 `document_field_mappings.hwp_field_name`과 같은 필드명을 미리 삽입한다.

- `GET /documents/hwp-templates` — active 템플릿과 필드 매핑 조회.
- `GET /documents/company-profile` — 활성 회사 프로필(없으면 환경 설정 기본값) 조회. 기존 API 키 인증 적용.
- `GET /documents/hwp-jobs` — DB 작업 기록 조회. `q`(공고명/번호/템플릿명), `review_status=pending|approved|rejected`, `status=pending|running|completed|failed`, `page>=1`, `page_size=1..100`(기본 20). `{items:[{job,title,template_name,export}],total,page,page_size,total_pages}` 반환. `job.created_at` 포함, 최신순.
- `POST /documents/hwp-templates` / `PATCH /documents/hwp-templates/{template_id}` — 관리자용 템플릿 upsert/수정/soft-disable.
- `POST /documents/hwp-templates/{template_id}/mappings` / `PATCH /documents/hwp-templates/{template_id}/mappings/{mapping_id}` — 관리자용 필드 매핑 upsert/수정/soft-disable.
- `POST /notices/{notice_no}/documents/hwp-context` — `template_key` 기준 Context JSON, 실제 입력값, required 누락 미리보기.
- `POST /notices/{notice_no}/documents/hwp-put-fields` — Windows HWP Worker `/document/put-fields`에 `{ template_path, output_path, values, visible }`를 위임해 `PutFieldText` 입력.
- `POST /notices/{notice_no}/documents/hwp-jobs/{job_id}/review` — 사람 검토 결과(`pending`/`approved`/`rejected`) 저장.
  - 성공 생성물과 유효 export가 없는 작업의 승인은 409. 필수 누락/미입력 항목/검증 경고가 있으면 공백 아닌 `review_note` 필수(422). 다운로드는 경고가 있어도 허용.
  - `hwp-compose`의 `template_key` 기본값은 `bid_form`, `proposal-compose`는 `proposal`. 선택한 활성 템플릿으로 매핑한다.
- `GET /proposals/{notice_no}/sections` — 저장된 섹션/근거/사실검증 상태 조회. 생성이나 외부 검색을 자동 실행하지 않는다.
- transform은 whitelist(`none`, `date_yyyy_mm_dd`, `number_comma`, `business_number_dash`, `strip`, `truncate_1000`)만 허용한다.
- 생성 로그는 `hwp_generation_jobs`에 context/input/missing/remaining/review_status로 저장되고, UI는 required 누락·remaining placeholder·검토 상태를 표시한다.
- Windows HWP Worker는 HWP COM 제약 때문에 단일 Lock/Queue로 `/document/put-fields` 작업을 순차 실행해야 한다.

### Proposal Agent POC — Evidence 기반 제안서 Workspace
공고 맞춤형 제안서 자동작성의 첫 단계로, AI가 바로 본문을 지어내지 않고 `요구사항 → Evidence → 섹션 초안 → 사실검증 → coverage` 순서로 구조화한다. 원문은 PostgreSQL의 `proposal_documents` / `document_chunks`가 원장이고, 정확한 실적 수치는 `project_performances`에 별도로 저장한다.

- `POST /proposals/documents` — 사내 제안서/보고서/회사소개서와 chunk를 등록한다. Qdrant에는 추후 `chunk_id`만 연결한다.
- `POST /proposals/performances` — 유사 실적을 정형 DB로 등록한다.
- `POST /proposals/analyze/{notice_no}` — 공고와 규격 항목에서 제안서 요구사항을 추출해 `notice_requirements`에 저장한다.
- `POST /proposals/{notice_no}/retrieve` — 문서 chunk와 실적 DB에서 요구사항별 Evidence Top 5를 저장한다.
- `POST /proposals/{notice_no}/generate` — Evidence ID가 붙은 제안서 섹션 초안을 `proposal_sections`에 저장한다.
- `POST /proposals/{notice_no}/verify` — Evidence 없는 주장과 `[검증필요]` 문구를 검사한다.
- `GET /proposals/{notice_no}/coverage` — 요구사항별 자료 확보 현황과 Proposal Readiness 점수를 반환하며, 공고 상세의 제안서 준비도 패널에 표시한다.

운영 투입 전 실제 또는 준실제 공고 3건 리허설은 [docs/operations-rehearsal.md](docs/operations-rehearsal.md)를 기준으로 기록한다.

### `GET /notices/{notice_no}/documents/exports/by-id/{export_id}/download` — 생성 결과 다운로드
`ExportRecord.id`가 있는 경우 이 경로를 우선 사용한다. active export row가 없으면 404, metadata는 있으나 파일이 없으면 410.

### `GET /notices/{notice_no}/documents/exports/{kind}/download` — 생성 결과 다운로드
기존 호환 경로. 해당 `kind`의 최신 active export를 다운로드한다. 미생성 시 404. 디스크 파일 누락 시 410.

### `POST /skus/ingest` — ABB SKU 카탈로그 인제스트 (M3)
```bash
curl -X POST http://localhost:8001/skus/ingest \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" -d '{}'
```
응답: `{ "ingested": N, "collection": "abb_skus" }`. `{"source": "..."}` 또는 `{"items": [...]}`로 입력 지정 가능.

### `GET /notices` — 목록·검색 ([api/routers/notices.py](api/routers/notices.py))

심화 검색 (M-search): 통합 키워드 + 다중 필터 + 라이프사이클 + 정렬 + 페이지네이션. 모든 파라미터 옵셔널.

```bash
# 기본 (lifecycle 기본은 'all' — 콘솔만 'active'를 명시적으로 보냄)
curl "http://localhost:8001/notices?q=ABB&status=analyzed&status=form_filled&lifecycle=active&sort=close_date&direction=asc&page=1&page_size=20" \
     -H "X-API-Key: $API_KEY"
```

쿼리 파라미터:

| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `q` | str (≤200) | 통합 부분일치 (제목·공고번호·기관·담당자·카테고리·추천SKU·grade_reason·risk_note, 대소문자·공백 무시) |
| `status` | str (반복) | 다중 선택 (`?status=a&status=b` 또는 `?status=a,b`) |
| `category` | str (반복) | 다중 |
| `bid_type` | str (반복) | 다중 |
| `source` | str (반복) | 다중 |
| `org_name` | str | 기관명 부분일치 |
| `assignee` | str | 담당자 정확일치 |
| `min_fit_score` / `max_fit_score` | int 0~100 | 적합도 범위 |
| `min_score_total` / `max_score_total` | float 0~1 | 종합 점수 범위 |
| `min_base_price` / `max_base_price` | float | 예가 범위 (원) |
| `open_from` / `open_to` / `close_from` / `close_to` | ISO 8601 datetime | 날짜 범위 |
| `lifecycle` | `active`/`closed`/`unknown`/`all` | 마감일 기반 분류 (기본 `all`) |
| `has_grade` | bool | `graded_at IS NOT NULL` (3-state) |
| `has_documents` | bool | `analysis.document_automation.generated_at` 존재 |
| `has_uploads` | bool | `uploads` 배열 길이 > 0 |
| `ready_for_submission` | bool | `analysis.document_automation.ready_for_submission == true` |
| `sort` | `close_date`/`updated_at`/`base_price`/`fit_score`/`score_total` | 기본 `updated_at` |
| `direction` | `asc`/`desc` | 기본 `desc`. NULL은 항상 뒤 (NULLS LAST) |
| `page` | int ≥1 | 기본 1 |
| `page_size` | int 1~100 | 기본 20 |

응답:
```json
{
  "items": [
    {
      "notice_no": "R25BK01131552-000",
      "title": "...",
      "source": "G2B",
      "raw": { "...G2B 원본 JSON...": null },
      "category": "ABB장비",
      "fit_score": 78,
      "assignee": "이용문",
      "analysis": { "...": "..." },
      "status": "analyzed",
      "created_at": "2026-06-09T00:00:00+00:00",
      "updated_at": "2026-06-09T00:00:00+00:00",
      "bid_no": "R25BK01131552",
      "bid_seq": "000",
      "bid_type": "물품",
      "org_code": "...",
      "org_name": "서울대학교산학협력단",
      "base_price": 84000000.0,
      "open_date": "2025-11-04T02:05:07+00:00",
      "close_date": "2025-11-12T01:00:00+00:00",
      "collected_at": "2026-06-09T00:00:00+00:00",
      "score_spec": 0.82, "score_qual": 0.70, "score_price": 0.90,
      "score_total": 0.81, "grade_reason": "...", "risk_note": null,
      "top_sku": "...", "top_sku_name": "...", "sku_match_score": 0.86,
      "graded_at": "2026-06-09T00:00:00+00:00"
    }
  ],
  "total": 123,
  "page": 1,
  "page_size": 20,
  "total_pages": 7
}
```

G2B 수집 컬럼(`bid_no`/`bid_seq`/`bid_type`/`org_code`/`org_name`/`base_price`/`open_date`/`close_date`/`collected_at`)은 `bid_pipeline` 정규 컬럼이므로 응답 top-level로 직접 노출된다 — 프론트는 `raw.ntceInsttNm`/`raw.presmptPrce`/`raw.bidClseDt` 대신 이 컬럼을 우선 읽으면 된다.

잘못된 sort/lifecycle/range는 HTTP 422 + 어떤 필드가 어떻게 잘못됐는지 본문에 포함.

기존 `status=analyzed&min_fit_score=50` 호출도 그대로 동작 (호환 유지). 응답에 `items`는 그대로 있고 페이지네이션 메타가 추가.

### `GET /notices/{notice_no}` — 단건 조회
응답: `NoticeRecord` (전 컬럼 — 위 list 응답 `items[*]` 와 동일 스키마). 없으면 404.

### `GET /healthz` — 헬스 ([main.py:44-63](api/main.py))
```bash
curl http://localhost:8001/healthz
# → {"ok": true, "checks": {"db": "ok"}}
```
DB 연결 실패 시 `ok: false`, `checks.db`에 에러 본문. 헤더 없이 호출 가능 (인증 면제).

---

## 8. 점수 체계 — 3축 그레이딩

### 공식 ([api/grading/scorer.py:85-111](api/grading/scorer.py))
```
score_total = spec × 0.5 + qualification × 0.2 + price × 0.3   (기본 가중치)
fit_score   = int(score_total × 100)                           # 0~100
```
가중치 합은 1.0이어야 하며 부팅 시 검증 ([api/config.py:85-88](api/config.py)).

**Hard gate** (`GRADE_HARD_GATE_QUAL_ZERO=true`, 기본): `qualification == 0.0`이면 `total = 0.0` 강제 (지역 미스매치 등으로 입찰 자체가 불가능한 경우).

### 1) Spec 축 (가중치 0.5)
- ElecSpec → Qdrant 임베딩 검색 ([api/sku/matcher.py](api/sku/matcher.py))
- 상위 1건의 코사인 유사도가 점수
- **노이즈 플로어 0.4** — 그 이하 매칭은 0.0 처리 ([scorer.py:19](api/grading/scorer.py))
- Qdrant 미가동/컬렉션 미존재 → 빈 매칭, spec=0.0 (silent fallback)

### 2) Qualification 축 (가중치 0.2) ([qualification.py](api/grading/qualification.py))

우선순위 1: **G2B 자격 API 라이브 호출** (M5, `/getBidPblancListInfoLicenseLimit`, `/getBidPblancListInfoPrtcptPsblRgn`)
- 지역 제한 vs ABB 등록 지역(`ABB_REGISTERED_REGIONS=서울,경기,전국` 기본):
  - 제한 없음 또는 전국 → 통과 (1.0 시작)
  - 등록 지역 중 하나라도 일치 → 통과
  - 미스매치 → **0.0 (hard gate 트리거)**
- 면허 제한: 각 1건당 **-0.15** 감점

우선순위 2: 자격 API 실패/없음 → `raw_json` 휴리스틱
- 계약방법 "수의/지명" → -0.5
- 자격등록 마감 경과 → -0.3
- 신호 전무 → **중립 0.5** (확대 해석 방지)

캐시: `QUAL_CACHE_ENABLED=true`이면 동일 `(bid_no, bid_seq)` 24h 내 재호출 시 메모리 캐시 사용 (`QUAL_CACHE_TTL_HOURS`).

### 3) Price 축 (가중치 0.3) ([scorer.py:31-68](api/grading/scorer.py))
- 카테고리·정격 조합으로 [price_table.py](api/grading/price_table.py)에서 단가 범위 lookup
- `lo = typical_lo × quantity`, `hi = typical_hi × quantity`
- `lo ≤ base_price ≤ hi` → **1.0**
- `base_price < lo` → `(base_price / lo) × 0.7` (저가 의심)
- `base_price > hi` → `(hi / base_price) × 0.7` (고가 의심)
- `base_price` / `quantity` / `product_category` 미상 → **중립 0.5**

가격 출처 라벨: G2B `presmptPrce`(추정가) 우선, 없으면 `asignBdgtAmt`(배정예산).

### 적합 사유 요약 ([summarizer.py](api/grading/summarizer.py))
- Claude tool-use `summarize_fit` 호출 → 한 줄 한국어 사유 (`grade_reason`) + 위험 노트 (`risk_note`)
- LLM 실패 시 룰 기반 fallback (grade 자체는 정상 완료)

### 자동 Slack 알림 조건
- 요청에 `alert=true` AND `score_total ≥ GRADE_ALERT_THRESHOLD(=0.6)`
- 발송: Block Kit 포맷 (3회 재시도, 실패해도 grade는 정상 응답)

### 담당자 라우팅 ([api/services/routing.py](api/services/routing.py))
| 카테고리 | 담당자 |
|---------|--------|
| HIL, SW | Sangjun |
| IGBT, SCR, 수동소자, ABB장비 | 이용문 |
| 혼합 | Sangjun / 이용문 |
| 비관련 | 미배정 |

---

## 9. HWP 양식 자동 작성

[저장소 내 Windows HWP Worker](docs/hwp-worker.md)는 필드 조회, 본문 추출, `/document/create-template`, `/document/put-fields`를 제공한다. v2 작업 실행기는 사람이 요청한 생성만 전달하고 저장 결과를 재검증한다. 2026-09-10 PLECS 제안서의 실제 HWP 16쪽, 표 20개, 필드 510개 저장값과 페이지 이미지를 확인했다. 담당자 내용 승인 및 기존 입찰양식 두 종 전체 검증은 별개다. [실생성 결과와 검증 범위](docs/hwp-layout-implementation-2026-09-10.md)를 따른다.

`hwp_templates.render_mode`는 기존 `fields`와 새 `proposal_layout_v1`만 허용한다. 새 모드는 제한된 Markdown을 실제 제목·문단·표·페이지 나눔과 개별 필드로 구성하고 `PutFieldText`로 입력한다. `python -m api.hwp_fields prepare-template`은 인증된 Worker에서 저장·재열기·필드 검사를 통과한 새 서식만 등록하며 기존 템플릿을 덮어쓰지 않는다.

- `GET /v2/hwp-templates`: 활성 템플릿과 `render_mode`, 매핑, `provenance`(출처 상태·해시·생성/승인 가능 여부).
- `GET /v2/hwp-worker`: 연결·작업 중·복구 필요, 현재 작업번호/단계/경과 시간.
- `GET /v2/jobs/{job_id}/pages/{number}`: 성공한 작업의 해시 검증된 PNG. 기존 API 인증을 적용한다.
- `POST /v2/notices/{notice_no}/jobs`의 `kind=hwp`는 그대로 유지한다. 생성물에 논리 본문/물리 필드 대응표, 입력·레이아웃·템플릿·출력 해시, 페이지 이미지와 검토 상태를 보존한다.
- 실제 줄바꿈 재검증: `HWP_LIVE_SMOKE=true`에서 `python -m tools.verify_hwp_linebreaks`. 인증된 Worker에 새 TEST ONLY 문서를 요청하고 LF/CRLF·저장값·3페이지 이미지를 검증한다. 기존 템플릿·실공고·승인은 변경하지 않는다. [2026-09-20 실검증 기록](docs/practitioner-e2e-2026-09-20.md).

### v2 인용 복구와 실행기 분리 (2026-09-10)
- `POST /v2/notices/{notice_no}/jobs/{job_id}/adopt-requirements`: 현재 `version`, `idempotency_key`, `note`, 선택 후보 `items`의 `candidate_id/quote/start/locator`를 받아 원문 해시와 위치를 재검증한다. 채택은 검토 대기·미판정이며 실패한 분석 이력은 유지한다.
- `PUT /v2/notices/{notice_no}/source-needs`: 현재 `version`과 `items`의 문서 ID, `missing/linked/not_applicable`, 근거 인용·의견을 저장한다. 미해결 참조 문서는 제출 준비를 차단하지만 검토용 초안은 허용한다.
- 작업 조회에 `quote_diagnostics`, `execution_lane`을 제공한다. 원문 일치·공백 차이·중복 위치·불일치를 구분하며 LLM 전체 응답이나 비밀값은 오류에 저장하지 않는다.

### v2 Excel/ZIP/PDF 추출 (2026-09-11)
- 기존 `kind=extract` 작업과 결과 반영 API를 사용한다. `result.documents[].extraction` 및 반영 후 `inputs.documents[].extraction`에 완전성(`complete`), 시트/셀(`cells`), 품목 후보(`items`), ZIP 내부 파일(`members`), PDF 페이지(`pages`)를 보존한다.
- XLSX는 읽기 전용으로 처리한다. 수식은 실행하지 않으며 캐시가 없으면 값은 null이다. 수식 값은 별도 대조가 필요하고 품목은 자동 적합/가격 판정이 아닌 후보다.
- ZIP을 디스크에 풀거나 실행하지 않는다. 내부 XLSX/PDF는 추출하며 HWP/도면/중첩 ZIP 등 미지원 파일도 해시와 미확인 상태로 남긴다. 일부 텍스트만 확보돼도 전체 원문 완료로 인정하지 않는다. XLS 바이너리 파서는 아직 지원하지 않는다.
- 스캔 PDF는 로컬 Tesseract가 설치된 경우 OCR한다. `WORKSPACE_OCR_ENABLED`, `TESSERACT_CMD`, `WORKSPACE_OCR_LANGUAGES=kor+eng`로 설정한다. 언어팩은 별도 설치가 필요하며 원문을 외부 OCR 서비스로 보내지 않는다.
- OCR 결과는 페이지별 신뢰도와 원문 대조 필요 상태로 보존한다. 미설치/시간 초과/읽지 못한 페이지는 완료로 숨기지 않는다. 입력 파일 50MB, ZIP 500개 항목/누적 해제 50MB, PDF 100쪽, 작업당 OCR 최대 10쪽 및 페이지당 20초 제한을 적용한다.
- 검증 범위와 남은 실제 파일 검증은 [첨부 처리 기록](docs/attachment-extraction-2026-09-11.md)을 따른다.
- `python -m api.workspace.supervisor --split`은 `local`(verify/excel/package)과 `external` 실행기를 각각 하나씩 실행한다. PostgreSQL 잠금, 완료 기록, 복구와 health는 경로별로 분리한다. 기존 `--lane all` 실행기와 혼용하지 않는다.
- `infra/start-workspace.ps1`은 분리 실행을 기본 사용한다. `-BackendOnly`는 기존 프론트를 유지하고 API/실행기만 시작하며, 기존 프로세스를 자동 종료하지 않는다.
- `hwp_inspect/hwp` 요청과 명시적 복구 요청의 `visible`은 기본 false다. 필드 검사 Worker 요청의 `operation_id/visible`은 선택값이다. `failure_stage/failed_at`은 뒤늦은 정리 단계와 구분하며 재시작으로 복구 차단을 해제하지 않는다.
- [현재 공고 복구 구현·실검증 보고서](docs/current-notice-recovery-2026-09-10.md): 실제 HWP 생성과 AI 인용 실패 복구, mock 검증 및 남은 사람 검토를 구분한다.

레거시 `POST /notices/{notice_no}/autofill-form`의 `/bid-form/autofill`은 기존 외부 Agent 전용 계약이다. 새 Worker가 해당 레거시 합성/RAG 기능까지 대체한다고 간주하지 않는다.

### 전송되는 값
**환경변수 (회사 상수)** — [.env](#11-환경변수-레퍼런스)에서 로드:
- `COMPANY_NAME` → 회사명
- `COMPANY_BUSINESS_NUMBER` → 사업자등록번호
- `COMPANY_CEO_NAME` → 대표이사명
- `COMPANY_ADDRESS` → 회사 주소

**공고 메타** — `bid_pipeline` 레코드에서:
- `notice_no`, `title`, `category`, `assignee`, `fit_score`

기존 동기 API에는 값 override가 있지만, v2는 회사 프로필과 입력 버전의 스냅샷·매핑을 사용한다. 작성값과 회사 증빙은 사람이 대조하며, 생성 성공은 제출 승인이 아니다.

### 응답 해석
| 필드 | 의미 |
|------|------|
| `replaced` | 요청했고 템플릿에서 찾아 입력한 필드명. v2는 저장 후 실제 값도 재조회 |
| `missing` | 요청한 필드 중 실제 템플릿에서 찾지 못한 필드명 |
| `remaining_placeholders` | 저장값이 비어 있거나 검증 표식이 남은 필드명 |

v2는 독립 작업의 입력·출력·해시·검증 결과를 기록하며 참가 결정을 변경하지 않는다. 기존 `analysis.bid_form`과 `form_filled`는 레거시 호환용으로 구분한다.

### 클라이언트 ([api/services/hwp_agent_client.py](api/services/hwp_agent_client.py))
- `HWP_AGENT_BASE_URL` (기본 `http://127.0.0.1:8000`)
- `HWP_AGENT_TOKEN`은 `X-Agent-Token` 헤더로 전달한다. 저장소 내 Worker는 32자 이상 토큰이 필수다.
- 읽기 HTTP 요청만 최대 2회 재시도한다. 생성 등 POST 요청은 결과가 불확실할 수 있으므로 자동 재시도하지 않는다. 기본 timeout은 30초, v2 HWP 생성 호출은 120초다.

---

## 10. 운영

### 컨테이너 라이프사이클
```bash
# 전체 기동
docker compose -f infra/docker-compose.yml up -d

# 일부 서비스만
docker compose -f infra/docker-compose.yml up -d db qdrant

# 로그 follow
docker compose -f infra/docker-compose.yml logs -f api
docker compose -f infra/docker-compose.yml logs -f frontend

# 재빌드 후 기동
docker compose -f infra/docker-compose.yml up -d --build

# 종료
docker compose -f infra/docker-compose.yml down

# 데이터까지 삭제 (DB 볼륨 포함)
docker compose -f infra/docker-compose.yml down -v
```

### DB 마이그레이션
- API 컨테이너 부팅 시 `alembic upgrade head` 자동 실행 ([infra/Dockerfile:30](infra/Dockerfile))
- 로컬 dev: `alembic upgrade head` 수동
- 기존 운영 DB(raw SQL 셋업)에서 alembic 도입: `alembic stamp head` (실행 없이 현재 상태만 기록)

### 헬스 확인
```bash
curl http://localhost:8001/healthz
# {"ok": true, "checks": {"db": "ok"}}

docker compose -f infra/docker-compose.yml ps
# 모든 서비스 (healthy) 표시
```

### 테스트
```bash
python -m pytest -v           # 백엔드 262 tests (인증 8개)
cd frontend && npm test       # Vitest 단위
cd frontend && npm run e2e    # Playwright smoke/workflow (`docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml up -d db api frontend` 선행)
cd frontend && E2E_BASE_URL=http://127.0.0.1:3002 E2E_API_BASE=http://127.0.0.1:8002 npm run e2e  # 로컬 분리 포트 smoke/workflow
cd frontend && E2E_OPS_LIVE=1 npm run e2e -- --project=chromium-ops-live  # 실제 외부 의존성 smoke
```

### 포트 충돌 override
이미 다른 컨테이너가 5433/3000/6333을 점유 중이면 `infra/docker-compose.override.yml`을 추가해 회피:
```yaml
services:
  qdrant:
    profiles: ["skip"]          # 호스트의 기존 qdrant 재사용

  db:
    ports: !override
      - "5434:5432"             # 5433 → 5434

  api:
    environment:
      QDRANT_URL: http://host.docker.internal:6333
    depends_on: !override
      db:
        condition: service_healthy
    extra_hosts:
      - "host.docker.internal:host-gateway"

  frontend:
    ports: !override
      - "3001:3000"
```
실행: `docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml --env-file .env up -d`.

### 로그 레벨
- `LOG_LEVEL=INFO` (기본) — DEBUG/INFO/WARNING/ERROR

---

## 11. 환경변수 레퍼런스

[.env.example](.env.example) 전체. 필수 표시는 운영 기준.

### 데이터베이스
| 변수 | 기본값 | 필수 | 설명 |
|------|-------|------|------|
| `DATABASE_URL` | (빈값) | ✓ | `postgresql+psycopg://user:pw@host:5432/db` |

### Claude / RAG
| 변수 | 기본값 | 필수 | 설명 |
|------|-------|------|------|
| `ANTHROPIC_API_KEY` | (빈값) | ✓ | Claude API 키 |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5` |  | 사용 모델 |
| `ANTHROPIC_MAX_TOKENS` | `2048` |  | 응답 토큰 한도 |
| `LLM_ATTACHMENT_FETCH` | `true` |  | G2B 첫 첨부 자동 다운 |
| `G2B_ATTACHMENT_DIR` | (시스템 temp) |  | 첨부 저장 경로 |

### Qdrant
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `QDRANT_URL` | `http://localhost:6333` | Qdrant 서버 |
| `QDRANT_API_KEY` | (빈값) | 선택 |
| `QDRANT_COLLECTION_NAME` | `abb_skus` | SKU 인덱스 컬렉션 |

### 3축 그레이딩
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `GRADE_WEIGHT_SPEC` | `0.5` | spec 가중치 (합=1.0) |
| `GRADE_WEIGHT_QUAL` | `0.2` | qualification 가중치 |
| `GRADE_WEIGHT_PRICE` | `0.3` | price 가중치 |
| `GRADE_HARD_GATE_QUAL_ZERO` | `true` | qual=0 → total=0 강제 |
| `GRADE_ALERT_THRESHOLD` | `0.6` | Slack 알림 임계 |
| `ABB_REGISTERED_REGIONS` | `서울,경기,전국` | 지역 규칙 (CSV) |

### Slack / Teams
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `SLACK_WEBHOOK_URL` | (빈값) | 빈값이면 grade 알림 미발송 |
| `TEAMS_WEBHOOK_URL` | (빈값) | 빈값이면 `/notify`는 dry-run |

### G2B (data.go.kr)
| 변수 | 기본값 | 필수 | 설명 |
|------|-------|------|------|
| `DATA_GO_KR_API_KEY` | (빈값) | ✓ | 공공데이터포털 인증키 |
| `BID_KEYWORDS` | `ABB,차단기,변압기,인버터,전력변환,UPS,배전반,IGBT,모터드라이브` |  | 검색 키워드 (CSV) |
| `COLLECT_HOUR` | `8` |  | 일일 수집 시(KST) |
| `COLLECT_MINUTE` | `0` |  | 일일 수집 분 |
| `SCHEDULER_ENABLED` | `true` |  | 스케줄러 on/off |

### 자동 그레이드 스케줄러
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `SCHEDULER_GRADE_ENABLED` | `true` | 자동 grade 잡 on/off |
| `GRADE_INTERVAL_MINUTES` | `30` | `0`이면 미등록 |
| `GRADE_BATCH_LIMIT` | `50` | 회당 최대 grade 공고 수 |

### 자격 API 캐시
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `QUAL_CACHE_ENABLED` | `true` | 캐시 on/off |
| `QUAL_CACHE_TTL_HOURS` | `24` | TTL |

### 프론트엔드
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `FRONTEND_ORIGIN` | `http://localhost:3000` | CORS allow_origins (CSV로 여러개) |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8001` | 프론트가 호출할 API (build/run time inline) |

### 인증 (M9)
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `API_KEY` | (빈값) | 빈값이면 인증 비활성. 운영은 32+ 문자 시크릿 |
| `INTERNAL_API_KEY` | (빈값) | Server Action server-side 주입용 (보통 `API_KEY`와 동일값) |

### 서류 자동화 v2 — 업로드/내보내기 (M11)
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `UPLOAD_DIR` | (빈값) | 빈값이면 `<temp>/autojebi/uploads`. 도커는 `/app/uploads` (호스트 `./data/uploads`) |
| `EXPORT_DIR` | (빈값) | 빈값이면 `<temp>/autojebi/exports`. 도커는 `/app/exports` (호스트 `./data/exports`) |
| `UPLOAD_MAX_BYTES` | `30000000` | 30MB. 초과 시 413 |
| `UPLOAD_ALLOWED_EXTS` | `pdf,hwp,hwpx,jpg,jpeg,png,xlsx,docx` | CSV. 위반 시 415 |

### HWP 에이전트 / 회사정보
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `HWP_AGENT_BASE_URL` | `http://127.0.0.1:8000` | 저장소 내 Windows HWP Worker 주소 |
| `HWP_AGENT_TOKEN` | (빈값) | Worker 실행에 32자 이상 필수. 빈값 인증 우회 없음. 로컬 API도 `--env-file .env`로 실행 |
| `COMPANY_NAME` | (빈값) | HWP 양식 회사명 |
| `COMPANY_BUSINESS_NUMBER` | (빈값) | 사업자번호 |
| `COMPANY_CEO_NAME` | (빈값) | 대표이사 |
| `COMPANY_ADDRESS` | (빈값) | 회사 주소 |

### 기타
| 변수 | 기본값 | 설명 |
|------|-------|------|
| `LOG_LEVEL` | `INFO` | uvicorn/앱 로그 레벨 |

---

## 12. 인증 (M9)

### 동작
- `.env`에 `API_KEY=<32+ 문자 랜덤 시크릿>` 설정 → 모든 라우터에 `X-API-Key` 헤더 필수
- `API_KEY=`(빈값) → 인증 비활성 (개발 친화)
- `/healthz`는 인증 면제 (Docker HEALTHCHECK용)

### 프론트엔드 server-side 주입
- 콘솔의 Server Action은 `INTERNAL_API_KEY`를 server-side 환경변수로 로드해 `X-API-Key`로 자동 첨부 → 브라우저 노출 0
- 보통 `API_KEY == INTERNAL_API_KEY`로 동일 시크릿 사용

### curl 호출
```bash
export API_KEY=your-32-char-secret
curl -X POST http://localhost:8001/notices/search \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"keyword":"ABB","page":1,"page_size":20}'
```

### 코드 위치
[api/auth.py](api/auth.py) — `verify_api_key` dependency. 라우터 정의 시 `dependencies=[Depends(verify_api_key)]`로 attach.

---

## 13. 트러블슈팅

### "Qdrant 연결 실패"
- 증상: grade 응답의 `score_spec=0.0`, `top_sku=null`
- 원인: Qdrant 미가동, 컬렉션 미인제스트, `QDRANT_URL` 오설정
- 동작: silent fallback (grade 자체는 정상 완료, spec 점수만 0)
- 해결: `docker compose up -d qdrant` + `POST /skus/ingest`

### "G2B 자격 API 타임아웃"
- 증상: grade 응답에 `risk_note: "자격 API 응답 없음 ..."` 또는 raw_json 휴리스틱 점수
- 동작: silent fallback → `raw_json` 휴리스틱 사용
- 해결: `DATA_GO_KR_API_KEY` 확인, data.go.kr 일시 장애 대기

### "Claude tool-use 실패"
- 증상: `analyze` 응답의 `analysis.errors`에 LLM 에러, `category=비관련`, `fit_score=0`
- 원인: `ANTHROPIC_API_KEY` 미설정/만료, 토큰 한도 초과
- 해결: 키 갱신, `ANTHROPIC_MAX_TOKENS` 상향, 첨부 너무 큰 경우 `LLM_ATTACHMENT_FETCH=false`

### "HWP autofill의 missing 리스트가 비어있지 않음"
- 원인: `.env`의 `COMPANY_NAME/BUSINESS_NUMBER/CEO_NAME/ADDRESS` 누락
- 해결: 누락된 값 채우거나 요청 본문 `values`에 직접 주입

### "스케줄러가 안 돔"
- 증상: 30분 grade 갱신이 안 됨
- 확인: `docker compose logs api | grep scheduler` 또는 환경변수 `SCHEDULER_ENABLED`, `SCHEDULER_GRADE_ENABLED`, `GRADE_INTERVAL_MINUTES`
- 해결: 모두 `true`/양수로 설정, API 컨테이너 재기동

### "포트 충돌 (5433/3000/6333)"
- [§ 10 포트 충돌 override](#포트-충돌-override) 참고

### "alembic.upgrade.head 실패 — Postgres 권한"
- 증상: 컨테이너 부팅 시 `permission denied for schema`
- 해결: 도커 컴포즈는 `autojebi/autojebi/autojebi`로 자동 셋업이지만, 외부 DB 사용 시 해당 유저에게 CREATE 권한 부여

### "G2B 검색 0건" / "G2B 검색 502"
- 0건: 검색어가 너무 좁지 않은지, 검색 기간(`start_date`/`end_date`)이 휴일에 걸리지 않는지 확인
- 502 + 로그에 `serviceKey=`가 비어있고 `401 Unauthorized`: `DATA_GO_KR_API_KEY` 미주입. data.go.kr **"일반 인증키(Decoding)"** 값을 쓸 것(Encoding 키는 이중 인코딩으로 401). 도커는 `--env-file .env`로 주입.

### "도커 실행 시 HWP 에이전트 미연결" (`/documents/hwp-agent/health` → ok:false)
- 원인: 컨테이너 안의 `127.0.0.1`은 컨테이너 자신을 가리켜 호스트의 에이전트에 닿지 못함.
- v2 검증은 Windows 로컬 API/작업 실행기/HWP Worker와 공통 파일 경로를 사용한다. COM 서비스를 외부 인터페이스로 공개하지 않는다.
- `python -m api.hwp_worker --check`로 등록 상태를 확인한다. 실행·토큰·허용 폴더와 실연동 기준은 [HWP Worker 운영 안내](docs/hwp-worker.md)를 따른다.

### "키를 .env에 넣었는데 반영 안 됨"
- compose는 `--env-file`로 명시한 파일에서만 `${VAR}`를 치환한다. 레포 루트에 `.env`를 두고:
  ```bash
  docker compose --env-file .env -f infra/docker-compose.yml -f infra/docker-compose.override.yml up -d api frontend
  ```
- 컨테이너 env 확인(값 비노출): `docker exec autojebi-api sh -lc '[ -n "$ANTHROPIC_API_KEY" ] && echo set || echo EMPTY'`
- 주의: `DATABASE_URL`은 compose에 하드코딩되어 `.env` 값이 무시된다(의도된 동작).

### "Windows: git/python/node가 파일을 못 만듦 (No such file or directory)" — 제어된 폴더 액세스(CFA)
- 증상: OneDrive 경로(예: `C:\Users\<user>\Documents\...`)에서 `git add`/`alembic`/`npm`이 `index.lock`/파일 생성 실패(ENOENT/Access denied). 디스크·권한은 정상.
- 원인: Windows 보안의 **랜섬웨어 보호(제어된 폴더 액세스)** 가 Documents 등 보호 폴더에 대한 비신뢰 앱의 쓰기를 차단.
- 해결(관리자 PowerShell): 해당 실행 파일을 허용목록에 추가
  ```powershell
  Add-MpPreference -ControlledFolderAccessAllowedApplications "C:\Program Files\Git\mingw64\bin\git.exe"
  # 필요 시 python.exe / node.exe 도 동일하게 추가
  ```
  또는 작업 동안 CFA 일시 해제, 혹은 레포를 보호 폴더 밖으로 이동.

---

### 문서별 비교·작성 API (검증 화면)

비교·작성 목록은 공고 서류 검토에서 확인한 실제 항목만 사용한다. `PUT /v2/notices/{notice_no}/writing-plan`으로 원문 인용과 작성/첨부/전자제출 구분을 검증하며, 응답의 `writing_plan_current`가 참인 목록에 포함된 직접 작성 항목만 저장할 수 있다. 원문 변경 시 재확인이 필요하다. 고정 문서·공통 목차는 기본으로 생성하지 않는다.

`POST /v2/notices/{notice_no}/document-drafts`는 입력 버전과 중복방지 키를 받아 정성제안서·입찰서·기타서류 초안을 각각 저장한다. 회사 참고자료 인용과 웹 자료는 승인된 증빙이 아니며, `GET /v2/notices/{notice_no}/document-drafts/{draft_id}/download`로 Markdown 검토 초안을 받는다. 웹검색은 Google/네이버 새 탭 검색과 선택 자료 등록 방식이다. 응답의 `inputs.proposal_sections`에 `document_kind`, `title`, `references`, `web_references`가 추가된다. 상세 계약과 검증 결과는 [문서별 작성 작업대](docs/document-writing-ui-2026-09-11.md)를 따른다.

공고에 첨부된 HWPX 원본은 `form-fields` 조회와 `form-fillings` 저장·다운로드로 항목별 작성한다. `inputs.form_fillings`에 작성 내용과 출처를 보존하며 원본 서식 사본을 내보낸다. 상세 지원 범위와 검증은 [공고 원본 양식 작성](docs/original-notice-forms-2026-09-11.md)을 참고한다.

`GET /v2/notices/{notice_no}/form-fillings/{document_id}/review`는 검토할 작성본의 `version`, `output_sha256`, `unfilled_count`, `review_status`를 반환한다. 같은 경로의 `POST`는 해당 버전·파일 해시와 `approved`, `source_checked`, `content_checked`, `layout_checked`, `note`를 받아 사람의 양식 검토를 기록한다. `inputs.form_fillings[].review`에는 검토 의견·시각·입력 버전·입력/출력 해시가 보존된다. 승인에는 모든 확인과 빈칸 없는 작성본이 필요하며, 자료·작성 내용이 바뀌면 재검토한다. 자격증빙이나 제출 준비 승인은 별도다. [검토 경로 검증 기록](docs/original-form-review-2026-09-12.md)을 따른다.

### 공고 표시·ZIP 내부 양식 계약 (ADR 0002)

작업대 응답의 `notice_brief`는 정확한 원문 인용·위치·해시, 항목 판정, 전체 추출 경고, 동일 문서 그룹, 요약 검토 비교 상태를 제공한다. `extraction.presentation`은 기존 본문을 바꾸지 않는 표시 구조이며 JEV·양식 승인 해시에서 제외한다. 과거 자료에는 없어도 된다.

`POST /v2/notices/{notice_no}/source-display-reviews`는 reviewer 전용이며 `version`, `kind=absent|equivalent`, `label`, `document_ids`, `source_signature`, `original_checked=true`, `note`를 받는다. 서버 신원·시각과 파일 해시로 대조 기록을 저장한다. 부재 확인 범위는 전체 공고 원본이고, 동등성 확인은 두 원본이다. 증빙 승인이나 제출 준비 승인이 아니다.

`form-fields`는 ZIP 내부 HWPX를 별도 `document_id`로 반환한다. `parent_document_id`, `container_sha256`, `member_path`, `member_hashes`가 목록·저장 기록·내보내기 출처에 추가된다. 기존 `form-fillings` 저장/검토/다운로드를 재사용하며 부모 ZIP 변경 시 새 대상이다. 바이너리 HWP 자동기입은 지원하지 않는다. `source_needs.candidates`는 원문/내부 위치 후보이며 직접 확인 전 상태를 바꾸지 않는다. `SourceNeedResolution.locator`는 선택 필드다.

현재 양식의 `fillings`와 정정 전 참고용 `retired_fillings`를 구분한다. 과거 초안은 이력에서 읽을 수 있으며 새 대상에 자동 이관하지 않는다. [실공고 재검증 결과](docs/notice-document-provenance-e2e-2026-09-22.md)에 검토 사본·미완료 조건을 기록한다.
`GET /v2/hwp-worker`는 재시도 없이 전체 3초 기한을 적용한다. 브라우저는 본문 처리 포함 5초 후 취소하고 실패 backoff를 적용한다. 계약과 적합도 함수는 [ADR 0002](docs/adr/0002-notice-document-provenance.md)를 따른다.

## 14. 핵심 파일 맵

| 영역 | 파일 |
|------|------|
| 앱 부팅 | [api/main.py](api/main.py) |
| 설정 | [api/config.py](api/config.py), [.env.example](.env.example) |
| 인증 | [api/auth.py](api/auth.py) |
| 라우터 | [api/routers/notices.py](api/routers/notices.py), [api/routers/skus.py](api/routers/skus.py), [api/routers/ontology.py](api/routers/ontology.py) |
| 수집 | [api/collector/pipeline.py](api/collector/pipeline.py), [api/collector/scheduler.py](api/collector/scheduler.py) |
| 분석 (Claude) | [api/services/claude_analyzer.py](api/services/claude_analyzer.py), [api/llm/extractor.py](api/llm/extractor.py), [api/llm/prompts.py](api/llm/prompts.py), [api/llm/schemas.py](api/llm/schemas.py) |
| 첨부 처리 | [api/services/attachments.py](api/services/attachments.py) |
| 서류 자동화 (M10) | [api/services/document_automation.py](api/services/document_automation.py), [frontend/src/components/DocumentPreparationPanel.tsx](frontend/src/components/DocumentPreparationPanel.tsx), [frontend/src/lib/documentAutomation.ts](frontend/src/lib/documentAutomation.ts) |
| 서류 자동화 v2 (M11) | [api/services/uploads.py](api/services/uploads.py), [api/services/exporters.py](api/services/exporters.py), [frontend/src/components/UploadDocumentDialog.tsx](frontend/src/components/UploadDocumentDialog.tsx), [frontend/src/components/UploadsTable.tsx](frontend/src/components/UploadsTable.tsx), [frontend/src/components/ExportButtonGroup.tsx](frontend/src/components/ExportButtonGroup.tsx), `frontend/src/app/api/notices/[noticeNo]/documents/.../route.ts` (다운로드 프록시 2종) |
| 그레이딩 | [api/grading/scorer.py](api/grading/scorer.py), [api/grading/qualification.py](api/grading/qualification.py), [api/grading/price_table.py](api/grading/price_table.py), [api/grading/summarizer.py](api/grading/summarizer.py) |
| SKU/Qdrant | [api/sku/matcher.py](api/sku/matcher.py), [api/sku/qdrant_store.py](api/sku/qdrant_store.py) |
| 외부 클라이언트 | [api/services/hwp_agent_client.py](api/services/hwp_agent_client.py), [api/services/notifications.py](api/services/notifications.py) |
| 라우팅/상태 | [api/services/routing.py](api/services/routing.py), [api/services/status.py](api/services/status.py) |
| 프론트 페이지 | [frontend/src/app/notices/page.tsx](frontend/src/app/notices/page.tsx), [frontend/src/app/notices/[noticeNo]/page.tsx](frontend/src/app/notices/[noticeNo]/page.tsx), [frontend/src/app/admin/page.tsx](frontend/src/app/admin/page.tsx) |
| 프론트 액션/API | [frontend/src/lib/actions.ts](frontend/src/lib/actions.ts), [frontend/src/lib/api.ts](frontend/src/lib/api.ts) |
| 프론트 컴포넌트 | [frontend/src/components/](frontend/src/components/) (StatusBadge, ScoreBadge, CategoryBadge, NoticeActionsBar, *Dialog 등) |
| DB 스키마 | [db/bid_pipeline_schema.sql](db/bid_pipeline_schema.sql), [db/migrations/](db/migrations/) |
| 마이그레이션 | [alembic/](alembic/), [alembic.ini](alembic.ini) |
| 도커 | [infra/Dockerfile](infra/Dockerfile), [infra/Dockerfile.frontend](infra/Dockerfile.frontend), [infra/docker-compose.yml](infra/docker-compose.yml) |
| 테스트 | [tests/](tests/), [frontend/test/](frontend/test/), [frontend/e2e/](frontend/e2e/) |

---

> 새 기능 추가 시 이 문서도 함께 갱신할 것. 점수 공식·상태 전이·환경변수 기본값이 바뀌면 §4·§8·§11도 동기화.
# 사양 검증·하이브리드 검색 (검증 환경 전용)

v2 사양 JSON/수치·단위·인용 검사, 표 구조 보존, 사양 교정 ETag, PostgreSQL lexical + Neo4j + BGE-M3/Qdrant 검색을 추가했다.
기본 비활성이고 3002/8002에서만 검증한다. 검색 순위는 사람 승인이나 참가 결정이 아니다.
API·환경·실측 결과·공개 차단 조건은 [구현 및 검증 기록](docs/specification-search-2026-09-11.md)을 따른다.
