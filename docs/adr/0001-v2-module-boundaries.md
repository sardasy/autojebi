# ADR 0001 — v2 작업대 모듈 경계와 의존 방향

- 상태: **제안(초안)** — 2026-09-18
- 관련: [리팩토링 파이프라인](../refactor/2026-09-18-refactor-pipeline.md) 9단계

## 맥락
- v2 코드(`api/workspace`, `api/routers/workspace.py`)는 공용 테이블 18개를 v1 라우터 `api/routers/notices.py`(3,454줄)에서 import한다. v1 핸들러(`search_notices_endpoint`, `upsert_notice`, `list_hwp_templates`)도 직접 호출한다.
- `service.py`는 `HTTPException`을 던진다(`fail()`). `routers/workspace.py`에는 SQL이 들어 있고, `execution.py`는 작업 종류 6개를 한 파일에서 실행한다.
- 세 모듈에 함수 안 import가 64개 있다. 이것은 순환 의존의 증상이다.
- PDF와 HWPX 파싱 경로는 각각 4~5곳에 중복돼 있다.

## 결정
**B안: 슬라이스 경계 + 포트/어댑터**를 채택한다. 의존은 위에서 아래로만 흐른다.

```
routers/workspace.py            HTTP 계층. WorkspaceError → {code,message} 응답으로 매핑
  → workspace/service/*         도메인: inputs, requirements, readiness, output_plan, audit
  → workspace/executors/*       작업 실행: fetch, extract, analyze, hwp, excel, package
  → api/parsing/*, workspace/providers.py              순수 어댑터 (파서·검증, LLM 공급자)
  → api/db/tables.py            SQLAlchemy 스키마(단일 metadata)
routers/notices.py (v1)  → api/db/tables.py
```

- v1 API와 화면의 동작은 바꾸지 않는다. `api.routers.notices`는 테이블 이름을 re-export해서 호환을 유지한다.
- v2가 v1 기능을 써야 하면 `workspace/intake.py` 같은 어댑터 한 곳에서만 부른다.

## 적합도 함수 (CI 강제)
1. import-linter(구현됨): `api.workspace` ↛ `api.routers`; `api.workspace` ↛ fastapi 직접 import(예외: `errors` 과도기, `identity` HTTP 어댑터); `api.parsing` ↛ `api.workspace`·`api.routers`·fastapi(간접 포함)
2. `tests/test_architecture.py`(구현됨): `api/workspace`의 함수 안 `api.*` import는 파일별 예산을 넘을 수 없고, 예산은 감소 방향으로만 바꾼다(R3 기준 31 → R4 29).
3. `anthropic.Anthropic(` 호출은 `workspace/providers.py`와 v1 허용목록 5곳에서만 허용한다.
4. 파일 크기 상한은 py 600줄, tsx 300줄이다. 신규 파일과 변경 파일에만 적용한다.
5. ESLint: `components/Workspace*`에서 `fetch`를 직접 호출하면 안 된다. `workspaceApi`를 사용한다.

## 검토한 대안
| 안 | 기각 사유 |
|---|---|
| A. 계층 정리(파일만 분할) | HTTP와 도메인이 계속 섞이고 순환 import가 남는다. 변경 증폭이 거의 줄지 않는다 |
| C. v2 별도 패키지(strangler) | 공용 테이블과 v1 핸들러 재사용 때문에 ACL 비용이 과다하다. 운영 전환 잔여 작업이 늦어진다 |

## 구현 중 조정 (2026-09-18)
- `api/net/*`, `parsing/text`, `parsing/llm_json`은 만들지 않았다. v2에는 중복이 없고, 중복은 모두 v1에 있다(v1 동작 유지 결정으로 범위 밖). v1을 정리할 때 다시 검토한다.
- HWPX 경로 3개(원문 추출·양식 편집·산출물 검증)는 한도·예외·엄격도가 다르므로 하나의 파서로 합치지 않는다.

## 결과
- 장점: 흐름 단계 하나를 바꿀 때 service나 executor 모듈 하나 안에서 끝나게 된다. FF가 있어서 경계가 다시 무너지지 않는다.
- 비용: 모듈을 대량으로 옮겨야 한다(PR R1~R7). re-export는 v1 테스트 import가 새 경로로 옮겨질 때까지 유지한다.
- 재평가: 파이프라인 10단계의 판단 매트릭스를 따른다(4주 후).
