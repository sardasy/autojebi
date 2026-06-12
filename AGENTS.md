# AGENTS.md — 미림씨스콘 입찰 자동화 (autojebi)

> 이 파일은 Claude Code 등 코딩 에이전트와 사람 개발자가 이 저장소에서 작업할 때
> 참조하는 단일 지침서입니다. 8개 섹션 모두 길어도 1~2분 안에 스캔할 수 있도록 유지.

---

## 1. 목적과 범위

**autojebi**는 미림씨스콘(전력전자 유통: Typhoon HIL, PLECS, ABB IGBT/SCR/Diode, 퓨즈/커패시터/부스바)의
공공조달 입찰 업무를 자동화하는 시스템이다. 데이터 소스는 **KJEBI 알림메일** + **나라장터(G2B) OpenAPI** 두 가지뿐이며,
전체 워크플로우는 단일 상태머신(`bid_pipeline.status`)으로 묶인다:

```
수집(G2B/메일) → Claude 분석 → 3축 그레이딩 → 서류 자동화 → Teams/Slack 알림 → 진행 추적
```

### 범위
- **포함**: 공고 수집·중복제거·필터, Claude 적합도 분석, 사양/자격/가격 3축 점수, 서류 체크리스트·초안·Excel/HWP 내보내기, 알림 전송, 상태 추적 대시보드.
- **제외 (절대 금지)**: 실제 G2B 사이트에서의 투찰 클릭·금액 입력 자동화. 자세히 §7.

### 마일스톤 상태 (2026-06 기준)
| 단계 | 범위 | 상태 |
|---|---|---|
| 1차 | 수집·분석·알림·추적 (M1~M9) | 완료 — G2B OpenAPI 직결, claude-haiku-4-5 분석, 3축 그레이딩+Qdrant SKU 매칭, Next.js 프론트, X-API-Key 인증 |
| 2차 | 서류 자동화 + 메일 paste-UI + 경쟁사 추정 | M10/M11 완료 (체크리스트·초안·업로드·Excel/HWP). M12(메일 paste) 진행, M13(경쟁사) 계획. M14(ontology) base 완료 |
| 3차 | M14 제안서 자동 생성 (python-pptx) | 예정. **자동 트리거 금지 — Human-in-the-loop** |
| 4차 | M15 투찰 전략 추천 (낙찰률·경쟁사 패턴) | 예정. **AI는 추천만, 최종 결정·입력은 사람** |

### 모델 선택 정책 (비용 최적화)
요약/적합도는 `claude-haiku-4-5`, PDF 심층은 `claude-sonnet-4-5`, 제안서는 Opus 상위. LLM 호출은 중복제거·키워드 필터 게이트 통과 건에만, 공고당 1~2회로 제한.

---

## 2. 개발 환경 및 주요 명령어

### 백엔드 (Python 3.11+ / FastAPI)
```bash
pip install -e ".[dev]"                                  # 의존성 + dev 도구
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
│   ├── main.py · config.py · auth.py · db.py
│   ├── routers/        # notices.py 등 (수집·분석·서류·내보내기 엔드포인트)
│   ├── services/       # claude_analyzer · attachments · document_automation
│   │                   # uploads · exporters · notifications · hwp_agent_client · routing · status
│   ├── collector/      # g2b_client.py · pipeline.py · scheduler.py
│   ├── grading/        # scorer · qualification · price_table · summarizer (3축 M3/M5)
│   ├── llm/            # Claude 스키마·프롬프트 (mail_schemas 등)
│   ├── models/         # Pydantic 스키마 (notices.py, ontology.py)
│   ├── ontology/ · sku/  # M14 ontology + Qdrant SKU 매칭
├── frontend/           # Next.js 15 App Router (M7~M9)
│   ├── src/app/        # /notices, /notices/[noticeNo] 등
│   ├── src/components/ · src/lib/
│   └── e2e/            # Playwright 스펙
├── alembic/versions/   # 0001~0004 마이그레이션
├── db/                 # bid_pipeline_schema.sql + db/migrations/ (raw SQL 사본)
├── tests/              # pytest 백엔드 스위트
├── infra/              # docker-compose.yml, Dockerfile
├── n8n/                # 워크플로우 JSON (M12 placeholder)
├── data/               # uploads/, exports/ (gitignore — 런타임 산출물)
├── dashboard/ · tools/ # BI/CLI 보조
└── .github/workflows/  # ci.yml (ruff+pytest, vitest+next build)
```

상세 라우터·서비스 설명은 [README.md](README.md) §3~§7.

---

## 4. 품질 게이트

PR 머지 전 다음이 모두 그린이어야 한다:

- **백엔드**
  - `ruff check .` — 룰셋 `E,F,I,B,UP` (line-length 100, py311). 무시는 `E501,B008,B904`만.
  - `pytest -q` — 현재 361건 전체 통과.
  - alembic head 단일 유지 — `tests/test_alembic_metadata.py`, `tests/test_ontology_migration.py`.
- **프론트**
  - `npm run lint` (Next ESLint) · `npm run typecheck` 0 errors · `npm test` (Vitest) · `npm run e2e` 그린.
- **CI** ([.github/workflows/ci.yml](.github/workflows/ci.yml))
  - 백엔드 잡: ruff + pytest, Python 3.11.
  - 프론트 잡: vitest + `next build`, Node 20, `npm ci`.
- **DB 변경 시**: alembic 마이그레이션 동반 + `alembic upgrade head` 후 `pytest tests/test_alembic_metadata.py`.

---

## 5. 코딩 스타일 및 명명 규칙

- **Python**: 타입힌트 필수, Pydantic으로 모든 외부 입출력 스키마 정의. `ruff` + `black` 호환(line-length 100, target py311). 함수·변수 `snake_case`, 클래스 `PascalCase`, 라우터 모듈은 리소스 복수형(`notices.py`).
- **TypeScript**: strict 모드. interface `PascalCase`(`NoticeRecord`), 변수·함수 `camelCase`. API 응답 타입은 백엔드 Pydantic 모델과 1:1 동기화 — 예: [api/models/notices.py](api/models/notices.py) `NoticeRecord` ↔ [frontend/src/lib/api.ts](frontend/src/lib/api.ts) `NoticeRecord`.
- **DB 컬럼·JSON 키**: `snake_case`. **응답은 raw JSONB fallback 의존 대신 정규 컬럼 우선** (예: `org_name` / `base_price` / `open_date` / `close_date`).
- **LLM 응답 파싱**: 코드펜스(\`\`\`json) 제거 + 첫 `{` ~ 마지막 `}` 구간만 파싱. 실패 시 기본 객체로 fallback, **예외로 파이프라인을 죽이지 말 것**.
- **멱등성**: 모든 INSERT는 `ON CONFLICT (notice_no) DO UPDATE` 업서트. status 다운그레이드 금지(`analyzed` 이상 유지).
- **상태 전이**: 각 단계 노드는 자기 status 전이만 책임. `can_transition` 화이트리스트([api/services/status.py](api/services/status.py)) 외 점프 금지.
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
  - 인증: `API_KEY`(X-API-Key, 운영은 32+자 랜덤), `INTERNAL_API_KEY`(Server Action 주입)
  - 인프라: `DATABASE_URL`
  - HWP Agent: `HWP_AGENT_BASE_URL`, `HWP_AGENT_TOKEN`
  - 회사 정보: `COMPANY_NAME`, `COMPANY_BUSINESS_NUMBER`, `COMPANY_CEO_NAME`, `COMPANY_ADDRESS`

### 민감 정보 분리
- 견적·낙찰가·원가·사업자번호·대표자명 등 PII는 **코드 하드코딩 금지**. 모두 env 또는 DB.
- `COMPANY_*` 기본값은 [api/routers/notices.py](api/routers/notices.py) `_company_defaults`가 env에서만 읽음.

### 인증 게이트
- 모든 non-healthz 엔드포인트는 [api/auth.py](api/auth.py) `verify_api_key` 적용.
- **운영 환경에서 `API_KEY` 공란 금지** — 빈 값은 dev 전용 우회 모드.

### 외부 액션은 dry_run 기본
- Teams/Slack 알림 ([api/services/notifications.py](api/services/notifications.py))은 `dry_run=True`. 실 전송은 명시적 플래그.
- G2B 라이브 호출은 tenacity 3회 백오프 — **임의 루프로 호출 폭주 금지**.

### Human-in-the-loop 자동 트리거 금지 영역
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
- **DB 스키마 5층 동기화**: SQLAlchemy `Table` ([api/routers/notices.py](api/routers/notices.py) `bid_pipeline`) → Pydantic `NoticeRecord` ([api/models/notices.py](api/models/notices.py)) → `_row_to_record` 매퍼 → 프론트 `NoticeRecord` 타입 ([frontend/src/lib/api.ts](frontend/src/lib/api.ts)) → 컴포넌트. 한 층만 빠지면 응답에서 키가 사라지거나 TS 컴파일 실패.
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
