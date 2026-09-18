# 실제 프로그램 E2E 1차 실행 — 2026-09-13

## 실행 환경

`infra/start-workspace.ps1`로 최신 작업대 API(127.0.0.1:8002), 화면(127.0.0.1:3002),
local/external 분리 실행기를 시작했다. 로컬 `.venv`와 기존 PostgreSQL 검증 DB
`autojebi_workspace_v2_check`를 사용했다. 시작 전 대기/실행 작업은 0개였다.
기존 운영 API(8001)와 실공고 자료·승인은 변경하지 않았다. 검증 프로그램은 실행 상태로 남겼다.

## 실제 문서 루프

- 시험 공고: `E2E-SAMPLES-1789233676137`
- 화면: `http://127.0.0.1:3002/workspace/E2E-SAMPLES-1789233676137#review`
- 최종 입력 버전: 18 / 요구사항 3개 / 초안 3개 / `ready=false` / 해당 공고 대기 작업 0개.
- 결과: Playwright headed 브라우저의 `sample-document-loop.spec.ts` 1 passed (약 1.1분).
  API 모의 응답 없이 실제 DB, 업로드 저장소, 작업 큐와 파일 다운로드를 사용했다.
- 자료는 `output/pdf/document-loop-samples`의 TEST ONLY 예시 PDF 3개다.
  가상 증빙·초안 검토는 테스트 공고에만 기록했으며 실공고의 제출 승인이 아니다.

| 단계 | 관측 결과 |
|---|---|
| 공고 등록·검색·검토 시작 | 실제 UI에서 새 시험 공고 생성 및 상세 진입 |
| PDF 업로드·본문 추출 | 공고/제품 근거/이전 제안서 업로드, 실제 extract 작업 2회 완료 및 결과 반영 |
| 요구사항 등록 | 원문 인용·가상 근거·제안값 연결 3건; 기존 검토 유지 확인 |
| 작성 대상 확인 | 현재 UI의 수동 작성 항목 추가 및 정성제안서 분류/확인 |
| 회사자료 비교·작성 | 이전 2대·60일·12개월을 현재 3대·30일·24개월로 수정한 초안 3건 저장 |
| 초안 검토 | 근거 없는 승인 차단, 검증 표식 제거·요구사항/가상 근거 연결 후 검토 저장 |
| 누락 검사 | 실제 verify 작업 완료 |
| Excel | 실제 생성·다운로드·반려 기록 확인 |
| 패키지 | 실제 생성·다운로드, ZIP 무결성 및 manifest 공고 번호 확인 |
| PDF 원본 | 페이지 PNG 응답, 이미지 픽셀과 브라우저 표시 확인 |
| 화면 크기 | 데스크톱 및 390px에서 가로 넘침 검사, 스크린샷 보존 |
| HWP | 필드 검사 `blocked / template_path`; 생성 완료로 집계하지 않음 |

초기 실행은 오래된 테스트 동선 때문에 접힌 의견/파일관리 영역과 기존 ReferenceWriter
선택자에서 멈췄다. 화면의 summary를 클릭해 펼치고, 현재의 작성 대상 확인 → 문서별
작성 경로, 접근성 이름, 중복 상태 표시에 맞춰 E2E를 보정했다. 애플리케이션의 검토
조건을 완화하거나 실패를 건너뛰어 통과시키지 않았다. 이전 실패 시험 공고와 기록도 보존했다.

## 다운로드 검증

결과 폴더: `data/workspace/sample-loop/E2E-SAMPLES-1789233676137/`

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| requirements.xlsx | 6,269 bytes | `3535e832a9697df3a394b5b41a78a40ad7c389e522f59d95ef1dd3716ba53c7b` |
| review-package.zip | 124,421 bytes | `049e6c51febe569b1d186a6d84ecca7ba8167bfc95418782e23badaf71320e58` |

다운로드 바이트 해시는 각 작업의 서버 기록과 일치했다. 두 ZIP의 CRC 검사를 통과했다.
패키지는 HWP 두 종류 미생성과 Excel 검토 미승인 경고를 정확히 포함한다.
이미 생성된 패키지나 Excel을 최종 승인하지 않았다.

## 실공고 원본 HWPX 조회

`R26BK01715307-000`의 기존 입력 버전 9를 그대로 열어 새 “작성본 검토 시작”을 실행했다.
검토 대기 / 미작성 12개 / 승인 비활성 상태와 해시를 지정한 다운로드 링크를 확인했다.
다운로드 HTTP 200, 233,108 bytes, SHA-256은
`523ecb16a78ad080c13b03345c57c041938e51faccbc11a7c3dc5da8a02444b4`로 검토 대상과 일치한다.
원본·배치 확인 체크박스와 승인/반려를 조작하지 않았다.
상세 해시 대조 결과는 `data/workspace/e2e-20260913/runtime-verification.json`에 있다.

## 남은 차단과 범위

아래는 최초 실행 시점의 상태다. 이후 Worker 복구와 CRLF 실생성, 과거 실패 입력 재검증, HWP 및 새 패키지 다운로드는 [HWP 후속 검증](hwp-recovery-e2e-2026-09-13.md)에서 완료했다. 기본 템플릿 누락과 실공고 최종 검증은 남아 있다.

- 기본 `bid_form` 템플릿은 허용 폴더에 없어 `template_path`로 차단됐다.
  설치된 한글 COM 등록은 조회됐지만 실제 활성화/새 파일 생성 검증은 아니다.
- HWP 복구 상태 CLI는 `recovery_required=true`를 반환했다. Worker를 새로 기동하거나
  복구 표식을 해제하지 않았다. 실행 UI에서는 Worker 연결 안 됨/시간 초과가 표시됐다.
- 시험 공고의 마감일시와 회사 필수정보가 미입력이다. `ready=false`가 정상이다.
- CRLF 수정 후 실제 HWP 재생성·배치 대조 및 실공고 최종 제출본 검증은 미완료다.
- 이번 실행에서 유료 LLM, G2B 라이브 검색, 알림 실전송, 실제 투찰은 실행하지 않았다.
- 보정한 E2E의 프론트 타입 검사, 파일 ESLint, `git diff --check` 통과.

재실행 명령:

```powershell
cd frontend
$env:E2E_BASE_URL='http://127.0.0.1:3002'
$env:E2E_API_BASE='http://127.0.0.1:8002'
$env:E2E_WORKSPACE_V2='true'
$env:E2E_SAMPLES='true'
npm run e2e -- --project=workspace-v2 sample-document-loop.spec.ts --headed
```

이 명령은 새 TEST ONLY 공고를 생성한다. 기존 공고를 초기화하거나 삭제하지 않는다.
