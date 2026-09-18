# Gemini 작업대 연동

작성일: 2026-09-09. 구현 및 mock 검증 완료, 실제 Google API 호출은 미검증.

후속 업데이트: 사용자가 현재 키 사용을 승인하여 실제 요청 2회를 실행했다. 두 분석 모두 실패했고 전체 E2E는 미완료다. 최신 결과는 [실제 버튼 E2E 기록](gemini-live-e2e-2026-09-09.md)을 참고한다. 아래의 키 미등록·실연동 미검증 표기는 최초 구현 시점의 기록이다.

## 적용 범위

- `/v2/notices/{notice_no}/jobs`의 `analyze`, `proposal` 작업에서 공급자를 선택한다.
- `anthropic` 기본값과 기존 Claude 요청 형식, 기존 API는 유지한다.
- `gemini`는 Google의 `generateContent` REST API와 JSON Schema 응답을 사용한다. 추가 SDK 설치는 필요 없다.
- 원문 인용 일치, 요구사항/근거 ID 검증, 새로운 수치의 `[검증필요]` 표시, 사람 검토 조건은 공급자와 무관하게 적용한다.
- 기존 작성자료 비교 초안(`reference-drafts`)은 기존 로컬 비교 동작을 유지하며 새 외부 호출을 추가하지 않는다.
- 원문이 없거나 확인된 회사/제품 증빙이 없는 경우의 기존 사전 조건은 그대로 유지한다.

## 로컬 설정

대화에 노출한 키는 폐기·재발급한다. 새 키는 저장소 루트 `C:/Users/junpr/autojebi/.env`에서만 등록한다. 이 작업에서는 대화의 키를 저장하거나 사용하지 않았고, `.env`도 변경하지 않았다.

```dotenv
WORKSPACE_LLM_PROVIDER=gemini
GOOGLE_API_KEY=
GEMINI_MODEL=gemini-2.5-flash
```

`GOOGLE_API_KEY`에 재발급한 값을 로컬에서 입력한다. `PROPOSAL_MODEL`은 Claude 전용이며 Gemini 분석·초안은 모두 `GEMINI_MODEL`을 사용한다. 다른 모델을 선택하면 해당 모델의 JSON Schema 지원과 프로젝트 사용 권한을 별도로 확인한다.

검증 환경은 `3002/8002`를 유지한다. 키 또는 공급자를 변경한 뒤 실행 중 작업이 없는지 확인하고 API 및 작업 실행기 감독 프로세스를 함께 재시작한다. 감독 프로세스가 이전 환경값을 물려줄 수 있으므로 자식 실행기만 재시작하는 것으로 설정 변경을 보장하지 않는다. 운영 `3000/8001`이나 사용자의 한글 프로세스는 종료하지 않는다.

설정 화면(`/admin`)의 AI 분석 영역에서 선택 모델과 키 등록 여부를 확인한다. 새로고침은 로컬 설정 조회만 하며 Google API를 호출하지 않는다. 유효성 확인은 사람이 원문 분석 버튼을 실행한 작업 결과로 판단한다.

## 안전 동작

- 같은 원문·회사·증빙 내용의 유료 호출은 공급자와 입력 버전을 넘어 합산 최대 2회다.
- 요청 전 영속 예약을 기록하고 타임아웃·인증 오류 등 실패 후에도 예약을 돌려주지 않는다. 키 미등록은 예약 전에 차단한다.
- 동일한 정상 요청은 결과를 재사용한다. Gemini/Claude 또는 모델이 다른 요청은 캐시를 공유하지 않는다. 기존 Claude 캐시 형식은 유지한다.
- 자동 재시도·다른 공급자 fallback·HTTP redirect를 사용하지 않는다.
- 키는 고정 Google 호스트의 `x-goog-api-key` 헤더에만 보낸다. 로그·오류·작업 결과·설정 응답에 키나 원시 공급자 오류를 포함하지 않는다.
- 인증 실패, 할당량 초과, 모델 사용 불가, 연결 오류, 시간 초과, 응답 차단, 출력 중단, JSON 오류를 구분한다.
- 종료 사유가 `STOP`이 아닌 응답은 결과로 저장하지 않는다. 생각 과정은 결과 본문에서 제외한다.
- LLM 실패는 미평가다. 0점·비관련·참가 결정·승인으로 바꾸지 않는다.

## API 변경

기존 `GET /v2/settings`의 `configured`, `last_checks`, `worker` 등을 유지한다. `configured.llm`은 선택 공급자의 키 등록 여부다. 아래 `llm` 필드를 추가한다. 실제 연결 검증을 위한 임의 유료 호출은 하지 않으므로 `connection_status`는 `not_checked`다.

```json
{"llm":{"provider":"gemini","model":"gemini-2.5-flash","key_registered":false,"connection_status":"not_checked"}}
```

분석·제안서 결과의 `llm_usage`에는 비밀값 없는 `provider`를 추가한다. 입력 내용에 대한 호출 한도와 별개로 요청 캐시는 공급자와 모델을 구분한다.

## 검증 기록

- Gemini 전송·오류·원문 인용·호출 한도·캐시 및 기존 관련 회귀: 66건 통과.
- 전체 workspace 관련 백엔드 회귀: 554건 통과, 7건 skip(총 561건). PostgreSQL/실연동 opt-in 테스트의 기본 skip은 실연동 통과로 계산하지 않는다.
- 변경 Python 파일 Ruff 검사 통과.
- 프론트 타입 검사 통과.
- AI 설정 표시 3건 + 기존 작업대 36건: 39건 통과. 기존 Worker 상태 컴포넌트의 React `act` 경고는 남아 있다.
- 검증 API와 대기 실행기를 최신 코드로 재시작했다. 진행 중 작업은 0건임을 먼저 확인했다.
- 실제 `http://127.0.0.1:3002/admin`을 열어 현재 기본 Claude 설정의 키 미등록 표시 및 새로고침 버튼을 확인했다.
- 실제 Gemini 유료 호출, Google 키 유효성, 실제 공고 전체 E2E 및 HWP 파일 생성은 이번 검증에 포함하지 않았다. 키 등록 후 별도 검증이 필요하다.

## 공식 참고

- [Google generateContent API](https://ai.google.dev/api/generate-content)
- [Google Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output)
- [Gemini 2.5 Flash 모델](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash)
