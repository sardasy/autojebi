# autojebi 전체 리팩토링 계획 — 10단계 파이프라인

> 상태: **진행 중** (2026-09-18). 1단계 페르소나 확정(박정비), 3단계 지표를 대표 변경 시나리오 방식으로 확정, R0~R3 완료.
> 9단계 ADR: [docs/adr/0001-v2-module-boundaries.md](../adr/0001-v2-module-boundaries.md). 지표 측정: `python tools/change_amplification.py`.

## Context
v2 검토 작업대는 구현은 되어 있지만 운영 전환이 막혀 있다(실공고 3~5건 대조, HWP 실검증 등 — AGENTS.md §1). 남은 전환 작업을 하려면 v2 코드를 계속 고쳐야 하는데, 지금 구조에서는 한 번 고칠 때마다 건드려야 하는 곳이 너무 많다.
- 백엔드: `api/routers/notices.py`(3,454줄)가 공용 DB 테이블 18개를 소유하고 있고 v2 전체가 여기에 의존한다. `workspace/execution.py`(933), `service.py`(794), `routers/workspace.py`(774)는 HTTP·SQL·도메인 로직이 한곳에 섞여 있고, 함수 안에서만 하는 import가 64개다. PDF·HWPX 파싱 경로는 4~5중으로 중복돼 있다.
- 프론트: `WorkspaceClient.tsx`(63KB)에 useState 27개와 인라인 API 호출이 몰려 있다. API를 부르는 방식이 세 가지이고, 타입은 백엔드에서 손으로 복제했다. 아무도 쓰지 않는 컴포넌트가 9개(약 1,400줄) 있다.

사용자 지시에 따라 리팩토링 자체를 10단계 파이프라인으로 설계한다. v1 API와 화면은 **동작을 그대로 두고 구조만 정리한다**. 착수 전에 **현재 미커밋 변경을 먼저 커밋한다**.

산출 문서: `docs/refactor/2026-09-18-refactor-pipeline.md`(1~8단계, 10단계), `docs/adr/0001-v2-module-boundaries.md`(9단계).

---

## 0. 기준선 확보 (선행)
- 미커밋 변경을 커밋한다. 수정 파일 40여 개와 신규 모듈 `identity`, `output_plan`, `requirement_candidates`, `runtime_version` 및 그 테스트가 대상이다. 커밋 메시지는 `v2: identity·output_plan·requirement_candidates·runtime_version` 기준으로 쓰고, 성격이 다른 변경이 섞여 있으면 커밋을 나눈다.
- 기준값을 기록한다: `ruff check .`, `pytest -q` 통과 수, `npm run typecheck`, `npm test`, mock e2e 통과 수.

**기준값 기록 (2026-09-18, 브랜치 `refactor/v2-boundaries`, 커밋 `23196ad`)**
| 항목 | 결과 |
|---|---|
| `ruff check .` | 통과 |
| `pytest` | **1,740 passed, 17 skipped** (86s). 외부 플러그인을 끄고 돌릴 때는 `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 pytest -p asyncio`로 실행해야 한다. `-p asyncio`를 빼면 `test_fetch_qualifications.py`의 4건이 실패한다 |
| `npm run typecheck`, `npm run lint` | 0 errors |
| Vitest | **41 files / 281 tests passed** |
| mock e2e | 미측정. R1 전에 dev 서버를 띄우고 측정한다 |
| 변경 증폭 | 시나리오 기준 **필수 수정 중앙값 4파일**, 접점 중앙값 10파일 (3단계 표). 커밋 기반은 3건·중앙값 18파일로 보조 관찰만 한다 |

## 1. 문제
| 항목 | 내용 |
|---|---|
| 페르소나 | **박정비** (2026-09-18 확정). 미림씨스콘 사내 개발자 겸 운영자. 혼자서 v2 운영 전환 잔여 조건을 처리한다 |
| 불편 | 작업대 기능 하나를 고치려면 v1 라우터, service, execution, router, WorkspaceClient를 동시에 건드려야 한다. 순환 import를 피하려고 함수 안에서 import한다 |
| 손실 | 전환 작업이 늦어진다. 파싱 경로가 중복돼 같은 버그를 여러 곳에서 고쳐야 하고, 회귀 위험이 크다 |
| 현재 대안과 한계 | 파일 단위 땜질과 테스트 추가뿐이다. 경계 규칙이 없어서 결합도가 계속 늘어난다 |
| 문제 문장 | "박정비는 v2 작업대 동선을 고칠 때마다 v1 라우터와 거대 모듈을 함께 수정해야 해서, 운영 전환 잔여 조건을 안전하고 빠르게 처리하지 못한다." |

완료 조건: 페르소나 이름과 문제 문장을 사용자가 확정한다. → **완료** (2026-09-18)

## 2. 가치·지불
- 가치 문장: "v2 핵심 동선(공고 찾기 → 서류 검토 → 비교·작성 → 서류 확인)의 변경이 한 모듈 경계 안에서 끝나게 해서, 전환 잔여 조건 처리 속도와 안전성을 높인다."
- 지불 주체: 미림씨스콘 내부. 비용은 개발 시간뿐이다.
- 과금 가설: 리팩토링에 약 2~3주를 타임박스로 쓴다. 이후 전환 작업 1건당 수정 범위가 줄어드는 것으로 회수된다고 본다. 타임박스를 넘으면 10단계 판단 매트릭스로 넘어간다.

완료 조건: 가치 문장 확정.

## 3. 지표
- **핵심 지표(1개)**: 대표 변경 시나리오 5건의 **필수 수정 파일 수 중앙값**(변경 증폭). 대상은 `api/`와 `frontend/src`의 테스트가 아닌 파일이다.
- 측정 방식: 정적 분석. 시나리오마다 "이 파일을 고치지 않으면 기능이 완성되지 않는다"는 파일을 센다. 보조 값으로 grep 접점 수도 함께 기록한다. 같은 시나리오 정의로 R7 이후에 다시 측정한다.
- 기준선 (2026-09-18, 커밋 `c2ffe43`):

| # | 시나리오 | 필수 수정 파일 (현재) | 수 | grep 접점 | 목표 구조에서 예상 |
|---|---|---|---|---|---|
| S1 | 새 첨부 형식 1개의 추출 지원 | `attachment_text`, `execution`(extract 분기), `assets`(업로드 허용), `routers/workspace`(미리보기) | 4 | 11 | `parsing/<fmt>` + `executors/extract` = 2 |
| S2 | 요구사항에 필드 1개 추가 | `models`(RequirementRequest), `routers/workspace`(save_requirement SQL), `service`, `lib/workspace.ts`, `WorkspaceClient`(RequirementForm) | 5 | 5+ | models, `service/requirements`, 타입, `RequirementForm` = 4 |
| S3 | 제출 준비 차단 조건 1개 추가 | `service`(blockers), `lib/workspace.ts`(라벨), `WorkspaceClient`(nextStep), `models` | 4 | 8 | `service/readiness` + `nextStep` = 2 |
| S4 | 새 작업 종류 1개 추가 | `models`, `service`(enqueue), `execution`(dispatch+실행), `lanes`, `routers/workspace`(apply_job), `prerequisites`, `lib/workspace.ts`, `WorkspaceClient`(작업 이력) | 8 | 10 | models, `executors/<kind>`, 레지스트리, `JobHistory` = 4 |
| S5 | v2 오류 코드 1개 추가 + UI 메시지 | 발생 모듈, `service.fail` 경유, `WorkspaceClient`(issues 맵) | 3 | 18 | 발생 모듈 + 메시지 맵 = 2 |
| | **중앙값** | | **4** | **10** | **2** |

- 확정 조건: R7 이후 재측정에서 필수 수정 중앙값이 **30% 이상 감소**(4 → 2.8 이하, 즉 2)하고, S4처럼 수정 파일이 5개 이상인 시나리오가 하나도 없을 것.
- 제외 조건: 테스트, 문서, 마이그레이션 파일은 세지 않는다. 시나리오 정의는 R7 재측정 전까지 바꾸지 않는다.
- 판단 보류 기준: 시나리오 5건 중 2건 이상이 리팩토링 범위 밖의 이유(예: v1 경유)로 측정 불가능하면 판단을 보류한다.
- 보조 관찰: `tools/change_amplification.py`(커밋당 수정 파일 수). 현재 표본은 3건이고 squash 커밋이라 판단에 쓰지 않는다. 귀속 기간 4주 동안 관찰만 한다.
- 가드레일(핵심 지표 아님): pytest와 vitest 통과 수가 줄지 않을 것, v2 OpenAPI 스냅샷에 차이가 없을 것, mock e2e가 통과할 것.

## 4. 데이터·운영
- 최소 데이터: git 이력, import 그래프(`import-linter`), 파일 줄 수, `/openapi.json` 스냅샷, 기존 테스트 결과.
- 입력 방식: CI에서 자동 수집한다(ruff, pytest, import-linter, vitest, eslint 규칙).
- 법적·개인정보 조건: 테스트 fixture에 `COMPANY_*` PII, 사업자번호, 실제 토큰, identity registry를 넣지 않는다(AGENTS.md §7). 실공고 데이터는 공개 G2B 데이터만 쓴다. `.env`는 커밋하지 않는다.

## 5. MVP 경계
**포함** (기준: 6단계 슬라이스가 지나가는 코드이면서 v1 동작을 바꾸지 않는 것)
1. 공용 테이블을 `routers/notices.py`에서 `api/db/tables.py`(신규)로 옮긴다. 기존 이름은 re-export로 호환을 유지한다.
2. v2 도메인 예외를 둔다: `service.fail` → `WorkspaceError(code, message)`로 바꾸고, 라우터의 exception handler가 같은 `{code,message}` 응답을 내도록 매핑한다.
3. `routers/workspace.py`에 있는 SQL을 service 함수로 이동한다(`apply_job`, `save_requirement` 등).
4. `workspace/execution.py`를 작업 종류별 `executors/`로 분할한다: fetch, extract, analyze, hwp, excel, package.
5. 공용 파서를 만든다: `api/parsing/{pdf,hwpx,text,llm_json}.py`. 기준 구현은 `workspace/pdf_text.py`와 `attachment_text.py`이고, v2 경로의 중복만 대체한다.
6. 프론트: `WorkspaceClient`를 분해한다. `useWorkspace` 훅(reload·polling·mutate·run), 순수 함수 `nextStep`, 탭 3개 컴포넌트, `JobHistory`로 나눈다.
7. 프론트: v2 API 호출을 `workspaceApi`로 일원화한다(ETag·If-Match 지원 추가). `SpecificationWorkbench`의 직접 fetch를 제거한다.
8. 사용처가 없는 컴포넌트 9개와 그 테스트를 삭제한다.
9. 적합도 함수(FF)를 CI에 추가한다(9단계).

**제외** (목록이 비어 있으면 안 됨)
- v1 API와 화면의 동작 변경 및 퇴역(proposals, document_automation, `/search`, `/reviews`)
- `notices.py`의 라우트 분할. 테이블을 빼낸 뒤 2차로 진행한다
- v1의 `anthropic.Anthropic` 직접 호출 5곳 교체. FF 허용목록으로 격리만 한다
- OpenAPI 타입 자동 생성, Tailwind 색상과 버튼 통일
- DB 스키마 변경과 alembic 마이그레이션
- 테스트 fixture 통합. 중복 fixture 18곳은 슬라이스에 닿는 파일만 정리한다

**수동 처리**: 실공고 3건으로 리팩토링 전후를 대조하는 작업(HWP Worker 실연동)은 담당자가 수동으로 확인한다. 페르소나와 지표 확정도 사용자가 한다.

## 6. Vertical slice
- 시나리오 문장: "박정비가 `/workspace`에서 공고 1건을 등록하고, 원문 수집·추출 → 요구사항 확인 → 원본 서식 작성·검토 → 산출물 선택 → 검토 패키지 zip 다운로드까지 한 번에 통과시킨다."
- 실연동과 스텁 구분:
  - 실연동: DB(SQLite, 가능하면 Postgres 게이트 테스트), 파일 저장소, worker 큐
  - 스텁: G2B(fixture 첨부), LLM(`providers` fake), HWP Worker(mock agent)
- 시작 조건: 등록된 적 없는 fixture 공고 번호.
- 종료 조건: `run_package`가 끝나고 zip readback 검증이 통과하며 `ws.ready`가 판정된 상태.
- 기존 자산 재사용: `frontend/e2e/sample-document-loop.spec.ts`, `document-writing-mock.spec.ts`, `tests/test_workspace_*`. 리팩토링의 각 PR은 이 슬라이스 테스트를 통과해야 머지한다.

## 7. 흐름 (현재 위치 → 목표 모듈)
| # | 사용자 행동 | 시스템 처리 | 현재 코드 | 목표 모듈 | 예외 흐름 |
|---|---|---|---|---|---|
| 1 | 공고 검색·등록 | G2B 검색, upsert | `routers/workspace.py`에서 v1 `search_notices_endpoint`, `upsert_notice` 직접 호출 | `workspace/intake.py`(v1 함수를 어댑터로 감쌈) | G2B 장애 시 오류 표시 후 재시도 버튼 |
| 2 | 원문 수집 | `fetch_sources` 작업 enqueue → worker 다운로드 | `execution.py:348-521` | `executors/fetch.py` + `api/net/download.py` | 다운로드 실패 시 작업 실패로 보존, 미확인 첨부는 차단 |
| 3 | 추출 | PDF, HWPX, 아카이브, OCR | `execution.extract`, `pdf_text`, `attachment_text` | `executors/extract.py` + `api/parsing/*` | 형식 미지원이나 OCR 실패 시 수동 변환본 연결 |
| 4 | 요구사항 확인 | 분석(LLM), 후보 제시, 검토 | `execution.analyze`, `requirement_candidates`, `routers/workspace.save_requirement` | `executors/analyze.py`, `service/requirements.py` | LLM 장애는 **미평가**로 처리, 인용 실패는 `quote_diagnostics` |
| 5 | 비교·작성 | 초안 저장, 서식 채움 | `notice_forms.py`(파싱, 도메인, 스키마 혼재) | `forms/{hwpx_io,filling,schemas}.py` | 버전 충돌 시 409 / If-Match 불일치 경고 |
| 6 | 산출물 선택·패키지 | `output_plan`, `run_hwp`/`run_excel`/`run_package` | `output_plan.py`(지연 import), `execution.py` | `service/output_plan.py`, `executors/{hwp,excel,package}.py` | HWP 타임아웃 시 차단 유지, 마감 경과 시 ready 거부 |
| 7 | 서류 확인 | `blockers`, `ready` 판정 | `service.blockers:316` | `service/readiness.py` | 미해결 `source_needs`가 있으면 차단 |

## 8. 화면 (프론트 분해 기준)
| 화면 | 정보 우선순위 | 주요 버튼(1개) | 제외 요소(이 화면에서 뺄 것) |
|---|---|---|---|
| `/workspace` | 검색 결과, 등록 여부, 마감 | **등록** | v1 `NoticeSearchItem` 타입 의존 → v2 타입으로 교체 |
| `/workspace/[no]` 공통 셸 | 다음 단계(`nextStep`), 작업 상태 | **다음 단계 버튼**(`nextStep.action`) | 인라인 API 호출 |
| 탭 "2. 공고 서류 검토" → `SourceReviewTab` | 원문 목록, 추출 상태, 요구사항 | **원문 수집·추출** | `ExtractionPages`·`ArchiveMembers`는 하위 파일로 분리 |
| 탭 "3. 비교·작성" → `WritingTab` | 초안, 원본 서식 | **저장** | `ReferenceWriter`(기존 방식)는 별도 파일로 격리 |
| 탭 "4. 서류 확인" → `ReviewTab` | 차단 사유, 산출물, 패키지 | **패키지 생성** | 작업 이력은 `JobHistory`로 분리 |

폼 컴포넌트(`RequirementForm`, `CommercialForm`, `DocumentRow`)는 각자 파일로 옮긴다. 작업 종류와 상태 문자열은 `lib/workspace.ts` 상수로 모은다.

## 9. 구조
**모듈 경계와 의존 방향** (위 → 아래로만 의존한다)
```
routers/workspace.py (HTTP, 예외 매핑)
   → workspace/service/* (도메인: inputs, requirements, readiness, output_plan, audit)
   → workspace/executors/* (작업 실행)
   → api/parsing/*, api/net/*, workspace/providers.py (순수 어댑터)
   → api/db/tables.py (스키마)
routers/notices.py (v1) → api/db/tables.py   # v2는 routers.* import 금지
```

**적합도 함수(FF)**: CI에 추가한다.
- import-linter 계약 3가지:
  1. `api.workspace` ↛ `api.routers`
  2. `api.parsing` ↛ `api.workspace`
  3. service ↛ fastapi. `HTTPException`은 라우터에서만 쓴다
- 함수 안 import 0개(허용목록 제외)를 확인하는 테스트: `tests/test_architecture.py`
- `anthropic.Anthropic(` 호출은 `providers.py`와 v1 허용목록 5곳에서만 허용하는 grep 테스트
- 파일 크기 상한: py 600줄, tsx 300줄. 신규와 변경 파일만 검사한다
- ESLint `no-restricted-globals`: `components/Workspace*`에서 `fetch` 직접 호출 금지

**설계안 3개 비교**
| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| A. 계층 정리 | 테이블만 분리하고 큰 파일을 같은 계층 안에서 쪼갬 | 가장 빠르고 위험이 낮음 | HTTP와 도메인 혼재, 순환 import가 남음 |
| **B. 슬라이스 경계 + 포트/어댑터 (권장)** | 흐름 단계별 service/executor 모듈, 공용 어댑터, FF로 방향 강제 | 핵심 지표(변경 증폭)에 직접 작용, 점진 적용 가능 | 초기 이동량이 큼(2~3주) |
| C. v2 별도 패키지(strangler) | v2를 독립 패키지로 떼고 v1과는 ACL로만 통신 | 경계가 가장 명확 | 공용 테이블과 v1 핸들러 재사용 때문에 비용이 과다하고, 운영 전환을 지연시킴 |

ADR 초안은 `docs/adr/0001-v2-module-boundaries.md`에 쓴다. B안을 채택하는 근거, 기각한 A·C안, FF 목록, re-export 호환 기간(v1 테스트가 새 경로로 옮겨질 때까지)을 담는다.

## 10. 완료·판단
- 검증 가설: "B안 경계를 적용하면 대표 변경 시나리오의 필수 수정 파일 중앙값이 4에서 2 이하로 줄고, 슬라이스 회귀는 0건이다."
- 완료 조건:
  - MVP 포함 항목 9개를 머지한다.
  - FF가 CI에서 그린이다.
  - 가드레일 3개를 유지한다.
  - 실공고 1건으로 수동 대조를 통과한다.
- **판단 매트릭스**
| 핵심 지표 (R7 후 재측정) | 가드레일 | 판단 |
|---|---|---|
| −30% 이상 | 유지 | **확장**: `notices.py` 라우트 분할, v1 LLM 경로를 providers로, OpenAPI 타입 생성 |
| −10~30% | 유지 | **수정**: 변경이 몰리는 모듈을 재분석한 뒤 경계를 조정 |
| −10% 미만 | 유지 | **중단**: FF만 유지하고 추가 이동은 멈춘 뒤 전환 작업에 집중 |
| 무관 | 회귀 발생 | **중단 후 롤백**: 해당 PR을 revert하고 슬라이스 테스트를 보강 |
| 시나리오 2건 이상 측정 불가 | — | **보류**: 시나리오 재정의 후 재측정 |

---

## 실행 순서 (PR 슬라이스, 각 PR마다 슬라이스 테스트 그린)
- **R0**: 미커밋 변경 커밋, 기준값 기록, `tools/change_amplification.py`
- **R1**: 테이블을 `api/db/tables.py`로 이동하고 re-export. 대상은 v2, `alembic/env.py`, `tests/conftest.py`의 import 경로. import-linter 계약 1을 도입한다
  - **완료 (2026-09-18)**: 17개 테이블과 `metadata`를 이동했다(`api/db.py` → `api/db/__init__.py` 패키지화). `api/` 비라우터 모듈 전체, `routers/{documents,proposals,workspace}`, alembic, conftest, tools를 새 경로로 바꿨다. 계약 1은 CI `lint-imports`에 넣었고 위반 주입 테스트에서 BROKEN을 확인했다. alembic 대상 테이블 28개는 변경 전후 동일하고, OpenAPI는 이동 전 코드 기준 스냅샷과 동일하다(`tests/test_openapi_snapshot.py`). pytest 1,741 passed / 17 skipped(+1은 스냅샷 테스트). 테스트 144곳의 `api.routers.notices` import는 re-export로 유지한다
- **R2**: `WorkspaceError`와 exception handler를 추가하고, 라우터의 SQL을 service로 옮긴다. 계약 3 도입
  - **완료 (2026-09-18)**:
    - R2a: `api/workspace/errors.py`의 `WorkspaceError`로 도메인 예외를 바꿨다. 응답은 FastAPI `http_exception_handler`에 위임해서 본문이 같다(`tests/test_workspace_errors.py`). 레거시 서비스(uploads·exporters·db)는 아직 HTTPException을 던지므로 catch 지점은 `HANDLED_ERRORS`로 받는다. 계약 3(`api.workspace` ↛ fastapi 직접 import)의 예외는 `errors`(과도기)와 `identity`(HTTP 어댑터) 두 곳이다. 테스트 13개 파일의 `pytest.raises(HTTPException)`을 `WorkspaceError`로 바꿨다.
    - R2b: `apply_job` 도메인 로직을 `api/workspace/apply.py`로, 라우터 SQL 7곳을 `api/workspace/queries.py`로 옮겼다. 라우터에 남은 SQL은 0이다(774 → 654줄). 목록 API 회귀 테스트를 추가했고 이동 전 코드에서도 통과함을 확인했다.
    - pytest 1,744 passed / 17 skipped. OpenAPI 스냅샷 동일.
  - **잔여**: 라우터 핸들러 몇 곳(`review_section`, `upload_document`, `link_source`, `register_text`, `confirm_document`)에 입력 dict 변경 로직이 남아 있다. SQL은 아니며, 해당 흐름 단계를 service 모듈로 나눌 때(R4 이후) 함께 옮긴다. `identity`는 `api.routers`로 이동할 후보다
- **R3**: `execution.py`를 `executors/*`로 분할하고 함수 안 import를 제거한다
  - **완료 (2026-09-18)**:
    - `execution.py`(933줄)를 `executors/{analyze,extract,fetch,hwp,excel,package}.py`(62~219줄)와 디스패처 `executors/__init__.py`로 나눴다. 파일 검사는 `storage.py`(storage_root, source_path, artifact)로, `fail`은 `errors.py`로 옮겼다. `service.fail`은 re-export로 유지한다. `execution.py`는 32줄짜리 호환 파사드로 남긴다.
    - 순환의 뿌리였던 `service ↔ execution`을 끊었다. 그래서 `source_path`를 함수 안에서 import하던 9곳을 모듈 상단 import로 바꿨다. `service`의 비순환 지연 import 4종(identity, asset_policy, output_plan, writing_plan)도 끌어올렸다.
    - 1st-party 함수 안 import: 67 → **31**. 전체(3rd-party 포함)는 81 → 39. 남은 것은 `notice_forms`·`source_needs`·`specifications.service` 순환(서비스 분할 때 해소)과 의도적 지연 2건(`spec-search` 선택 extra, grading의 Qdrant 스택)이다. `tests/test_architecture.py` 래칫이 파일별 예산을 감소 방향으로만 허용한다.
    - 테스트 패치 대상 12곳을 코드가 실제로 있는 모듈로 바꿨다. 원래 지연 import였던 이름(`pdf_text.extract_pdf`, `attachment_text.*`, `uploads.*`)은 모듈 속성 접근으로 바꿔서, 호출 시점에 바인딩되는 의미를 유지했다. 대상을 일부러 틀리게 넣는 변이 검사로 패치가 실제로 효과가 있는지 확인했다.
    - pytest 1,746 passed / 17 skipped(+2 아키텍처 테스트). OpenAPI 스냅샷 동일. 계약 2개 유지.
- **R4**: `api/parsing/*`, `api/net/download.py`를 만들고 v2 중복 경로를 대체한다. `notice_forms`를 분할한다. 계약 2 도입
- **R5**: 프론트 `workspaceApi`를 일원화하고 사용처 없는 컴포넌트를 삭제한다
- **R6**: `WorkspaceClient`를 분해한다(`useWorkspace`, `nextStep`, 탭 3개, `JobHistory`)
- **R7**: 나머지 FF(파일 크기, anthropic grep, ESLint fetch 금지)와 ADR을 확정하고 문서를 갱신한다(AGENTS.md §3·§8의 5층 동기화 경로)

## 재사용할 기존 코드
- `api/workspace/pdf_text.py`, `api/workspace/attachment_text.py`: 파서 기준 구현
- `api/services/claude_analyzer.py:35` `safe_parse_json_object`: `llm_json` 기준
- `api/workspace/providers.py`: LLM 단일 경로
- `frontend/src/lib/workspace.ts` `workspaceApi`: v2 클라이언트 기준
- `tests/conftest.py` `sqlite_engine`/`client`, `e2e/helpers.ts`

## 검증
- 매 PR: `ruff check .`, `pytest -q`(통과 수가 기준선 이상), `lint-imports`, `cd frontend && npm run lint && npm run typecheck && npm test`
- v2 API 무변경 확인: `/openapi.json` 스냅샷 diff 테스트(`tests/test_openapi_snapshot.py`)
- 슬라이스: `npm run e2e -- sample-document-loop document-writing-mock workspace-v2` (mock 경로)
- v1 무변경 확인: `tests/test_notices_*`, `test_documents_*` 전체 통과, `/notices/[no]` 수동 스모크 1회
- R7 이후: 실공고 1건 수동 대조, `tools/change_amplification.py`로 4주 후 판단 매트릭스 적용
