# Document Engine 1단계 기능 테스트

2026-09-23. 사용자의 기능 테스트 요청으로 로컬 한글과 인증된 Worker에서 실행했다.
실제 공고나 회사 자료 대신 TEST ONLY 합성 문서를 사용했다.

## 결과

| 검증 | 결과 |
|---|---|
| HWP 관련 단위·통합·아키텍처 테스트 | 215 passed, 4 skipped |
| `/document/create-template` | 새 시험 템플릿 생성·재열기·해시 검증 통과 |
| `/document/generate` → HWP | 23개 필드, 3페이지, 저장값·구조·해시 검증 통과 |
| `/document/generate` → HWPX | 23개 필드, 3페이지, 저장값·구조·해시 검증 통과 |
| `/document/put-fields` → HWP | 23개 필드, 3페이지, 저장값·구조·해시 검증 통과 |
| LF/CRLF·한글·숫자·표 셀 | 입력값을 정규화한 전체 필드별 저장값 대조 통과 |
| 원본 템플릿 보존 | 세 생성 작업 이후 해시 동일 |
| PNG 미리보기 | 9개 파일 해시 검증; 출력 세 종류의 대응 페이지 해시 동일 |
| 인증 누락 | HTTP 401 |
| 기존 출력 덮어쓰기·경로 탈출·미지원 PDF 옵션 | 각각 HTTP 422; 기존 출력 해시 유지 |
| 종료 후 Worker | 정상 대기, 큐 비어 있음, 복구 차단 없음 |

4개 skip은 호스트의 symlink 생성 권한 제한에 따른 테스트다.
실파일 생성 중 실패·재시도·복구 표식 해제는 없었다.

3개 고유 페이지 이미지를 직접 확인했다. 제목·한글·줄바꿈·표 셀·목록·페이지 번호가
보이고, 눈에 띄는 잘림이나 겹침은 없었다. 이는 합성 시험 문서의 에이전트 확인이며
실제 공고 최종본에 대한 담당자 배치 승인이나 운영 전환 승인으로 간주하지 않는다.

## 실행과 산출물

재현 도구: `tools/verify_hwp_document_engine.py`.
인증·허용 폴더·단일 COM 큐는 Worker가 처리하며 도구는 COM에 직접 접근하지 않는다.
쓰기 요청은 재시도하지 않고, 응답 불명/실패 시 중단하며 테스트 폴더에 증거를 보존한다.

```powershell
$env:HWP_LIVE_SMOKE = 'true'
.venv/Scripts/python.exe -m tools.verify_hwp_document_engine
```

기존 Worker가 없어 `infra/start-hwp-worker.ps1`로 현재 코드의 Worker를
localhost:8000에 시작했다. 테스트 종료 시 Worker는 정상 대기 상태다.

산출물 디렉터리(런타임 자료, 커밋 제외):

`data/workspace/exports/engine-test-2d000264e24b4b37b4f9eb697c005ed4/`

- `generate-hwp.hwp`, `generate-hwpx.hwpx`, `legacy-hwp.hwp`
- `*-pages/page-001.png`부터 `page-003.png`까지 각 3장
- `input.json`: 합성 입력값, 필드·표 명세
- `*-response.json`: 템플릿 제작 및 각 생성 요청의 응답 증거
- `verification.json`: 구조·필드·해시·페이지 검증 결과
- `boundary-checks.json`: 실제 HTTP 오류 요청 차단 결과

pyhwpx 활성화, syhwp ingestion, Linux HWPX 생성, PDF 변환은 이번 테스트 대상이 아니다.
현재 HWPX 생성도 Windows COM 경로다. 실제 공고 검증과 담당자 최종본 대조는 별도로 남아 있다.
