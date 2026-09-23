# JEV 작업대 통합검증 — 2026-09-21

## 변경과 실행 범위

공고 서류 검토 화면의 JEV 수동 실행을 기존 PostgreSQL 작업 큐의 external 실행기에 연결했다.
`WORKSPACE_JEV_ENABLED` 기본값은 false이며 실제 검증 프로세스에서만 true로 실행했다.
회사 정책은 `config/company.example.yaml`의 가상 Example 회사 정책을 명시했다.
원문 텍스트와 정책·모델을 확인하는 request hash를 화면에서 받아 실행 시 다시 검증한다.
입력 버전·원문·정책·claim token 검사 뒤 분류 이력과 작업 완료를 같은 트랜잭션에 저장한다.
기존 anthropic/gemini/openai 분석 경로, 참가 결정, 증빙 승인 및 제출 준비 로직은 유지한다.

검증 서버는 화면 3002, API 8002, PostgreSQL 5434의 `autojebi_workspace`다.
이 DB에 `0017_spec_search → 0018_decision_layer`를 적용했다. 운영 `autojebi` DB는 변경하지 않았다.
자동 수집은 꺼져 있고 local/external 실행기는 분리되어 있다.

## 실호출 결과

Playwright `jev-live.spec.ts` 1건 통과, 시나리오 실행 시간 18.3초.
새 가상 공고 `E2E-JEV-1789985432127`을 화면에서 등록하고 TEST ONLY PDF를 추출·반영했다.
버튼으로 JEV 분류를 요청해 아래 결과를 화면과 API에서 확인했다.

| 항목 | 결과 | API 신뢰도 |
|---|---|---|
| 제품군 | HIL | 100% |
| 적용 분야 | HVDC | 99% |
| 회사 관련도 | high | 93% |
| 검토 우선순위 | high | 36% |

응답 모델은 `jev-1.13.0`. 최저 신뢰도 36%에 따라 `human_review`로 안내되었다.
API 신뢰도는 선택값 확률과 별도로 보존하며 정확도나 사업적 적합성을 보증하지 않는다.

- 작업: `fb19f1d3-955e-4c22-9ffc-2a71951005c2`
- 분류 저장: `55698da8-9e3a-45c4-bc58-09802d7f5b39`
- 입력 버전 3에서 분류 완료. 다시 확인 버튼과 새로고침 후 같은 기록을 표시했다.
- 화면에서 원문 수정 후 버전 4, `current_job_id=null`, 기존 작업 1건 보존.
- 참가 결정·검토 이력은 변경하지 않았고 `ready=false`를 유지했다.
- 증거: `data/workspace/jev-loop/E2E-JEV-1789985432127/result.json`, `classified.png`, `historical.png`.

## 회귀와 제한

오프라인 통합 테스트는 원문/정책 변경, 검토만 바뀐 버전의 재사용, 중복 요청,
시간 초과·인증 오류의 미평가, 실행 중 변경 차단, writer 독립 역할, 호출 한도를 검사한다.
전체 백엔드 pytest와 프론트 Vitest 281건, 타입 검사·ESLint·Ruff·모듈 경계 3개 계약을 통과했다.
분리된 `.next-jev-check` 폴더의 Next 배포 빌드도 통과했고 빌드가 추가한 임시 tsconfig 항목은 제거했다.
기존 첨부·Excel·ZIP·승인 무효화 E2E는 27.9초에 통과했다.
화면 회귀 10건 통과 후 규격 화면 8건은 새 classification 조회가 모의 응답 목록에 없어 실패했다.
해당 GET에 JEV 비활성 응답을 명시하고 8건을 재실행해 모두 통과했다. 별도 legacy 환경 전용 2건은 생략했다.
검증 DB를 별도로 조회해 분류 행 1건과 작업 결과의 전체 payload가 일치함을 확인했다.
API 및 두 실행기의 지문은 `current`, `restart_required=false`였다.
별도 대조 증거는 `data/workspace/e2e-20260921/jev-db-runtime.json`에 있다.
OpenAPI 변경은 classification 조회 응답과 JobRequest의 jev/classification_hash를 포함한다.

SDK 자동 재시도는 꺼져 있다. 실패나 응답 불명 요청을 그대로 다시 실행하는 예외 API는 없다.
같은 공고·내용·정책은 모델을 변경해도 최대 2회이며 정확히 같은 요청은 최초 기록을 반환한다.
실제 회사 정책·공고의 정답 대조, 신뢰도 보정 및 팀 역할 운영 리허설은 이번 가상 검증 범위 밖이다.
