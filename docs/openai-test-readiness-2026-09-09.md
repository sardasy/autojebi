# OpenAI API 테스트 준비

2026-09-09 준비 시점 기록. 이후 로컬 키 등록과 실제 OpenAI 분석·제안서 생성 각 1회를 완료했다. 최신 상태는 [실제 E2E 결과](openai-live-e2e-2026-09-09.md)를 따른다. 아래 키 미등록·실호출 미실행 표기는 준비 당시 상태다.

## 로컬 설정

`C:/Users/junpr/autojebi/.env`에 아래 항목을 준비했다. 키 입력란은 비어 있다. 기존 Google 키와 다른 설정은 보존했다.

```dotenv
WORKSPACE_LLM_PROVIDER=openai
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MAX_OUTPUT_TOKENS=16384
```

실제 키는 대화에 보내지 말고 이 파일의 `OPENAI_API_KEY`에 등록한다. 모델 선택과 키 등록만으로 실제 연결 성공을 판단하지 않는다.

현재 PC 프로세스 환경에 별도 `OPENAI_API_KEY`가 감지되었다. 이번 검증 API/감독 프로세스에는 해당 환경변수를 상속하지 않고 로컬 파일의 키를 기다리도록 재시작했다. PC 전역 환경변수는 변경하지 않았다. 일반 설정 로더는 환경변수를 `.env`보다 우선하므로 다른 셸에서 재시작할 때도 원하는 키의 출처를 확인해야 한다.

키 등록 후 진행 중 작업이 없는지 확인하고 검증 API와 작업 실행기 감독 프로세스를 재시작한다. 자식 Worker만 재시작하면 감독 프로세스의 이전 환경변수를 상속할 수 있다. 검증 환경은 3002/8002이며, 운영 3000/8001은 유지한다.

## 구현 범위

- `/v2/notices/{notice_no}/jobs`의 `analyze`, `proposal`에 OpenAI를 추가했다.
- `POST https://api.openai.com/v1/responses`, Bearer 인증, `text.format`의 strict JSON Schema, `store=false`를 사용한다.
- 현재 공통 스키마의 필수 항목을 그대로 유지하고 객체마다 `additionalProperties=false`를 적용한다. `$defs` 내부의 제안서 섹션에도 적용한다. 원래 Claude/Gemini 스키마는 변경하지 않는다.
- 완료된 assistant 메시지의 JSON만 받는다. 거절·미완료·출력 한도·잘못된 JSON·인증·할당량·모델·HTTP 오류는 실패로 처리한다. 내부 추론 내용과 원시 오류는 결과로 사용하지 않는다.
- 같은 원문·회사·증빙에 대한 합산 2회 한도, 사전 예약, 실패 예약 유지, 정확한 정상 요청의 결과 재사용을 보존한다.
- 공급자·모델별 요청 캐시는 구분한다. 다른 공급자로 자동 전환하거나 자동 재시도하지 않는다.
- 원문 인용 검증, 근거 ID 검증, 새 수치의 `[검증필요]`, 사람 검토 조건을 공통 적용한다.
- 기존 Claude 호환 API 및 로컬 참고자료 비교 초안은 그대로 유지한다.
- `/v2/settings`와 관리자 AI 분석 영역에 OpenAI 공급자·모델·키 등록 여부를 표시한다. 조회만으로 외부 OpenAI 요청을 보내지 않는다.

## 검증 결과

| 항목 | 결과 |
| --- | --- |
| OpenAI/Gemini·호출 한도·원문 사전조건·v2 관련 집중 회귀 | 127 passed |
| 전체 workspace 관련 백엔드 회귀 | 581 passed, 7 skipped |
| AI 설정·연결 상태·기존 작업대 프론트 | 41 passed |
| 프론트 타입 검사 | 통과 |
| 변경 Python 파일 Ruff | 통과 |
| 검증 API/작업 실행기 재시작 | 진행 중 작업 0건 확인 후 반영 |
| 실제 OpenAI 키 유효성·공고 분석 | 미실행 |

전체 workspace 테스트의 7개 skip은 opt-in 검증을 실행한 것으로 계산하지 않는다. 프론트 기존 Worker 상태 테스트의 React `act` 경고는 남아 있다. 이번 검증은 실제 LLM 품질이나 공고 서류/HWP 전체 E2E 통과를 뜻하지 않는다.

## 다음 실호출 조건

1. 로컬 OpenAI 키를 등록하고 검증 API·감독 프로세스를 재시작한다.
2. 관리자 화면에서 `OpenAI`, 선택 모델, 키 등록 상태를 확인한다.
3. 호출 이력이 없는 새로운 실제 공고 또는 독립된 테스트 샘플을 사용한다. 기존 PLECS 공고 `R26BK01706511-000`은 Gemini 시도 2회가 이미 예약되어 있으므로 한도를 리셋하거나 복제 공고로 우회하지 않는다.
4. 원문 확보와 남은 호출 한도를 확인하고 사람이 요구사항 분석을 실행한다.
5. 실제 인용 결과와 오류를 확인한 뒤 검토 대상으로 반영한다. 제안서 생성에는 확인된 회사/제품 자료가 필요하다. 공급자 변경으로 증빙·HWP 템플릿 누락이 해결되지는 않는다.

## 공식 자료

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [GPT-4.1 Mini 모델 및 지원 기능](https://developers.openai.com/api/docs/models/gpt-4.1-mini)
