# v2 개인 인증·역할·승인자 기록 — 2026-09-13

`/workspace`에 개인 토큰 로그인과 역할별 서버 검증을 추가했다. `WORKSPACE_AUTH_ENABLED=true`인 환경에서는 `/v2/*` 조회와 변경 모두 개인 인증이 필요하며 공유 `X-API-Key`만으로 접근할 수 없다. 기존 공유 키 검증도 유지한다. 이번 검증에는 가상 계정과 격리된 테스트 저장소만 사용했고 실제 사용자 등록·토큰 발급·로컬 `.env` 변경은 하지 않았다.

## 설정

API 실행 환경에서 다음 값을 설정한다. 기본값은 기존 로컬 검증과 호환되는 비활성 상태다.

| 설정 | 의미 |
|---|---|
| `WORKSPACE_AUTH_ENABLED` | `true`일 때 개인 인증과 역할 검증 활성화. 기본 `false` |
| `WORKSPACE_AUTH_USERS` | 개인 계정 레코드의 JSON 배열. 원문 토큰을 넣지 않는다. |
| `WORKSPACE_AUTH_REGISTRY` | 같은 JSON 배열을 담은 UTF-8 로컬 파일 경로. 위 환경변수 대신 사용한다. |

두 registry 설정 중 정확히 하나만 지정한다. 계정은 1~1,000개이며 파일은 1 MB 이하이다. 각 계정 레코드의 필드는 다음과 같다.

| 필드 | 제약 |
|---|---|
| `id` | 변경하지 않는 사용자 식별자, 영문·숫자·`_ . -`, 1~100자 |
| `name` | 표시 이름, 1~100자 |
| `role` | `viewer`, `writer`, `reviewer`, `approver` 중 하나 |
| `token_sha256` | 개인 원문 토큰의 SHA-256, 소문자 16진수 64자 |
| `enabled` | 선택 항목, 기본 `true`. `false`이면 인증 거부 |

개인 원문 토큰은 관리자가 발급하고 사용자에게 별도로 전달한다. 충분히 무작위인 32~512자의 `A-Z a-z 0-9 . _ ~ + / = -` 문자만 허용한다. 일반 비밀번호를 SHA-256으로 등록하는 용도가 아니다. registry에는 식별 정보와 토큰 해시만 저장하며 원문 토큰·실사용자 자료·registry 파일을 저장소에 커밋하지 않는다. 파일 접근 권한은 운영 계정으로 제한한다.

설정은 요청마다 읽으므로 계정 삭제·비활성화·역할 변경은 다음 요청부터 적용된다. 설정이 비었거나 JSON/해시가 잘못됐거나 식별자·해시가 중복되면 `503 workspace_auth_config`로 차단한다. 오류 응답에는 registry 원문과 토큰을 포함하지 않는다.

Next 서버는 기존 `INTERNAL_API_BASE`, `INTERNAL_API_KEY`, `FRONTEND_ORIGIN` 설정을 사용한다. `FRONTEND_ORIGIN`에는 허용할 웹 출처를 쉼표로 지정한다. 미지정 시 `http://127.0.0.1:3002`만 허용하며 요청의 Host/Origin을 따라 허용 범위를 바꾸지 않는다. 실배포 출처를 명시하고 운영 환경에서는 HTTPS를 사용한다.

## 역할과 승인

역할은 독립적이며 상위 역할이 다른 역할의 권한을 자동으로 얻지 않는다. 사용자가 보낸 이름·역할 헤더나 본문으로 권한을 바꾸지 않는다.

| 작업 | 허용 역할 |
|---|---|
| 작업대 조회·다운로드·읽기 전용 공고/사양 검색 | 네 역할 모두 |
| 공고 등록, 참가 결정, 원문/참고자료 등록·연결, 작성·출력 계획, 작업 실행 | `writer` |
| 섹션 `approved=null` 초안 저장, 미판정 요구사항 저장 | `writer` |
| 원문 검토, 문서 확인, 원본 양식과 섹션 승인·반려 | `reviewer` |
| 요구사항 `accepted/rejected` 또는 충족 여부 판정 | `reviewer` |
| 생성물 `approved/rejected` | `reviewer` |
| 검토 패키지 `ready` 최종 제출 준비 완료 | `approver` |

인증과 역할 확인은 기존 입력 버전·원문 해시·인용 위치·파일 무결성·마감일시·검토 충돌 검증에 추가된다. `approver`라도 미확인 항목이나 변경된 파일을 승인할 수 없다. 참고자료 `company_reference`를 증빙으로 바꾸는 제한과 사람이 명시적으로 실행·검토해야 하는 정책을 유지한다.

새 변경 API는 기본적으로 `writer`를 요구한다. 신규 승인/판정 경로를 추가할 때는 `api/workspace/identity.py`의 역할 분류와 우회 차단 테스트를 함께 갱신해야 한다.

## 로그인·감사 기록

`/workspace/login`에서 개인 토큰을 입력하면 Next의 `/api/workspace-session`이 API `/v2/identity`에서 검증한 뒤 8시간 `HttpOnly`, `SameSite=Strict` 쿠키를 설정한다. 운영 또는 HTTPS 요청에는 `Secure`도 설정한다. 토큰은 응답 JSON·로그·브라우저 localStorage에 저장하지 않는다. 로그인 실패 시 입력을 지운다.

Next `/api/v2/*` proxy는 쿠키의 개인 토큰만 upstream `Authorization: Bearer`로 전달한다. 브라우저가 직접 보낸 인증·사용자·역할 헤더는 전달하지 않는다. API는 브라우저 쿠키를 직접 인증 수단으로 인정하지 않으며, 개인 Bearer와 기존 API 키 정책으로 검증한다. 로그인·로그아웃 및 proxy 변경 요청은 허용 Origin을 확인한다.

`GET /v2/identity`의 응답은 `{enabled, actor}`이며 인증된 actor는 `{id, name, role}`이다. 비활성 환경은 `{enabled: false, actor: null}`을 반환하고 화면에 개발 모드를 표시한다.

서버가 검증한 actor는 요청 범위 ContextVar에 두며 요청 종료 후 해제한다. `service.audit`가 `details.actor`에 저장하고 작업대 검토 이력의 `actor` 응답 키로 노출한다. 기존 기록과 인증 비활성 상태에서 생성한 기록에는 개인 식별 정보를 소급해서 붙이지 않는다. 백그라운드 작업이 사람의 신원을 임의로 만들어 승인하지 않는다.

## 검증 결과

- `tests/test_workspace_identity.py`와 `tests/test_auth.py`: 40건 통과. 조회 인증, 공유 키 단독 우회, 역할별 작성·검토·최종 승인 차단, 경로 이름 교란, 사용자 헤더/본문 위조, registry 변경·회수, 잘못된 설정의 비밀 비노출, 기존 API 호환을 검증했다.
- `tests/test_workspace_identity_integration.py`: 1건 통과. 실제 workspace router와 `service.audit`를 격리 DB에서 실행해 검토 이력 응답의 `actor` 키와 저장된 식별자·이름·역할을 확인하고, 기존 개인 식별 없는 기록은 `actor=null`로 보존됨을 확인했다.
- `frontend/src/lib/__tests__/workspace-session.test.ts`: 8건 통과. 쿠키 속성·8시간 유효기간, 검증 후 발급, 로그인/로그아웃 Origin, 실패 시 쿠키 미발급, proxy의 위조 헤더 제거, Host/Origin 동시 위조 차단을 검증했다.
- 관련 Python Ruff, 프론트 ESLint, TypeScript 검사 통과.
- 실제 사용자 권한으로 실행 중인 환경에서 로그인부터 최종 승인까지 검증한 결과는 아니다.

## 운영 전 남은 일과 한계

실사용자 등록·개인 토큰 발급·역할 배정, HTTPS 환경의 로그인/로그아웃 및 권한 회수 점검, 담당자 간 작성→검토→최종 승인 리허설이 남아 있다. 이 검증이 끝나기 전에 팀 배포용 개인 인증이 운영 검증됐다고 표시하지 않는다.

현재 쿠키는 개인 Bearer 자격증명을 보관한다. 로그아웃은 해당 브라우저 쿠키를 삭제하며 다른 브라우저의 자격증명을 회수하지 않는다. 계정 전체 회수는 registry 비활성화·삭제 또는 토큰 해시 교체로 수행한다. 서버 세션 저장소, 계정관리 화면, SSO/MFA, 비밀번호 복구, 로그인 시도 제한은 제공하지 않는다.

v2 인증을 켜도 기존 `/notices` 등 호환 API는 기존 공유 키 정책을 사용한다. 시스템 전체의 개인별 접근 통제나 데이터 단위 접근 격리를 완료한 것은 아니다. 팀 배포에서는 호환 경로의 노출 범위를 별도로 제한해야 한다.
