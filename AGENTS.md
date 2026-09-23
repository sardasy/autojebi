# AGENTS.md — 미림씨스콘 입찰 자동화 (autojebi)

> 이 파일은 Claude Code 등 코딩 에이전트와 사람 개발자가 이 저장소에서 작업할 때
> 참조하는 단일 지침서입니다. 8개 섹션 모두 길어도 1~2분 안에 스캔할 수 있도록 유지.

---

## 1. 목적과 범위

검증 화면의 기본 동선은 공고 찾기 → 공고 서류 검토 → 기존 작성자료와 비교·작성 → 서류 확인이다.
`company_reference`는 참고용 기존 작성자료이며 회사/제품 증빙으로 승인하거나 재분류하지 않는다.
비교 초안은 `/v2/notices/{notice_no}/reference-drafts`에서 입력 버전과 인용을 검증해 검토 대기로 저장한다.
섹션 검토 `approved=null`은 초안 저장, `true/false`는 승인/반려다. 동일 본문 재추출은 검토를 초기화하지 않으며 실제 변경 문서의 연결 대상만 재검토한다. PDF 페이지 미리보기와 검증 기록은 `docs/document-workbench-ux-2026-09-08.md`를 따른다.
마감 경과·마감일시/시간대 미확인 공고는 제출 준비 완료로 승인하지 않는다. 검토용 다운로드와 과거 이력은 보존한다. 실제 공고 준비 결과는 `docs/plecs-R26BK01706511-preparation-2026-09-08.md`를 따른다.
그레이딩·SKU·알림은 호환 API로 보존하되 새 기본 화면에 재노출하지 않는다. 상세는 `docs/document-loop-2026-09-07.md`.

**autojebi**는 미림씨스콘(전력전자 유통: Typhoon HIL, PLECS, ABB IGBT/SCR/Diode, 퓨즈/커패시터/부스바)의
공공조달 입찰 업무를 자동화하는 시스템이다. 데이터 소스는 **KJEBI 알림메일** + **나라장터(G2B) OpenAPI** 두 가지뿐이며,
v2 검토 작업대는 참가 결정, 작업 실행, 입력 버전, 사람 검토를 분리한다.
`bid_pipeline.status`는 기존 API 호환용이며 v2 참가 결정이나 제출 준비 판정의 근거로 사용하지 않는다:

```
수집(G2B/메일) → Claude 분석 → 3축 그레이딩 → 서류 자동화 → Teams/Slack 알림 → 진행 추적
```

v2는 `/workspace` 및 `/v2/*`에서 검증 중이다. `python -m api.workspace.worker`는 별도 프로세스이며
PostgreSQL 영속 큐를 사용한다. 새 입력은 버전 증가, 과거 결과/승인은 이력 보존, 최신 버전 승인만 유효하다.
검증 실행은 `python -m api.workspace.supervisor --split`으로 local(verify/excel/package)과 external을 분리한다.
경로별 잠금·완료 기록·복구·health를 유지하고 기존 all 실행기와 혼용하지 않는다. HWP 단일 COM 큐는 그대로 유지한다.
인용 실패 작업은 실패로 보존하고 `quote_diagnostics`의 구조 검증 후보만 담당자가 채택한다. 채택 API는 현재 버전·원문 해시·정확한 위치·중복방지 키를 확인하며 승인하지 않는다.
`source_needs`는 별도 과업/제안요청 자료의 확보·해당 여부를 관리한다. 같은 공고서 두 형식을 별도 필요 문서 확보로 계산하지 않으며 미해결은 제출 준비를 차단한다.
현재 공고 복구와 검증 범위는 `docs/current-notice-recovery-2026-09-10.md`를 따른다.
LLM 장애는 미평가이며 0점/비관련으로 확정하지 않는다. 업로드·자동 분류는 증빙 승인으로 간주하지 않는다.
알림은 업무 상태를 바꾸지 않고 v2에서는 dry-run만 제공한다. 실제 HWP 및 공고 3건 검증 전 기본 화면 전환 금지.
자세한 실행/전환 조건은 `docs/workspace-v2-implementation.md`를 따른다.
Windows HWP Worker는 `api/hwp_worker`에 둔다. `python -m api.hwp_worker --check`는 읽기 전용 진단,
실행은 동일 명령에서 `--check`를 뺀다. 32자 이상 토큰, 허용 폴더, 단일 COM 스레드/전역 mutex 필수.
레지스트리 자동 등록, 보안 모듈 우회, 사용자의 한글 프로세스 전체 종료 금지. 저장값 검증과 실제 배치 검토는 별개다.
HWP 서식 모드는 기존 `fields`와 `proposal_layout_v1`을 구분한다. 템플릿 제작은 인증된 Worker의 `/document/create-template`와 `python -m api.hwp_fields prepare-template`만 사용하며 별도 직접 COM 작성기를 만들지 않는다. 시간 초과 후 신규·대기 요청을 차단하고 늦은 응답/재시작으로 복구 표식을 해제하지 않는다. 실생성 결과와 남은 담당자 검토는 `docs/hwp-layout-implementation-2026-09-10.md`를 따른다.

### 범위
- **포함**: 공고 수집·중복제거·필터, Claude 적합도 분석, 사양/자격/가격 3축 점수, 서류 체크리스트·초안·Excel/HWP 내보내기, 알림 전송, 상태 추적 대시보드.
- **제외 (절대 금지)**: 실제 G2B 사이트에서의 투찰 클릭·금액 입력 자동화. 자세히 §7.

### 마일스톤 상태 (2026-09-12 기준)
| 단계 | 범위 | 상태 |
|---|---|---|
| 1차 | 수집·분석·알림·추적 (M1~M9) | 완료 — G2B OpenAPI 직결, claude-haiku-4-5 분석, 3축 그레이딩+Qdrant SKU 매칭, Next.js 프론트, X-API-Key 인증 |
| 2차 | 서류 자동화 + 라이브 검색 (M10~M13) | M10/M11 완료 (체크리스트·초안·업로드·Excel/HWP). M13 G2B 라이브 검색 완료. M12(메일 paste)는 `/admin` paste 폼까지, M13(경쟁사 추정)은 미착수 |
| 3차 | M14 HWP 제안서 + v2 작업대 | 구현은 되어 있으나 **운영 전환 미완료**: `api/workspace`(영속 큐·입력 버전·사람 검토), `api/hwp_worker`(단일 COM 큐), 규격 검색(`api/specifications`, opt-in). 차단 조건은 아래 "운영 전환 잔여 조건". **자동 트리거 금지 — Human-in-the-loop** |
| 4차 | M15 투찰 전략 추천 (낙찰률·경쟁사 패턴) | 예정. **AI는 추천만, 최종 결정·입력은 사람** |

### 운영 전환 잔여 조건 (2026-09-13 갱신, 완료 전 기본 화면 전환 금지)
- HWP Worker 복구·CRLF 실파일 재검증은 완료했다. 실제 공고 최종본 검토와 운영 전환은 별도 — `docs/hwp-recovery-e2e-2026-09-13.md`.
- 실제 공고 3~5건 + 담당자 최종본 대조 (기존 "완료" 표기는 구현 이력이지 실공고 검증이 아님).
- 규격 검색: 사람 채점 홀드아웃 확보 전 공개·운영 반영 금지 — `docs/specification-search-2026-09-11.md`.
- 요구사항 등록→누락검사 루프는 검증용 공고에서 확인했으며 실제 공고 누락률과 담당자 최종본 대조는 남아 있다. OCR(Tesseract+kor) 실검증, 전용 Windows 인스턴스, 백업·복구 리허설도 남아 있다.
- v2 개인 인증·독립 역할·승인자 기록은 opt-in 구현/격리 테스트 완료. 실사용자 등록·토큰 발급·역할 배정과 팀 승인 리허설은 미완료이며 기존 호환 API의 공유 키 접근은 별도 제한해야 한다 — `docs/workspace-identity-2026-09-13.md`.

### 모델 선택 정책 (비용 최적화)
v2 분석/제안서는 `WORKSPACE_LLM_PROVIDER=anthropic|gemini|openai`로 선택한다(기본 anthropic).
Gemini는 `GOOGLE_API_KEY`, `GEMINI_MODEL`을 사용하고 Claude의 `PROPOSAL_MODEL`(`settings.proposal_model`)은 적용하지 않는다.
세 공급자 모두 `api/workspace/providers.py`의 `prepare_request`/`generate`를 거친다. 새 LLM 호출 경로에서 `anthropic.Anthropic`을 직접 생성하지 말 것 — 호출 한도·재사용 기록이 빠진다.
OpenAI는 `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_MAX_OUTPUT_TOKENS`를 사용하며 Responses API의 strict JSON Schema와 `store=false`를 적용한다. 기존 비교 초안은 유료 호출로 전환하지 않는다.
공급자/모델 변경은 호출 한도를 초기화하지 않으며 자동 fallback/재시도하지 않는다.
등록된 키와 실제 연결 검증은 구분한다. 기존 호환 API와 참고자료 비교 초안은 변경하지 않는다.
요약/적합도는 `claude-haiku-4-5`, PDF 심층은 `claude-sonnet-4-5`, 제안서는 Opus 상위. LLM 호출은 중복제거·키워드 필터 게이트 통과 건에만, 공고당 1~2회로 제한.
v2 비용 게이트는 같은 원문·회사·증빙 내용에 대해 입력 버전을 넘어 합산 2회이며, 정확히 같은 정상 요청은 재사용한다.
자료가 바뀌지 않은 검토/판정 수정으로 호출 한도를 새로 부여하지 않는다. 그레이딩은 LLM 호출을 하지 않는다.

---

## 2. 개발 환경 및 주요 명령어

### 백엔드 (Python 3.11+ / FastAPI)
```bash
python -m venv .venv && .venv/Scripts/activate           # 로컬 venv (.venv는 gitignore). 시스템 파이썬에 직접 설치하지 말 것
pip install -e ".[dev]"                                  # 의존성 + dev 도구 (규격 검색: ".[dev,spec-search]", HWP Worker: ".[dev,hwp-worker]")
uvicorn api.main:app --reload --port 8001                # 로컬 API 서버
alembic upgrade head                                     # 마이그레이션 적용 (컨테이너에선 자동)
alembic revision -m "0005_describe_change"               # 새 마이그레이션 작성
python -m api.ontology seed                              # 온톨로지/SKU 시드
pytest -q                                                # 전체 백엔드 테스트
pytest tests/test_notices_search.py -q                   # 단일 파일
```

### 프론트 (Next.js 15 / npm — `frontend/`)
```bash
cd frontend && npm ci                                    # lockfile 고정 설치
npm run dev                                              # 3000번 dev 서버
npm run build && npm run start                           # 프로덕션 빌드 검증
npm run lint                                             # Next ESLint
npm run typecheck                                        # tsc --noEmit
npm test                                                 # Vitest 단위
npm run e2e                                              # Playwright (dev:3000, docker:3001)
```

### Docker 풀스택
```bash
cp .env.example .env                                     # 시크릿 채워서 .env (커밋 금지)
docker compose -f infra/docker-compose.yml up -d         # Postgres(5433) + Qdrant(6333) + API(8001) + Frontend(3000)
# API 코드만 재기동 (override 포함):
docker compose -f infra/docker-compose.yml -f infra/docker-compose.override.yml up -d --build api
```

---

## 3. 프로젝트 구조

```
autojebi/
├── api/                # FastAPI 코어 (Python 3.11)
│   ├── main.py · config.py · auth.py
│   ├── db/             # 엔진(__init__) · tables.py(공용 Table·단일 metadata — ADR 0001)
│   ├── routers/        # notices.py 등 (수집·분석·서류·내보내기 엔드포인트)
│   ├── services/       # claude_analyzer · attachments · document_automation
│   │                   # uploads · exporters · notifications · hwp_agent_client · routing · status
│   ├── collector/      # g2b_client.py · pipeline.py · scheduler.py
│   ├── grading/        # scorer · qualification · price_table · summarizer (3축 M3/M5)
│   ├── llm/            # Claude 스키마·프롬프트 (mail_schemas 등)
│   ├── models/         # Pydantic 스키마 (notices.py, ontology.py)
│   ├── ontology/ · sku/  # M14 ontology + Qdrant SKU 매칭
│   ├── workspace/      # v2 작업대: service · executors/(작업 종류별) · storage · errors · worker · supervisor · providers(anthropic/gemini/openai) · hwp_* · llm_usage
│   ├── parsing/        # 순수 파서·검증(PDF/HWPX/XLSX/ZIP 추출, HWP 산출물 검증) — workspace·routers import 금지
│   ├── hwp_worker/     # Windows 한글 COM Worker (별도 FastAPI, 토큰 인증, 단일 COM 큐, recovery)
│   ├── hwp_fields/     # HWP 템플릿/필드 매핑 CLI (prepare-template)
│   ├── specifications/ # 규격 검증 + 하이브리드 검색 (opt-in: SPEC_SEARCH_ENABLED)
├── frontend/           # Next.js 15 App Router (M7~M9)
│   ├── src/app/        # /notices, /notices/[noticeNo] 등
│   ├── src/components/ · src/lib/   # v2 작업대: WorkspaceClient(셸) + components/workspace/(useWorkspace·derive·탭) · lib/workspace.ts(workspaceFetch)
│   └── e2e/            # Playwright 스펙
├── alembic/versions/   # 0001~0017 마이그레이션 (단일 head — 0010b는 리비전 ID 길이 우회용 no-op)
├── db/                 # bid_pipeline_schema.sql (2025-06 스냅샷 — Alembic이 원본, 참고용일 뿐 갱신 안 됨)
├── tests/              # pytest 백엔드 스위트
├── infra/              # docker-compose.yml, Dockerfile
├── n8n/                # 워크플로우 JSON (M12 placeholder)
├── data/               # uploads/, exports/, workspace/, templates/*.hwp (gitignore — 런타임 산출물)
├── tmp/ · output/ · chroma_db/  # 로컬 스크래치 (전부 gitignore — 재사용할 스크립트는 tools/로 옮겨서 커밋)
├── dashboard/ · tools/ # BI/CLI 보조
└── .github/workflows/  # ci.yml (ruff+pytest, vitest+next build)
```

상세 라우터·서비스 설명은 [README.md](README.md) §3~§7.

---

## 4. 품질 게이트

PR 머지 전 다음이 모두 그린이어야 한다:

- **백엔드**
  - `ruff check .` — 룰셋 `E,F,I,B,UP` (line-length 100, py311). 무시는 `E501,B008,B904`만.
  - `pytest -q` — 전체 통과 (2026-09-11 기준 1,3xx건; Postgres/HWP/규격검색 라이브 테스트는 env 게이트로 skip).
  - alembic head 단일 유지 — `tests/test_alembic_metadata.py`, `tests/test_ontology_migration.py`.
- **프론트**
  - `npm run lint` (Next ESLint) · `npm run typecheck` 0 errors · `npm test` (Vitest) · `npm run e2e` 그린.
- **CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml))
  - 프론트 잡: lint + typecheck + vitest + `next build`, Node 20, `npm ci`.
  - 백엔드 잡: ruff + `lint-imports`(ADR 0001) + pytest.
- **모듈 경계**: `lint-imports` — ADR 0001 계약(`api.workspace` ↛ `api.routers`, `api.workspace` ↛ fastapi 직접 import, `api.parsing` ↛ workspace/routers/fastapi). `tests/test_architecture.py`는 함수 안 `api.*` import 예산, 파일 크기(py 600줄, ts/tsx 300줄·24KB; 기존 초과 파일은 현재 크기가 예산), Anthropic 클라이언트 생성 위치(providers 경로 + 동결된 v1 5곳)를 검사하며 예산은 감소 방향으로만 바꾼다. 프론트 UI 코드는 `fetch`를 직접 쓰지 않고 `lib/workspace`(v2)·`lib/api`(v1)를 쓴다(ESLint). 새 작업 종류는 `api/workspace/executors/<kind>.py` + 디스패처에 추가한다. API 스키마 변경 시 `UPDATE_OPENAPI_SNAPSHOT=1 pytest tests/test_openapi_snapshot.py` 후 diff 검토.
- **DB 변경 시**: alembic 마이그레이션 동반 + `alembic upgrade head` 후 `pytest tests/test_alembic_metadata.py`.

---

## 5. 코딩 스타일 및 명명 규칙

- **Python**: 타입힌트 필수, Pydantic으로 모든 외부 입출력 스키마 정의. `ruff` + `black` 호환(line-length 100, target py311). 함수·변수 `snake_case`, 클래스 `PascalCase`, 라우터 모듈은 리소스 복수형(`notices.py`).
- **TypeScript**: strict 모드. interface `PascalCase`(`NoticeRecord`), 변수·함수 `camelCase`. API 응답 타입은 백엔드 Pydantic 모델과 1:1 동기화 — 예: [api/models/notices.py](api/models/notices.py) `NoticeRecord` ↔ [frontend/src/lib/api.ts](frontend/src/lib/api.ts) `NoticeRecord`.
- **DB 컬럼·JSON 키**: `snake_case`. **응답은 raw JSONB fallback 의존 대신 정규 컬럼 우선** (예: `org_name` / `base_price` / `open_date` / `close_date`).
- **LLM 응답 파싱**: 코드펜스(\`\`\`json) 제거 + 첫 `{` ~ 마지막 `}` 구간만 파싱. 실패 시 기본 객체로 fallback, **예외로 파이프라인을 죽이지 말 것**.
- **멱등성**: 모든 INSERT는 `ON CONFLICT (notice_no) DO UPDATE` 업서트. status 다운그레이드 금지(`analyzed` 이상 유지).
- **상태 전이**: 기존 API는 `can_transition`/`advance_status` 호환 규칙을 유지한다. v2 실행 상태는 `workspace_jobs`, 참가 결정은 `notice_workspaces.decision`이 관리하며 외부 작업이 참가 결정을 변경하면 안 된다.
- **에러 처리**: 외부 API 호출(G2B, Teams, Slack)은 타임아웃·재시도(tenacity 3회 백오프). 한 건 실패가 배치를 막지 않게 item-단위 try/except + `errors[]` 누적.
- **언어**: 코드·주석은 영/한 혼용 허용. 사용자 대면(알림·UI 라벨)은 한국어. (TyphoonTest IDE 외부 스크립트는 순수 ASCII — 본 저장소엔 해당 없음.)

라우팅 규칙(카테고리→담당자, fit_score→상태)은 코드 상수다: [api/services/routing.py](api/services/routing.py), [api/services/status.py](api/services/status.py).

---

## 6. 테스트 지침

- **백엔드 단위/통합**: pytest. SQLite in-memory + `StaticPool` 패턴 — fixture 참고: [tests/test_notices_search.py](tests/test_notices_search.py)의 `sqlite_engine` / `client`. `monkeypatch`로 `settings.api_key=""` 인증 비활성.
- **회귀 의무**: 새 응답 키나 컬럼 추가 시, 응답 본문에 키 존재 + 시드값 노출을 확인하는 회귀 테스트 1건 필수 (예: `test_list_exposes_g2b_columns_top_level`).
- **그레이딩/외부 의존**: G2B 자격 API는 `tests/test_qualification_live.py`로 라이브 검증, 나머지는 mock. Qdrant 미가동 시 spec=0.0 silent fallback.
- **프론트 단위**: Vitest + jsdom. `NoticeRecord` 모킹 시 모든 nullable 필드를 `null`로 명시 — 생략하면 TS strict에서 `undefined` 미스매치.
- **E2E**: Playwright. baseURL은 dev 3000 / docker 3001. 스펙 패턴은 [frontend/e2e/notices-flow.spec.ts](frontend/e2e/notices-flow.spec.ts).
- **알려진 이슈**: `tests/test_g2b_client.py` 일부는 네트워크 의존(라이브 호출). 새 alembic head 추가 시 `tests/test_ontology_migration.py::test_alembic_chain_includes_*` 함께 갱신.

---

## 7. 보안 · 비밀번호 · 위험한 작업 금지

### 시크릿 관리
- `.env`는 `.gitignore` 등록됨. **`.env.example`만 추적**, 실제 값은 절대 커밋 금지.
- 필수 env (전체 목록은 [.env.example](.env.example)):
  - LLM/RAG: `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `QDRANT_URL`, `QDRANT_API_KEY`
  - 외부 API: `DATA_GO_KR_API_KEY`(G2B), `TEAMS_WEBHOOK_URL`, `SLACK_WEBHOOK_URL`
  - 인증: `API_KEY`(X-API-Key, 운영은 32+자 랜덤), `INTERNAL_API_KEY`(Server Action 주입), `APP_ENV`(production이면 API_KEY 필수)
  - v2 개인 인증(opt-in): `WORKSPACE_AUTH_ENABLED`, `WORKSPACE_AUTH_USERS` 또는 `WORKSPACE_AUTH_REGISTRY` 중 하나. registry에는 개인 식별 정보·역할·토큰 SHA-256만 저장하며 원문 토큰과 registry를 커밋하지 않는다.
  - 인프라: `DATABASE_URL`
  - HWP Agent: `HWP_AGENT_BASE_URL`, `HWP_AGENT_TOKEN`
  - 회사 정보: `COMPANY_NAME`, `COMPANY_BUSINESS_NUMBER`, `COMPANY_CEO_NAME`, `COMPANY_ADDRESS`

### 민감 정보 분리
- 견적·낙찰가·원가·사업자번호·대표자명 등 PII는 **코드 하드코딩 금지**. 모두 env 또는 DB.
- `COMPANY_*` 기본값은 [api/routers/notices.py](api/routers/notices.py) `_company_defaults`가 env에서만 읽음.

### 인증 게이트
- 모든 non-healthz 엔드포인트는 [api/auth.py](api/auth.py) `verify_api_key` 적용.
- **운영 환경에서 `API_KEY` 공란 금지** — 빈 값은 dev 전용 우회 모드. `APP_ENV=production`이면 [api/main.py](api/main.py) `enforce_auth_policy`가 공란 기동을 거부하고, 그 외 환경은 경고 로그만 남긴다.
- `WORKSPACE_AUTH_ENABLED=true`인 `/v2/*`는 GET 포함 개인 Bearer 인증을 추가 검증한다. 공유 키만으로 우회할 수 없으며 설정 오류·미등록·비활성 계정은 차단한다. 비활성 기본값은 로컬 검증 호환용이며 팀 배포 전에 실사용자 발급과 역할 점검을 완료한다.
- 역할은 독립: 작성/초안은 `writer`, 문서·요구사항·섹션·원본 양식·생성물 검토는 `reviewer`, 패키지 최종 `ready`는 `approver`, `viewer`는 조회만 허용한다. 신규 승인 경로는 [api/workspace/identity.py](api/workspace/identity.py) 역할 분류와 회귀 검증을 함께 추가한다.
- 원문 부재·동일 문서 대조 기록(`/source-display-reviews`)도 `reviewer`만 저장한다. 파일 해시 집합·확인 범위를 검증하며 증빙/제출 승인으로 사용하지 않는다. 표시 정보와 ZIP 작성 대상의 출처 규칙은 [ADR 0002](docs/adr/0002-notice-document-provenance.md)를 따른다.
- 승인자 식별은 서버 인증 ContextVar에서 `service.audit`의 `details.actor`로 기록한다. 클라이언트 이름/역할/헤더를 신뢰하거나 기존 기록에 신원을 소급 생성하지 않는다. Next는 HttpOnly·SameSite 쿠키와 변경 요청 Origin 검증을 사용한다.
- v2 개인 인증은 기존 호환 API의 공유 키 정책을 바꾸지 않는다. SSO/MFA·서버 세션 저장소·전체 시스템 RBAC 완료로 표시하지 않는다. 설정과 범위는 [docs/workspace-identity-2026-09-13.md](docs/workspace-identity-2026-09-13.md)를 따른다.

### 외부 액션은 dry_run 기본
- Teams/Slack 알림 ([api/services/notifications.py](api/services/notifications.py))은 `dry_run=True`. 실 전송은 명시적 플래그.
- G2B 라이브 호출은 tenacity 3회 백오프 — **임의 루프로 호출 폭주 금지**.

### Human-in-the-loop 자동 트리거 금지 영역
- 기본 HWP 검증 골격은 SHA 출처 기록을 보존하며 파일명·서식 키 변경으로 제출용 승인 대상이 되지 않는다. 기존 파일은 자동 분류하지 않고 실제 양식 교체 후 로컬 관리자의 원본 출처·해시·사람 확인을 명시 등록한다. 출처 확인과 생성물 배치 승인·최종 준비 승인은 별개다 — [등록·이관 절차](docs/hwp-template-provenance-2026-09-20.md).
- **M14 제안서 생성** — 담당자가 수동 트리거한 건만.
- **M15 투찰가 추천** — AI는 제안만, 최종 투찰 결정·입력은 반드시 사람이.
- **실제 G2B 투찰 클릭 자동화 절대 금지**. 정보 수집·서류 준비·체크리스트 검증까지만 보조.

### 외부 소스 ToS
- **KJEBI 직접 크롤링 금지** (ToS 위반·차단 위험). 알림메일 수신 + G2B OpenAPI 조합만 사용.
- M12 메일 paste-UI는 **사용자가 직접 paste**한 본문만 받음.

### 위험 도구 / 파괴적 작업
- HWP Agent 로컬 Windows 프로세스 호출 ([api/services/hwp_agent_client.py](api/services/hwp_agent_client.py))은 `HWP_AGENT_TOKEN` 필수.
- alembic 마이그레이션은 파괴적 가능성. 항상 staging 선행 + `alembic downgrade -1` 가능한 형태로 작성.
- `--no-verify`, `git push --force`, `git reset --hard` 등 destructive 명령은 **사용자 명시 승인 후에만**.

### 런타임 산출물
- `data/uploads/`, `data/exports/`, `*.log` 는 gitignore. 절대 커밋 금지.

---

## 8. 작업 방식 가이드

- **변경 단위**: 한 PR = 한 마일스톤 슬라이스. 커밋·PR 제목은 `M14: ...` 같은 prefix로 통일.
- **DB 스키마 5층 동기화**: SQLAlchemy `Table` ([api/db/tables.py](api/db/tables.py) `bid_pipeline`; `api.routers.notices`는 호환용 re-export) → Pydantic `NoticeRecord` ([api/models/notices.py](api/models/notices.py)) → `_row_to_record` 매퍼 → 프론트 `NoticeRecord` 타입 ([frontend/src/lib/api.ts](frontend/src/lib/api.ts)) → 컴포넌트. 한 층만 빠지면 응답에서 키가 사라지거나 TS 컴파일 실패.
- **새 status 추가**: [api/services/status.py](api/services/status.py) `can_transition` 화이트리스트 갱신 + 상태 전이 테스트 추가.
- **새 ingest 경로**: 항상 `ON CONFLICT (notice_no) DO UPDATE`. 기존 status가 `analyzed` 이상이면 다운그레이드 금지.
- **외부 API 실패**: 한 건 실패가 배치 전체를 막지 않도록 item 단위 처리. 502는 HTTPException으로 분류해 상위에 전파.
- **컨테이너 재기동 워크플로우**: API 코드 변경 후 `docker compose ... up -d --build api`. DB 마이그레이션은 컨테이너 entrypoint에서 `alembic upgrade head` 자동.
- **PR 전 셀프체크**: ① `ruff check .` ② `pytest -q` ③ 프론트 변경 시 `npm run typecheck` + `npm test` ④ 응답 스키마 변경 시 [README.md](README.md) §7 갱신 ⑤ 본 AGENTS.md §7 갱신이 필요한 정책 변경이면 같이 PR에 포함.
- **에이전트 도구 사용 가이드**
  - 코드베이스 탐색: Explore agent (3개 이하 병렬).
  - 광범위 리뷰: `/code-review` 슬래시 커맨드.
  - 변경 단위가 크면 plan 모드로 사전 검토 후 ExitPlanMode → 구현.
  - **임의로 destructive 명령 실행 금지** — 사용자 명시 승인 필요.
  - 시크릿/PII가 포함될 수 있는 출력은 코드/로그에 남기지 말 것.
# 사양 검색 검증 지침 (2026-09-11)

`api/specifications`는 `SPEC_SEARCH_ENABLED=true`와 `SPEC_SEARCH_ENV=validation`에서만 활성화한다.
PostgreSQL이 원본이며 Neo4j/Qdrant는 버전별 검색 투영이다. `spec_index`는 기존 external 실행기에서만 처리한다.
수치 허용오차 기본 0, 모델/프로토콜 식별자 구두점 보존, 인용·원본 해시·입력 버전·claim token 검사를 우회하지 않는다.
RRF는 세 축 동일 가중치 `sum(1/(60+rank))`이며 증빙/참고/불충족 그룹을 분리한다. 검색으로 참가 결정·승인을 변경하지 않는다.
실제 검토된 홀드아웃 없는 공개 금지. `tools/spec_validation_runtime.py`는 별도 localhost 저장소만 사용하며 운영 DB에 적용하지 않는다.
현재 적용 범위와 잔여 조건은 `docs/specification-search-2026-09-11.md`를 따른다.
