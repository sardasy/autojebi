# kordoc 수동 문서 추출 비교

2026-09-23 적용. `kordoc@4.14.1`을 공고 HWP/HWPX의 읽기 전용 비교 추출기로 연결했다.
기존 `extract`, HWP 생성/저장값 검증, 승인·참가 결정·RAG 입력은 그대로 유지한다.

## 사용

외부 작업 실행기 호스트에 Node >=22.13과 고정된 런타임을 설치한다. 이번 로컬 검증은 Node 24.11.1을 사용했다.

```powershell
cd tools/kordoc_runtime
npm ci --omit=optional --ignore-scripts --no-audit --no-fund
cd ../..
```

API와 external 실행기 환경에 `WORKSPACE_KORDOC_ENABLED=true`를 설정하고 재시작한다.
Node 경로를 찾지 못하면 `KORDOC_NODE_BIN`에 실행파일 절대 경로를 지정한다.
저장소 예제 기본값은 false이며, 이번 로컬 `.env`는 true로 설정했다. 기존 실행 프로세스에는 재시작 시 반영된다.
Python 전용 Docker 이미지에는 Node 런타임이 없다. 이 기능의 external 실행기는 위 런타임을 설치한 호스트에서 실행한다.
기존 split supervisor와 all 실행기를 중복 실행하지 않는다.

화면: **공고 서류 검토 → 원문·상세 검토 → 문서 추출 비교 · 검증용 → 실행**.
회사 증빙·제품 증빙·참고자료는 대상에서 제외한다. HWP/HWPX 이외 문서는 비교 제외로 표시한다.
동일 입력 버전의 작업은 기존 큐 중복 방지 규칙을 따른다. 입력이 바뀌면 이전 비교 결과는 과거 입력으로 표시한다.

API는 기존 `POST /v2/notices/{notice_no}/jobs`에 다음 작업 종류를 추가했다.

```json
{"kind":"document_compare","input_version":1,"idempotency_key":"comparison-unique-id"}
```

`WorkspaceRecord.kordoc_comparison_enabled`는 기능 표시 여부이며, 런타임 설치 성공을 보장하는 health 결과는 아니다.
개인 인증 사용 시 기존 writer 작업 권한을 적용한다. 승인 API는 산출 파일이 없는 비교 결과의 승인을 거부하고,
apply API도 해당 종류를 반영하지 않는다. 실행 결과는 작업 이력에만 저장한다.

## 데이터와 실행 경계

- `api/services/kordoc_client.py`: 기존 구조/보호문서 검사 후 바이트를 Node stdin으로 전달. 원본 파일 경로를 라이브러리에 제공하지 않는다.
- `tools/kordoc_runtime/runner.mjs`: `parse(Buffer)` → 버전/해시/본문/Markdown/표/셀/블록 위치/경고의 JSON 계약.
- Node permission으로 자식 프로세스·워커·네이티브 addon·파일 쓰기를 허용하지 않는다. 읽기 권한은 런타임 디렉터리만 부여한다.
- 별도 guard로 알려진 Node 네트워크·프로세스 API를 차단하고 `KORDOC_OFFLINE=1`, OCR/formula OCR off를 적용한다. OS 네트워크 격리나 적대적 JavaScript 전용 보안 샌드박스로 간주하지 않는다.
- kordoc의 Windows COM fallback을 사용하지 않는다. COM 관련 경고 결과도 거부한다. 전역 설치·MCP 등록·레지스트리 등록을 하지 않는다.
- 하위 프로세스에 API 키·사용자 환경·NODE_OPTIONS를 전달하지 않는다. 라이브러리 로그와 예외 원문은 사용자/작업 로그에 전달하지 않는다.
- 문서당 50MB, 30초, stdout 4MB, V8 heap 256MB. 공고 원문 10개, 결과 합계 8MB까지다.
- 원본 SHA-256은 실행 전/후와 Node 응답에서 확인한다. 문서 하나의 파싱 실패는 문서별 오류로 남기고 다음 문서를 처리한다.
- `api/parsing/kordoc.py`는 구조 계약과 토큰 차이만 검사한다. 블록 위치는 후보이고 검증된 인용이 아니다.
- page mode가 `section`/`unknown`이면 실제 페이지 번호를 제공하지 않는다. `layout`도 사람의 원문/배치 검토를 대체하지 않는다.
- `verified=false`, `review_required=true`를 강제한다. 토큰 차이 0도 사실성·누락 없음·정확도 100%를 뜻하지 않는다.

## 검증 결과

- 백엔드 전체 pytest 통과(기존 환경 의존 테스트 skip 포함). 추가로 원본 변경/해시 불일치/개별 실패 격리, 적용·승인 거부 회귀 통과.
- ruff, import-linter 3개 계약, OpenAPI 스냅샷, 프론트 lint/typecheck 통과.
- 프론트 42개 파일 291개 테스트, 프로덕션 빌드 통과. 수동 클릭으로만 실행되는 Playwright 비교 화면 E2E 통과.
- Node guard 테스트: 권한 없는 실행 거부, COM 프로세스 실행·네트워크·파일 쓰기 차단 통과.

실파일 파싱은 아래 5개 모두 성공했고, 실행 후 원본 해시가 동일했다.

| 파일 | 문자 수 | 표 | 구조 조각 | page mode |
|---|---:|---:|---:|---|
| 합성 생성 HWP | 241 | 1 | 21 | section |
| 합성 생성 HWPX | 243 | 1 | 23 | section |
| R26BK01728736-000의 HWP 1개 | 5,949 | 3 | 94 | layout |
| R26BK01722905-000의 HWP 1개 | 4,540 | 3 | 98 | section |
| R26BK01721736-000의 HWP 1개 | 9,125 | 7 | 141 | layout |

로컬 상세 결과: `data/workspace/kordoc-validation/5e9c597c4c4c4c7c9bc9038ed1619fa2/`.
실제 공고 HWP 3건은 파싱·구조 반환·원본 불변성을 확인한 것이며 COM 원문과 전수 대조한 정확도 검증은 아니다.
합성 HWPX의 기존 추출기는 필드 지시문도 본문에 포함하여 토큰 차이가 발생했다. 이 차이를 곧바로 누락으로 판정하지 않는다.
표 병합·중첩표·머리말/꼬리말·수식의 실제 공고 담당자 대조 후 주 추출기 채택 여부를 결정한다.

독립 실파일 재검증(운영 DB/COM 호출 없음):

```powershell
$env:WORKSPACE_KORDOC_ENABLED='true'
.venv/Scripts/python.exe -m tools.verify_kordoc path/to/source.hwp path/to/source.hwpx
```

HWPX는 기존 로컬 추출 본문과 비교한다. 독립 CLI의 HWP는 저장된 기존 본문이 없으므로 `no_baseline`이다.
작업대에서는 입력 스냅샷의 기존 본문을 비교 기준으로 사용한다.

상위 프로젝트: [kordoc](https://github.com/chrisryugj/kordoc), MIT 라이선스.

## 실제 프로그램 실행 검증

2026-09-23 사용자 요청으로 로컬 작업대를 실행하고 브라우저에서 직접 검증했다.
API `127.0.0.1:8002`, 화면 `127.0.0.1:3002`, PostgreSQL 및 split local/external 실행기를 사용했다.
공고 `E2E-KORDOC-LIVE-20260923-01`은 합성 검증 전용이며 실제 입찰 공고가 아니다.

1. 화면에서 공고 등록·검토 시작·합성 HWP/HWPX 업로드 완료.
2. 기존 본문 추출 작업 실행 후 두 문서 결과 반영 완료(입력 v4).
3. 화면의 문서 추출 비교 버튼으로 실제 external 큐와 Node kordoc 실행, 두 문서 모두 `compared`.
4. HWP는 기존 COM 본문과 토큰 차이 0개, 표 1개/셀 8개를 화면에서 확인.
5. HWPX는 표 1개를 추출했고 기존 본문의 필드 제어문 때문에 토큰 차이 230개가 표시됨.
6. 작업 전후 입력 전체·버전·검토 기록·참가 결정·ready 상태·두 원본 해시 동일.
7. 재실행 후 비교 작업은 1개로 유지. 새로고침 뒤 저장 결과와 표·셀 표시 유지.

기능 실행 검증은 통과했다. 기존 HWPX 추출기의 필드 제어문 혼입은 이번 비교로 확인된 별도 개선 항목이다.
정확도 전수 검증이나 제출 준비 승인을 의미하지 않는다.
실행 전 상태 지문·비교 결과·12개 검증 결과는 `data/workspace/kordoc-validation/live-20260923-01/`에 보존했다.
프로그램과 비교 결과 브라우저 탭은 사용자 확인을 위해 실행 상태로 남겼다.

## 후속: 본문 추출·비교 v2

같은 날 [문서 비교 v2](document-comparison-v2-2026-09-23.md)를 적용했다. 위 230토큰 결과는 이전 방식의 이력으로 유지한다. 새 화면은 본문 내용 차이와 필드 제어문 23묶음을 구분하며, 수동 본문 정리 반영 후 제어문 차이는 0묶음으로 바뀐다. 버전별 계약, ADR-4 재검토 정책, 테스트·실화면 결과와 최대 실파일 측정의 한계는 후속 기록을 따른다.
